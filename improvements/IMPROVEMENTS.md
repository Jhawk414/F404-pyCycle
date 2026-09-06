# Repo Improvements Roadmap

Forward-looking architectural changes discussed after closing out
`feature/alt-mach-sweep` (see `HANDOFF_05Sep26.md` for the branch's actual
accomplishments). None of this is implemented yet — it's a plan to work
from in a new branch.

## 1. Move F404 application code out of the repo root into `/src/`

This repo is a fork of the `pycycle` library (`pycycle/`, `setup.py`,
`pyproject.toml`, `.travis.yml`, `example_cycles/`, `release_notes.md` are
all upstream library scaffolding). The F404-specific application code
currently lives loose at the repo root, mixed in with that scaffolding:

| File | Role | Proposed location |
|------|------|--------------------|
| `MFTF_od_CRZ.py` | Original monolithic model — superseded by `engine_model.py` + `mp_cycle.py` | Archive or delete (confirm nothing still depends on it) |
| `engine_model.py` | `MixedFlowTurbofan(pyc.Cycle)` — single-point cycle | `src/F404_pycycle/engine_model.py` |
| `mp_cycle.py` | `MPMixedFlowTurbofan(pyc.MPCycle)` — DESIGN+OD | `src/F404_pycycle/mp_cycle.py` |
| `sweep_utils.py` | Sweep infrastructure (`SweepRunner`, bridge points) | `src/F404_pycycle/sweep_utils.py` |
| `sweep_full_envelope.py` | Sweep driver script | `src/F404_pycycle/sweep_full_envelope.py` (or `scripts/` if we want to separate "library" from "runnable entry point") |
| `run_design_od.py` | Single design+OD point runner | Same as above |
| `printer.py` | Console/terminal output formatter for cycle results | `src/F404_pycycle/viz/printer.py` or `src/F404_pycycle/reporting/printer.py` — it's an auxiliary output utility, not part of the physics model, and should be namespaced as such |

`setup.py` at the root is the **vendored pycycle package's** setup file,
not F404 app code — don't move it as part of this cleanup. If the F404
app code becomes its own installable package, it needs its own
`pyproject.toml`/`setup.py` under `src/F404_pycycle/` (or wherever it
lands), separate from pycycle's.

**Also clean up:** `HANDOFF_22Apr26.md` and stray `*_out/` sweep artifact
directories don't belong in version control long-term (`*_out/` is now
gitignored). The `.rtf` note file at the root, on the other hand, is being
kept and committed as reference material for item 5's solver-log format —
see the "Solver convergence log" note under item 5.

## 2. Test suite convention

For every module under `src/`, add a sibling `<module>_test.py`. Coverage
should include, per module, as applicable:

- **Unit tests** — individual functions in isolation (e.g.
  `build_snake_sweep`, `generate_bridge_points`, `extract_od_results` in
  `sweep_utils.py` are pure-ish functions and should be directly testable
  without spinning up an `om.Problem`).
- **Integration tests** — full `om.Problem` build + `run_model()` for a
  known design point, asserting against previously-verified numbers. This
  is exactly the kind of regression check that belongs here; the original
  baseline (from `HANDOFF_22Apr26.md`, `run_design_od.py` verified
  numerically identical to the pre-refactor `MFTF_od_CRZ.py`) was:

  | Variable | Value |
  |----------|-------|
  | DESIGN.Fn | 19338.46 lbf |
  | DESIGN.W | 133.02 lbm/s |
  | DESIGN.BPR | 0.35 |
  | DESIGN.TSFC | 1.4584 |
  | OD.Fn | 17359.00 lbf |
  | OD.W | 143.57 lbm/s |
  | OD.BPR | 0.35 |
  | OD.TSFC | 1.4059 |

  Note this predates the dry/wet split (single Fn target = 17,700 lbf,
  BPR bounds 0.3–0.35) — it's no longer a valid target for the current
  model, but is worth keeping as a historical checkpoint of "the modular
  refactor didn't change the physics." A fresh baseline against the
  current dry/wet DESIGN points should be captured once item 1's `src/`
  layout lands and this test suite is actually written.
- **Fail-fast tests** — assert that known-bad inputs (e.g. a `power`
  target the model can't reach, a negative altitude) raise or are rejected
  clearly, rather than silently producing a garbage-but-"converged"
  result. This directly targets the class of bug fixed on
  `feature/alt-mach-sweep` (bound-saturated states reported as
  converged) — a regression test locking in `err_on_non_converge=True`
  plus the saturation/target checks in `SweepRunner._run_point` would
  have caught that regression immediately instead of requiring several
  rounds of debugging.

## 3. Pydantic models for validated inputs (larger refactor, not urgent)

Candidates for `pydantic` models once the src/ layout exists:
- Design-point input sets (`fn_target`, `Tt4`, `Tt7`, PR/eff guesses) —
  currently passed as loose `float` args and `prob.set_val()` calls with
  no validation that e.g. a PR is > 1 or an efficiency is in (0, 1).
- Sweep point definitions (`{'alt', 'dTs', 'power'}` dicts) — currently
  untyped dicts threaded through `build_snake_sweep` → `SweepRunner`.
  A `SweepPoint` model would catch typos/unit mistakes at construction
  time instead of at Newton-failure time.
- `BalanceComp` bound definitions (the `_OD_BOUNDS` dict in
  `sweep_utils.py`) — currently hand-maintained in parallel with the
  actual bounds declared in `engine_model.py`; a shared model (or at
  least a single source of truth) would remove the drift risk noted in
  that file's docstring.

This is explicitly lower priority than items 1-2 and 4-5 — worth doing
once the module boundaries from the `src/` restructure are stable, not
before.

## 4. Branch hygiene

`feature/alt-mach-sweep` grew beyond its original scope (sweep
infrastructure) into cycle calibration and convergence-robustness work.
Going forward:
- Close out `feature/alt-mach-sweep` once the cleanup items in
  `HANDOFF_05Sep26.md` are resolved.
- Start a new, narrowly-scoped branch per major thread instead of
  stacking unrelated work:
  - e.g. `refactor/src-layout` for items 1-2 here
  - e.g. `feature/single-engine-sizing` for the `docs/single_engine_mode.md`
    work (dry/wet engines currently differ by ~1-2%)
  - Keep the pydantic refactor (item 3) as its own branch once the
    layout work lands, rather than bundling it in.

## 5. `/deck/` — a durable home for validated cycle-deck results

Proposal: a top-level `deck/` folder, written to only when a sweep's
results have been reviewed and accepted as good/representative (not every
exploratory run) — with subfolders:

```
deck/
  steady-state/
    dry_envelope_v1.csv
    wet_envelope_v1.csv
  transient/        # future — not started
```

**On file format** — worth thinking through since this folder is meant to
be browsable by people who land on the GitHub repo, not just you in
PyCharm:

- **CSV (current format, e.g. `cycle_deck_wet.csv`)** — GitHub's web UI
  auto-renders `.csv`/`.tsv` files as a sortable, filterable table when
  you click on them in the repo browser — no plugin needed, this works
  for anyone browsing github.com. (There's a file-size ceiling above
  which GitHub falls back to a plain-text/blob view instead of the table
  — worth keeping individual deck files under that by splitting per
  mode/power-level rather than one giant combined file.) CSV also opens
  natively in Excel, Numbers, and `pandas.read_csv` with zero friction.
  This is likely still the best primary format for the actual data.
- **YAML** — as you noted, unreadable at scale; fine for a handful of
  named config values, bad for a few hundred rows × 20 columns.
- **JSON** — same problem as YAML for tabular data, plus no GitHub table
  rendering (renders as syntax-highlighted text/tree).
- **Parquet** — compact and fast for tooling, but opaque to a human
  clicking around on GitHub — wrong fit for "public users should be able
  to view it," even though it'd be the right choice for a large archival
  dataset.

**Recommendation:** keep CSV as the source-of-truth format in `deck/`
(it's already what you're producing, and it's the one format here that's
natively browsable on github.com without extra tooling). If the concern
is that a full CSV is still a lot to skim visually, consider generating
a short companion Markdown summary (e.g. `deck/steady-state/README.md`
with a small table of representative points — SLS, cold-day max-AB,
altitude corners — plus a link to the full CSV) *auto-generated* from the
CSV rather than hand-maintained, so it can't drift out of sync.

**Solver convergence log ("document of record"):** alongside each deck
CSV, capture the plaintext terminal output of the sweep run that produced
it — the Newton solver's per-point iteration/convergence log — as a
sibling file (e.g. `deck/steady-state/wet_envelope_v1.log`). This is the
same role an Ansys Mechanical `solve.out` plays: proof that a specific
deck was generated by a run that actually converged as claimed at each
bridge point, not just a CSV with no record of *how* it got there.
`test_modes good run 23Apr26 .rtf` (kept, uncommitted-for-now, at the repo
root) is effectively a prototype/example of this — a captured solver log
from a known-good `test_modes.py` run. Once `deck/` exists, this pattern
should be formalized: redirect `SweepRunner`'s stdout to a `.log` file per
run instead of only printing to the terminal, and store it next to the
CSV it documents.

## 6. Replace the README

The repo's `README.md` is still the default upstream `om-pycycle` README
from the original fork — it doesn't mention the F404 work at all. Needs a
full rewrite covering:

- High-level purpose/function of this repo (F404 mixed-flow turbofan
  cycle deck built on pyCycle) — a few sentences, not a spec.
- A photo of the F404 engine with afterburner lit.
- Local clone/install instructions.
- A high-level architecture diagram (mermaid or D2) showing how
  `engine_model.py` / `mp_cycle.py` / `sweep_utils.py` /
  `sweep_full_envelope.py` relate — this should get revisited once the
  `src/` restructure in item 1 actually lands, so the diagram matches
  real module paths instead of the current root-level layout.
- Starter usage commands — running a single DESIGN+OD point, running a
  full alt/Mach/dTs sweep (e.g. `python sweep_full_envelope.py --mode
  both`).
- Current-capabilities vs. planned checklist (sweep infra done; single-
  engine dry/wet sizing, `src/` layout, deck/ folder, test suite —
  planned, per items 1-5 above).

Best sequenced after item 1 (`src/` restructure) so the architecture
diagram and usage commands don't need a rewrite the moment paths move.
