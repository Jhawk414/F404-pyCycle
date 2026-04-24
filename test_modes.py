"""
Smoke test for dry and wet afterburner modes.

Runs four points in sequence:
  1. DESIGN (dry)  — SLS, mil Tt4, afterburner off
  2. OD     (dry)  — same alt/MN as design, same Tt4 — should reproduce design thrust
  3. DESIGN (wet)  — SLS, mil Tt4, Tt7 = 3800 degR (max AB; anchors engine sizing)
  4. OD     (wet)  — same alt/MN/Tt4 as wet design; Tt7 reduced to 3600 degR (partial AB)

NOTE — design point thrust targets:
  DRY_DSN_FN: F404 produces ~17,700 lbf ONLY with max afterburner.
              Dry mil thrust is lower — fill in DRY_DSN_FN below with your value.
  WET_DSN_FN: 17,700 lbf at Tt7=3800 degR is the correct max-AB design anchor.
              OD points at lower T7 (partial AB) will produce less thrust.

NOTE — two separate om.Problem instances are required because the FAR_ab
balance is structural and cannot be toggled at runtime.

Usage:
    python test_modes.py
"""
import time
import warnings

import openmdao.api as om

from mp_cycle import MPMixedFlowTurbofan
from printer import page_viewer

# Silence noisy-but-expected warnings during Newton iteration on pyCycle models
warnings.filterwarnings('ignore', category=RuntimeWarning)
try:
    from openmdao.utils.om_warnings import SolverWarning
    warnings.filterwarnings('ignore', category=SolverWarning)
except ImportError:
    pass

# ── Performance targets ───────────────────────────────────────────────────────
# TODO: replace DRY_DSN_FN with the F404's actual SLS mil (dry) thrust in lbf.
# The -402 variant is nominally ~11,000 lbf dry; confirm against test data.
DRY_DSN_FN = 11_000.  # lbf — SLS mil power (no afterburner)
WET_DSN_FN = 17_700.  # lbf — SLS max afterburner

# ── Shared operating conditions ───────────────────────────────────────────────
ALT    = 0.0    # ft
MN     = 0.01   # Mach — SLS (static-ish)
Tt4    = 3100.  # degR — core burner exit, mil power (both modes)

# Wet mode T7 targets
WET_DSN_Tt7 = 3800.  # degR — design-point afterburner exit (max AB; matches WET_DSN_FN)
WET_OD_Tt7  = 3600.  # degR — OD afterburner exit (stepped down from design)


def _set_design_inputs(prob, Fn_target):
    prob.set_val('DESIGN.fc.alt', ALT, units='ft')
    prob.set_val('DESIGN.fc.MN', MN)
    prob.set_val('DESIGN.balance.rhs:W', Fn_target, units='lbf')
    prob.set_val('DESIGN.balance.rhs:FAR_core', Tt4, units='degR')
    prob.set_val('DESIGN.fan.PR', 4.1)
    prob.set_val('DESIGN.fan.eff', 0.8948)
    prob.set_val('DESIGN.hpc.PR', 6.5)
    prob.set_val('DESIGN.hpc.eff', 0.8707)
    prob.set_val('DESIGN.hpt.eff', 0.8888)
    prob.set_val('DESIGN.lpt.eff', 0.8996)
    # Initial guesses
    prob['DESIGN.fc.balance.Pt']       = 5.3
    prob['DESIGN.fc.balance.Tt']       = 450.
    prob['DESIGN.balance.W']           = 120.0
    prob['DESIGN.balance.BPR']         = 0.65
    prob['DESIGN.balance.FAR_core']    = 0.025
    prob['DESIGN.balance.hpt_PR']      = 2.5506
    prob['DESIGN.balance.lpt_PR']      = 2.5  # chosen so core exit P ≈ bypass exit P (ER≈1)
    prob['DESIGN.mixer.balance.P_tot'] = 55.  # ≈ bypass total P, not the old 20


def _set_od_guesses(prob, pt):
    prob[pt + '.fc.balance.Pt']        = 14.7
    prob[pt + '.fc.balance.Tt']        = 519.
    prob[pt + '.balance.FAR_core']     = 0.025
    prob[pt + '.balance.BPR']          = 0.35
    prob[pt + '.balance.W']            = 100.
    prob[pt + '.balance.HP_Nmech']     = 15000.
    prob[pt + '.balance.LP_Nmech']     = 10000.
    prob[pt + '.mixer.balance.P_tot']  = 55.
    prob[pt + '.hpt.PR']               = 2.523
    prob[pt + '.lpt.PR']               = 2.401
    prob[pt + '.fan.map.RlineMap']     = 2.0
    prob[pt + '.hpc.map.RlineMap']     = 2.0


def header(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


# ── DRY PROBLEM (afterburn=False) ─────────────────────────────────────────────
header("DRY MODE — building problem...")
prob_dry = om.Problem()
prob_dry.model = mp_dry = MPMixedFlowTurbofan(afterburn=False)
prob_dry.setup()

_set_design_inputs(prob_dry, DRY_DSN_FN)
prob_dry['DESIGN.afterburner.Fl_I:FAR'] = 0.0  # afterburner off at design

pt_dry = mp_dry.od_pt  # 'OD'
_set_od_guesses(prob_dry, pt_dry)
prob_dry[pt_dry + '.afterburner.Fl_I:FAR'] = 0.0

# Pre-set OD flight conditions so the OD solver has a sane starting point
# when prob.run_model() fires the first time (runs DESIGN and OD together).
prob_dry.set_val(pt_dry + '.fc.alt', ALT, units='ft')
prob_dry.set_val(pt_dry + '.fc.MN', MN)
prob_dry.set_val(pt_dry + '.fc.dTs', 0.0, units='degR')
prob_dry.set_val(pt_dry + '.balance.rhs:FAR_core', Tt4, units='degR')

prob_dry.set_solver_print(level=-1)
prob_dry.set_solver_print(level=2, depth=2)  # show DESIGN/OD Newton iterations

# Point 1 — Dry DESIGN
header(f"Point 1 / 4 — DRY DESIGN  (alt={ALT:.0f} ft, MN={MN}, Tt4={Tt4:.0f} R, Fn_tgt={DRY_DSN_FN:.0f} lbf)")
t0 = time.time()
prob_dry.run_model()
print(f"  elapsed: {time.time()-t0:.1f}s")
page_viewer(prob_dry, 'DESIGN')

# Point 2 — Dry OD at identical conditions to design (should reproduce Fn)
header(f"Point 2 / 4 — DRY OD      (alt={ALT:.0f} ft, MN={MN}, Tt4={Tt4:.0f} R — same as design)")
prob_dry.set_val(pt_dry + '.fc.alt', ALT, units='ft')
prob_dry.set_val(pt_dry + '.fc.MN', MN)
prob_dry.set_val(pt_dry + '.fc.dTs', 0.0, units='degR')
prob_dry.set_val(pt_dry + '.balance.rhs:FAR_core', Tt4, units='degR')
t0 = time.time()
prob_dry.run_model()
print(f"  elapsed: {time.time()-t0:.1f}s")
page_viewer(prob_dry, pt_dry)


# ── WET PROBLEM (afterburn=True) ──────────────────────────────────────────────
header("WET MODE — building problem...")
prob_wet = om.Problem()
prob_wet.model = mp_wet = MPMixedFlowTurbofan(afterburn=True)
prob_wet.setup()

_set_design_inputs(prob_wet, WET_DSN_FN)
prob_wet.set_val('DESIGN.balance.rhs:FAR_ab', WET_DSN_Tt7, units='degR')
prob_wet['DESIGN.balance.FAR_ab'] = 0.0375  # initial guess

pt_wet = mp_wet.od_pt  # 'OD'
_set_od_guesses(prob_wet, pt_wet)
prob_wet[pt_wet + '.balance.FAR_ab'] = 0.025  # initial guess

# Pre-set OD flight conditions and T7 target before first run_model().
# rhs:FAR_ab defaults to 0 (impossible target) if not set here — the FAR_ab
# balance would drive toward T7=0 R and diverge immediately.
prob_wet.set_val(pt_wet + '.fc.alt', ALT, units='ft')
prob_wet.set_val(pt_wet + '.fc.MN', MN)
prob_wet.set_val(pt_wet + '.fc.dTs', 0.0, units='degR')
prob_wet.set_val(pt_wet + '.balance.rhs:FAR_core', Tt4, units='degR')
prob_wet.set_val(pt_wet + '.balance.rhs:FAR_ab', WET_DSN_Tt7, units='degR')

prob_wet.set_solver_print(level=-1)
prob_wet.set_solver_print(level=2, depth=2)  # show DESIGN/OD Newton iterations

# Point 3 — Wet DESIGN
header(f"Point 3 / 4 — WET DESIGN  (alt={ALT:.0f} ft, MN={MN}, Tt4={Tt4:.0f} R, Tt7={WET_DSN_Tt7:.0f} R, Fn_tgt={WET_DSN_FN:.0f} lbf)")
t0 = time.time()
prob_wet.run_model()
print(f"  elapsed: {time.time()-t0:.1f}s")
page_viewer(prob_wet, 'DESIGN')

# Point 4 — Wet OD: same alt/MN/Tt4 as design, Tt7 reduced to exercise partial AB
header(f"Point 4 / 4 — WET OD      (alt={ALT:.0f} ft, MN={MN}, Tt4={Tt4:.0f} R, Tt7={WET_OD_Tt7:.0f} R — AB throttled back)")
prob_wet.set_val(pt_wet + '.fc.alt', ALT, units='ft')
prob_wet.set_val(pt_wet + '.fc.MN', MN)
prob_wet.set_val(pt_wet + '.fc.dTs', 0.0, units='degR')
prob_wet.set_val(pt_wet + '.balance.rhs:FAR_core', Tt4, units='degR')
prob_wet.set_val(pt_wet + '.balance.rhs:FAR_ab', WET_OD_Tt7, units='degR')
t0 = time.time()
prob_wet.run_model()
print(f"  elapsed: {time.time()-t0:.1f}s")
page_viewer(prob_wet, pt_wet)
