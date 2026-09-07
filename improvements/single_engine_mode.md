# Single-Engine Sizing for Dry + Wet Modes

## Problem statement

The repo currently builds two independent `om.Problem` instances — one for dry
operation (`afterburn=False`) and one for wet/AB operation (`afterburn=True`).
Each instance runs its own DESIGN solve with its own thrust target:

| Mode | DESIGN target | Resulting engine |
|---|---|---|
| Dry | `Fn = 11,000 lbf` at SLS, `Tt4 = 3100 R`, no AB | Engine A |
| Wet | `Fn = 17,700 lbf` at SLS, `Tt4 = 3100 R`, `Tt7 = 3800 R` | Engine B |

Engines A and B differ by roughly 1–2% in mass flow, map scalars, and station
areas. The dry sweep CSV reflects Engine A; the wet sweep CSV reflects Engine B.
For an F404 representation — a single physical engine that runs both dry and
wet — this is incorrect.

The dual-instance pattern was chosen because OpenMDAO's `BalanceComp` topology
is fixed at `prob.setup()` time. The FAR_ab balance can't be added or removed
at runtime, so a problem built without it (dry) and one with it (wet) must be
separate Python objects.

## Goal

Size the engine **once** at max-AB conditions (Fn=17,700 lbf, Tt7=3800 R), then
operate that same sized engine across the full throttle range — from dry mil
(Tt4=3100 R, FAR_ab=0) down through partial AB to max AB. All OD points,
whether dry or wet, should run off identical map scalars and station areas.

## Approaches

Two viable architectures, each with tradeoffs.

### Option 1: Snapshot-and-inject

Run the wet problem first. Capture its converged DESIGN values (map scalars
and station areas). Build a second problem for dry OD operation that *skips*
DESIGN sizing and consumes the snapshot as fixed inputs.

**What gets snapshotted from the wet DESIGN:**

```
fan.s_PR, fan.s_Wc, fan.s_eff, fan.s_Nc
hpc.s_PR, hpc.s_Wc, hpc.s_eff, hpc.s_Nc
hpt.s_PR, hpt.s_Wp, hpt.s_eff, hpt.s_Np
lpt.s_PR, lpt.s_Wp, lpt.s_eff, lpt.s_Np

inlet.area, fan.area, splitter.area1, splitter.area2,
splitter_core_duct.area, hpc.area, bld3.area, burner.area,
hpt.area, hpt_duct.area, lpt.area, lpt_duct.area,
bypass_duct.area, mixer.area, mixer.Fl_I1_stat_calc.area,
mixer_duct.area, afterburner.area
mixed_nozz.Throat:stat:area  (drives balance.rhs:W in OD)
```

**Implementation sketch:**

```python
def snapshot_design(prob_wet):
    """Return a dict of converged DESIGN map scalars and station areas."""
    snap = {}
    for comp in ('fan', 'hpc'):
        for s in ('s_PR', 's_Wc', 's_eff', 's_Nc'):
            snap[f'{comp}.{s}'] = float(prob_wet[f'DESIGN.{comp}.{s}'])
    for comp in ('hpt', 'lpt'):
        for s in ('s_PR', 's_Wp', 's_eff', 's_Np'):
            snap[f'{comp}.{s}'] = float(prob_wet[f'DESIGN.{comp}.{s}'])
    for area_path, _ in AREA_TRANSFERS:  # the same list mp_cycle uses
        snap[area_path] = float(prob_wet[f'DESIGN.{area_path}'])
    snap['mixed_nozz.Throat:stat:area'] = \
        float(prob_wet['DESIGN.mixed_nozz.Throat:stat:area'])
    return snap


def setup_dry_od_only(snapshot):
    """Build a dry problem that runs OD only, fed by a wet DESIGN snapshot."""
    # afterburn=False so FAR_ab balance is absent
    # Skip the DESIGN point entirely — only add OD
    # Inject snapshot values as inputs to OD via prob.set_val()
    ...
```

**Pros:**
- Clean separation. Wet sizes the engine; dry just operates it.
- No structural changes to `engine_model.py` or `mp_cycle.py`.
- Dry mode is still a real OpenMDAO problem with the same OD balance topology.

**Cons:**
- `MPCycle` currently *requires* a DESIGN point before OD — the
  `pyc_connect_des_od` calls assume both exist. Either DESIGN must be retained
  (as a no-op passthrough that re-receives the snapshot values) or `mp_cycle.py`
  needs a "OD-only" mode added.
- Need to maintain a list of every snapshot quantity in two places (here and
  in `mp_cycle.py`'s `pyc_connect_des_od` block) — drift risk.
- Two `om.Problem` instances still — sweep code (`SweepRunner`) doesn't change,
  but the second problem has subtly different setup.

### Option 2: Single-problem-always-AB

Use `afterburn=True` for both dry and wet operation. The FAR_ab balance is
always present. For dry OD points, set `rhs:FAR_ab` such that the balance
converges to FAR_ab ≈ 0 (no afterburner fuel burned).

**Key insight:** The FAR_ab balance equation is
`afterburner.Fl_O:tot:T == rhs:FAR_ab`. If `rhs:FAR_ab` equals the afterburner
*inlet* total temperature (i.e., the mixer/mixer_duct exit total temperature),
then no fuel needs to be added and FAR_ab → 0.

For a dry OD point at fixed Tt4, the mixer exit temperature is determined by
the cycle (~1500 R typically). So we can either:

1. **Solve once at higher-level setup**: do an initial dry run with a guess for
   `rhs:FAR_ab`, read the actual `mixer_duct.Fl_O:tot:T`, then re-set
   `rhs:FAR_ab` to that value and re-solve. Two iterations to lock in dry.
2. **Add a feedback connection** from `mixer_duct.Fl_O:tot:T` to
   `balance.rhs:FAR_ab` for dry points. This adds a (trivial) loop in the
   solver graph but lets the FAR_ab balance auto-resolve to ~0 in dry mode and
   to the user-specified Tt7 in wet mode.

The mode then becomes a runtime input rather than a structural choice.

**Pros:**
- Truly one engine, one DESIGN solve, one set of map scalars.
- One `om.Problem` instance instead of two — sweep code simplifies.
- Toggle dry vs wet at runtime via a single input, without rebuilding.

**Cons:**
- The FAR_ab Newton state variable is *always* live, even in dry mode where
  it's ~0. Adds a state to the dry solve that doesn't exist today.
- The recursive `rhs:FAR_ab = mixer_duct.Fl_O:tot:T` connection (option 2.2)
  introduces a feedback loop that the Newton solver has to resolve. Likely
  harmless — the mixer duct exit temperature is independent of FAR_ab when
  FAR_ab=0 — but it's a structural change worth testing carefully.
- DESIGN must be sized at max-AB even when the deliverable is mostly dry data.
  Conceptually fine (max AB *is* the F404's design corner), but it inverts the
  "dry mil is the design throttle wall" assumption baked into a few comments.

## Recommendation

**Option 2 (single-problem-always-AB) is cleaner.** It produces a model that
behaves like a real engine: one piece of hardware, throttle setting as a
runtime variable, no parallel build. The cost is a small structural change to
`mp_cycle.py` to wire `rhs:FAR_ab` from `mixer_duct.Fl_O:tot:T` for dry points.

Option 1 is the lower-risk path if the always-AB feedback loop turns out to
cause Newton headaches. It treats the wet solve as the source of truth and
reduces dry to pure OD operation, but at the cost of duplicated state-tracking
code.

## Suggested implementation order

1. Get the current dual-engine sweep producing a clean CSV (validates the
   solver, sweep, and bridge logic end-to-end).
2. Compare wet DESIGN's converged scalars against dry DESIGN's. Quantify the
   actual % difference. If < 1%, the dual-engine artifact is empirically
   negligible and the refactor can be deferred indefinitely.
3. If the difference matters: prototype Option 2 in a branch. Wire
   `mixer_duct.Fl_O:tot:T` → `balance.rhs:FAR_ab` for dry, leave it free
   (driven by user input) for wet. Verify dry mode converges with FAR_ab ≈ 0.
4. Migrate `test_modes.py` and `sweep_full_envelope.py` onto the unified
   problem. Delete `setup_dry_problem()`; keep one `setup_problem()` that
   takes a `mode='dry'|'wet'` argument.
5. Remove the `afterburn` option from `engine_model.py` / `mp_cycle.py` once
   the unified path is stable.

## Acceptance criteria

A successful refactor produces:

- One DESIGN solve per script invocation (not two).
- Identical map scalars and station areas across all dry and wet OD points
  in the resulting CSV.
- Dry OD points report `FAR_ab ≈ 0` (within solver tolerance).
- `test_modes.py` 4-point smoke test passes with the same Fn, T4, T7, BPR,
  and ER values as the current dual-engine version (within ~1%).
