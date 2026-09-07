# Handoff: F404-pyCycle — Off-Design Sweep Convergence

Supersedes `HANDOFF_22Apr26.md` (stale — written before the dry/wet mode
question was resolved). That file should be deleted once this one is
reviewed; see `IMPROVEMENTS.md` for the broader repo cleanup this implies.

## Branch: `feature/alt-mach-sweep` — status: ready to close out

The branch's original goal (add altitude/Mach/dTs sweeping on top of the
modular cycle-deck architecture) is done. What shipped, oldest to newest:

1. **`026467f`** — Refactored the monolithic `MFTF_od_CRZ.py` into a modular
   architecture: `engine_model.py` (single-point cycle), `mp_cycle.py`
   (DESIGN+OD multi-point), `sweep_utils.py` (sweep infrastructure),
   `sweep_full_envelope.py` (driver script).
2. **`0950011` → `bb952b7` → `dd3badc`** — Fixed cycle balance convergence
   (BPR/ER targets, initial conditions), widened DESIGN BPR bounds, anchored
   the wet DESIGN point at Tt7=3800 R (max AB — the correct F404 sizing
   corner instead of an arbitrary mid-AB point).
3. **`51c9bb6`** (HEAD) — Fixed a family of convergence-detection bugs that
   were producing cycle-deck CSVs full of garbage "converged" rows
   (Fn > 100,000 lbf, BPR clipped to 1.0, LP_Nmech at its 500 rpm floor):
   - Dry-mode afterburner is now a `pyc.Duct`, not a zero-FAR `Combustor`
     (the latter produces a rank-deficient Jacobian at part power).
   - Convergence check replaced: `_iter_count < maxiter` (which silently
     accepted bound-clipped/false-positive solutions) → `err_on_non_converge
     =True` + explicit bound-saturation check + burner/AB exit-temperature
     target-met check.
   - State snapshot/restore now captures the **entire OD output vector**
     (`_outputs.asarray()`), not ~12 named primary balance variables. The
     partial-key approach left nested implicit states (e.g.
     `staticMN.ps_resid`'s internal `Ps`) uncaptured, so a restore after one
     bad cold-corner point left the model in an inconsistent state that
     degraded to non-physical gamma within a few iterations and cascaded
     through every point after it. Full-vector restore fixed the cascade.
   - Hybrid linesearch: `ArmijoGoldsteinLS` with `maxiter=0` by default
     (behaves like `BoundsEnforceLS`, fast), bumped to `maxiter=5` Armijo
     backtracks on a per-point retry.
   - `sweep_full_envelope.py` gained a `--mode dry|wet|both` flag.
   - Silenced a debug `print()` in pyCycle's `static_ps_resid.py` that fired
     on every Newton iteration touching negative gamma — was burying sweep
     status under thousands of lines of terminal spam.

### Current convergence results

Full envelope: alt ∈ {0, 2500, 5000} ft, dTs ∈ {0,±10,±20,±30,±40,±50} R,
MN=0.001 (static/runway), 4 power levels per mode.

| Mode | Converged | Notes |
|------|-----------|-------|
| Dry  | 125 / 132 | Tt4 sweep 3100→2500 R |
| Wet  | 89 / 132  | Tt7 sweep 3800→3200 R (fixed Tt4=3100 R mil) |

Both modes: every point with dTs ≥ 0 R converges. Failures are
concentrated at cold (dTs < 0 R) + high-altitude + max-AB corners — these
appear to be genuinely hard for Newton from any warm-start tried so far,
not an artifact of the convergence-detection bugs above.

### Known open issue — not part of this branch's scope

`docs/single_engine_mode.md` documents that dry and wet sweeps currently
size **two slightly different engines** (~1-2% difference in W, BPR, map
scalars) because each mode runs its own independent DESIGN solve. Two
resolution paths are laid out there (snapshot-and-inject vs. an
always-live FAR_ab balance). This is real-engine-fidelity work, not sweep
infrastructure — it belongs in a new, more targeted branch (see
`IMPROVEMENTS.md`).

## Decision made this session

The user (Ryan) wants to:
1. Close out `feature/alt-mach-sweep` — the sweep capability it set out to
   build is done and validated (125/132 dry, 89/132 wet).
2. Not continue stacking cycle-calibration / single-engine-sizing work on
   top of this branch — that's a distinct goal from "add sweeping" and
   deserves its own branch.
3. Use a new branch for: (a) the single-engine-sizing refactor from
   `docs/single_engine_mode.md`, and (b) a broader repo restructure (see
   `IMPROVEMENTS.md`) before further cycle calibration work continues.

## Uncommitted / untracked items to resolve before closing the branch

- `docs/single_engine_mode.md` — staged, not committed. Commit it (it's a
  planning doc, useful regardless of which branch continues the work) or
  move it into whatever new branch picks up that thread.
- `HANDOFF_22Apr26.md` — stale, superseded by this file. Delete.
- `cycle_deck_wet.csv` (root) — sweep output artifact, untracked. See
  `IMPROVEMENTS.md` for where validated decks should live long-term;
  either delete this one or move it once that structure exists.
- `sweep_full_envelope_out/`, `sweep_full_envelope2_out/`, `test_modes_out/`,
  `test_modes2_out/` — sweep run artifacts, untracked. Safe to delete once
  their contents are no longer needed for reference.
- `test_modes good run 23Apr26 .rtf` — untracked note file; fold anything
  useful into this handoff or delete.

## Key F404 model parameters (for reference)

- Design point: SLS (alt = 0 ft, MN ≈ 0.001–0.01)
- Dry design thrust target: 11,000 lbf (mil power, Tt4 = 3100 R)
- Wet design thrust target: 17,700 lbf (max AB, Tt7 = 3800 R)
- Thermodynamics: TABULAR / `AIR_JETA_TAB_SPEC`
- Fan PR = 4.1, HPC PR = 6.5, OPR ≈ 26.65 (wet DESIGN)
- BPR ≈ 0.75 (bounds 0.25–0.80), low-bypass mixed-flow
- No LPC (F404 architecture); `lp_shaft` has `num_ports=2` (fan + LPT only)
- Afterburner max T7 ≈ 3800 R (F404 historical max)
