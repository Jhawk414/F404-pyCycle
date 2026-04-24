"""
Full-envelope cycle deck builder for the F404 mixed-flow turbofan.

Runs two separate sweeps — dry (mil power and below) and wet (afterburning) —
using two independent om.Problem instances, one per mode.

Dry sweep
---------
  - afterburn=False: no FAR_ab balance; afterburner is a zero-FAR pass-through
  - 'power' in sweep points = Tt4 target (degR)

Wet sweep
---------
  - afterburn=True: FAR_ab balance drives T7 to target
  - 'power' in sweep points = T7 (Tt7) target (degR)
  - Tt4 is fixed at mil power (mil_Tt4) for the entire wet sweep

Usage:
    python sweep_full_envelope.py
"""
import logging
import time
import warnings

import numpy as np
import openmdao.api as om
import pandas as pd

from mp_cycle import MPMixedFlowTurbofan
from printer import page_viewer
from sweep_utils import build_snake_sweep, SweepRunner

warnings.filterwarnings('ignore', category=RuntimeWarning)
try:
    from openmdao.utils.om_warnings import SolverWarning
    warnings.filterwarnings('ignore', category=SolverWarning)
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# ── Shared design geometry ────────────────────────────────────────────────────
MIL_Tt4  = 3100.   # degR — core burner exit at mil power (throttle wall)
DSN_Tt7  = 3400.   # degR — afterburner exit at DESIGN point (wet only)
DSN_Fn   = 17700.  # lbf  — SLS design thrust target


def _apply_design_inputs(prob):
    """Set design-point values and initial guesses (shared by both modes)."""
    prob.set_val('DESIGN.fc.alt', 0.0, units='ft')
    prob.set_val('DESIGN.fc.MN', 0.01)
    prob.set_val('DESIGN.balance.rhs:W', DSN_Fn, units='lbf')
    prob.set_val('DESIGN.balance.rhs:FAR_core', MIL_Tt4, units='degR')

    prob.set_val('DESIGN.fan.PR', 4.1)
    prob.set_val('DESIGN.fan.eff', 0.8948)
    prob.set_val('DESIGN.hpc.PR', 6.5)
    prob.set_val('DESIGN.hpc.eff', 0.8707)
    prob.set_val('DESIGN.hpt.eff', 0.8888)
    prob.set_val('DESIGN.lpt.eff', 0.8996)

    # Design initial guesses
    prob['DESIGN.fc.balance.Pt']   = 5.3
    prob['DESIGN.fc.balance.Tt']   = 450.
    prob['DESIGN.balance.W']       = 120.0
    prob['DESIGN.balance.BPR']     = 0.65
    prob['DESIGN.balance.FAR_core'] = 0.025
    prob['DESIGN.balance.hpt_PR']  = 2.5506
    prob['DESIGN.balance.lpt_PR']  = 2.5
    prob['DESIGN.mixer.balance.P_tot'] = 55.


def _apply_od_guesses(prob, pt):
    """Set OD initial guesses (shared starting point for both modes)."""
    prob[pt + '.fc.balance.Pt']    = 14.7
    prob[pt + '.fc.balance.Tt']    = 519.
    prob[pt + '.balance.FAR_core'] = 0.025
    prob[pt + '.balance.BPR']      = 0.35
    prob[pt + '.balance.W']        = 100.
    prob[pt + '.balance.HP_Nmech'] = 15000.
    prob[pt + '.balance.LP_Nmech'] = 10000.
    prob[pt + '.mixer.balance.P_tot'] = 55.
    prob[pt + '.hpt.PR']           = 2.523
    prob[pt + '.lpt.PR']           = 2.401
    prob[pt + '.fan.map.RlineMap'] = 2.0
    prob[pt + '.hpc.map.RlineMap'] = 2.0


def setup_dry_problem():
    """Build and return a converged dry (no afterburner) MPCycle problem."""
    prob = om.Problem()
    prob.model = mp = MPMixedFlowTurbofan(afterburn=False)
    prob.setup()

    _apply_design_inputs(prob)

    # Dry mode: afterburner FAR must stay at 0 — enforce initial condition
    prob['DESIGN.afterburner.Fl_I:FAR'] = 0.0

    pt = mp.od_pt
    _apply_od_guesses(prob, pt)
    prob[pt + '.afterburner.Fl_I:FAR'] = 0.0

    # Pre-set OD flight conditions before first run_model() (runs DESIGN + OD together)
    prob.set_val(pt + '.fc.alt', 0.0, units='ft')
    prob.set_val(pt + '.fc.MN', 0.01)
    prob.set_val(pt + '.fc.dTs', 0.0, units='degR')
    prob.set_val(pt + '.balance.rhs:FAR_core', MIL_Tt4, units='degR')

    prob.set_solver_print(level=-1)
    prob.set_solver_print(level=2, depth=1)

    print("=" * 60)
    print("DRY — Running DESIGN point...")
    print("=" * 60)
    prob.run_model()
    page_viewer(prob, 'DESIGN')

    # Verify OD at design conditions
    print("\n" + "=" * 60)
    print("DRY — Verifying OD at design conditions...")
    print("=" * 60)
    prob.set_val(pt + '.fc.alt', 0.0, units='ft')
    prob.set_val(pt + '.fc.MN', 0.01)
    prob.set_val(pt + '.fc.dTs', 0.0, units='degR')
    prob.set_val(pt + '.balance.rhs:FAR_core', MIL_Tt4, units='degR')
    prob.run_model()
    page_viewer(prob, pt)

    return prob, mp


def setup_wet_problem():
    """Build and return a converged wet (afterburning) MPCycle problem."""
    prob = om.Problem()
    prob.model = mp = MPMixedFlowTurbofan(afterburn=True)
    prob.setup()

    _apply_design_inputs(prob)

    # Wet DESIGN: set T7 target and FAR_ab initial guess
    prob.set_val('DESIGN.balance.rhs:FAR_ab', DSN_Tt7, units='degR')
    prob['DESIGN.balance.FAR_ab'] = 0.0375

    pt = mp.od_pt
    _apply_od_guesses(prob, pt)
    prob[pt + '.balance.FAR_ab'] = 0.025

    # Pre-set OD flight conditions and targets before first run_model()
    prob.set_val(pt + '.fc.alt', 0.0, units='ft')
    prob.set_val(pt + '.fc.MN', 0.01)
    prob.set_val(pt + '.fc.dTs', 0.0, units='degR')
    prob.set_val(pt + '.balance.rhs:FAR_core', MIL_Tt4, units='degR')
    # OD T7 target — will be overridden per-iteration during sweep
    prob.set_val(pt + '.balance.rhs:FAR_ab', DSN_Tt7, units='degR')

    prob.set_solver_print(level=-1)
    prob.set_solver_print(level=2, depth=1)

    print("=" * 60)
    print("WET — Running DESIGN point...")
    print("=" * 60)
    prob.run_model()
    page_viewer(prob, 'DESIGN')

    # Verify OD at design conditions
    print("\n" + "=" * 60)
    print("WET — Verifying OD at design conditions...")
    print("=" * 60)
    prob.set_val(pt + '.fc.alt', 0.0, units='ft')
    prob.set_val(pt + '.fc.MN', 0.01)
    prob.set_val(pt + '.fc.dTs', 0.0, units='degR')
    prob.set_val(pt + '.balance.rhs:FAR_core', MIL_Tt4, units='degR')
    prob.set_val(pt + '.balance.rhs:FAR_ab', DSN_Tt7, units='degR')
    prob.run_model()
    page_viewer(prob, pt)

    return prob, mp


if __name__ == "__main__":

    # ── Sweep grid (shared by both modes) ────────────────────────────────────
    alts      = np.arange(0, 45001, 5000)      # 0–45k ft, 5k steps
    dTs_vals  = np.arange(-50, 51, 10)          # ±50 degR delta-ISA
    MACH      = 0.85                            # fixed Mach for this deck

    # Dry: sweep Tt4 from mil (3100) down to part-power (2500)
    dry_powers = [3100., 2900., 2700., 2500.]   # Tt4, degR

    # Wet: sweep T7 from min AB (3200) up to max (3800)
    wet_powers = [3800., 3600., 3400., 3200.]   # Tt7, degR

    st_total = time.time()

    # ── DRY SWEEP ────────────────────────────────────────────────────────────
    prob_dry, mp_dry = setup_dry_problem()
    prob_dry.set_solver_print(level=-1)

    dry_sweep_pts = build_snake_sweep(alts, dTs_vals, dry_powers)
    print(f"\nDry sweep matrix: {len(dry_sweep_pts)} points")

    runner_dry = SweepRunner(
        prob_dry, od_pt=mp_dry.od_pt, mach=MACH,
        afterburn=False,
    )
    df_dry = runner_dry.run_sweep(
        dry_sweep_pts,
        bridge_threshold={'alt': 5000, 'dTs': 30},
        max_bridge_steps=5,
    )
    df_dry['mode'] = 'dry'

    # ── WET SWEEP ────────────────────────────────────────────────────────────
    prob_wet, mp_wet = setup_wet_problem()
    prob_wet.set_solver_print(level=-1)

    wet_sweep_pts = build_snake_sweep(alts, dTs_vals, wet_powers)
    print(f"\nWet sweep matrix: {len(wet_sweep_pts)} points")

    runner_wet = SweepRunner(
        prob_wet, od_pt=mp_wet.od_pt, mach=MACH,
        afterburn=True, mil_Tt4=MIL_Tt4,
    )
    df_wet = runner_wet.run_sweep(
        wet_sweep_pts,
        bridge_threshold={'alt': 5000, 'dTs': 30},
        max_bridge_steps=5,
    )
    df_wet['mode'] = 'wet'

    # ── Combine and save ─────────────────────────────────────────────────────
    df_all = pd.concat([df_dry, df_wet], ignore_index=True)
    outfile = 'cycle_deck_full_envelope.csv'
    df_all.to_csv(outfile, index=False)

    elapsed = time.time() - st_total
    dry_conv  = len(df_dry)
    wet_conv  = len(df_wet)
    print(f"\nSweep complete in {elapsed:.1f}s")
    print(f"  Dry: {dry_conv} / {len(dry_sweep_pts)} converged")
    print(f"  Wet: {wet_conv} / {len(wet_sweep_pts)} converged")
    print(f"  Total rows: {len(df_all)}")
    print(f"Results saved to {outfile}")
