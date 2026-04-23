"""
Full-envelope cycle deck builder for the F404 mixed-flow turbofan.

Sweeps altitude, delta-ISA, and power level (Tt4) in a snake pattern
with automatic bridge points for convergence stability.

Usage:
    python sweep_full_envelope.py
"""
import logging
import time

import numpy as np
import openmdao.api as om

from mp_cycle import MPMixedFlowTurbofan
from printer import page_viewer
from sweep_utils import build_snake_sweep, SweepRunner

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


def setup_problem():
    """Build the MPCycle problem and run the design point."""

    prob = om.Problem()
    prob.model = mp = MPMixedFlowTurbofan()
    prob.setup()

    # ---- Design point values (SLS) ----
    prob.set_val('DESIGN.fc.alt', 0.0, units='ft')
    prob.set_val('DESIGN.fc.MN', 0.01)

    prob.set_val('DESIGN.balance.rhs:W', 17700, units='lbf')
    prob.set_val('DESIGN.balance.rhs:FAR_core', 3100, units='degR')

    prob.set_val('DESIGN.fan.PR', 4.1)
    prob.set_val('DESIGN.fan.eff', 0.8948)

    prob.set_val('DESIGN.hpc.PR', 6.5)
    prob.set_val('DESIGN.hpc.eff', 0.8707)

    prob.set_val('DESIGN.hpt.eff', 0.8888)
    prob.set_val('DESIGN.lpt.eff', 0.8996)

    # ---- Design initial guesses ----
    prob['DESIGN.fc.balance.Pt'] = 5.3
    prob['DESIGN.fc.balance.Tt'] = 450

    prob['DESIGN.balance.W'] = 120.0
    prob['DESIGN.balance.BPR'] = 0.34

    prob['DESIGN.balance.FAR_core'] = 0.025
    prob['DESIGN.balance.FAR_ab'] = 0.0375

    prob['DESIGN.balance.hpt_PR'] = 2.5506
    prob['DESIGN.balance.lpt_PR'] = 3.55

    prob['DESIGN.mixer.balance.P_tot'] = 20

    # ---- OD initial guesses (close to design for warm-start) ----
    pt = mp.od_pt
    prob[pt+'.fc.balance.Pt'] = 14.7
    prob[pt+'.fc.balance.Tt'] = 519

    prob[pt+'.balance.FAR_core'] = 0.025
    prob[pt+'.balance.FAR_ab'] = 0.025
    prob[pt+'.balance.BPR'] = 0.35
    prob[pt+'.balance.W'] = 100
    prob[pt+'.balance.HP_Nmech'] = 15000
    prob[pt+'.balance.LP_Nmech'] = 10000

    prob[pt+'.mixer.balance.P_tot'] = 18
    prob[pt+'.hpt.PR'] = 2.523
    prob[pt+'.lpt.PR'] = 2.401

    prob[pt+'.fan.map.RlineMap'] = 2.0
    prob[pt+'.hpc.map.RlineMap'] = 2.0

    return prob, mp


if __name__ == "__main__":
    prob, mp = setup_problem()

    prob.set_solver_print(level=-1)
    prob.set_solver_print(level=2, depth=1)

    # ---- Step 1: Run design point ----
    print("=" * 60)
    print("Running DESIGN point...")
    print("=" * 60)
    prob.run_model()
    page_viewer(prob, 'DESIGN')

    # ---- Step 2: Verify OD at design conditions (warm-start handoff) ----
    print("\n" + "=" * 60)
    print("Verifying OD at design conditions...")
    print("=" * 60)
    pt = mp.od_pt
    prob.set_val(pt+'.fc.alt', 0.0, units='ft')
    prob.set_val(pt+'.fc.MN', 0.01)
    prob.set_val(pt+'.fc.dTs', 0.0, units='degR')
    prob.set_val(pt+'.balance.rhs:FAR_core', 3100, units='degR')
    prob.run_model()
    page_viewer(prob, pt)

    # ---- Step 3: Define sweep ranges ----
    # Adjust these ranges to your needs
    alts = np.arange(0, 45001, 5000)          # 0 to 45k ft, 5k steps
    dTs_values = np.arange(-50, 51, 10)        # -50 to +50 degR delta-ISA
    powers = [3100, 2900, 2700, 2500]          # Tt4 values (high → low power)

    # ---- Step 4: Build snake-pattern sweep matrix ----
    sweep_points = build_snake_sweep(alts, dTs_values, powers)
    print(f"\nSweep matrix: {len(sweep_points)} total points")
    print(f"  Altitudes:  {list(alts)}")
    print(f"  Delta-ISA:  {list(dTs_values)}")
    print(f"  Power (Tt4): {powers}")

    # ---- Step 5: Run the sweep ----
    print("\n" + "=" * 60)
    print("Starting sweep...")
    print("=" * 60)

    st = time.time()

    # Suppress per-iteration solver output during sweep
    prob.set_solver_print(level=-1)

    runner = SweepRunner(prob, od_pt=pt, mach=0.01)
    results = runner.run_sweep(
        sweep_points,
        bridge_threshold={'alt': 5000, 'dTs': 30},
        max_bridge_steps=5,
    )

    elapsed = time.time() - st
    print(f"\nSweep finished in {elapsed:.1f}s")
    print(f"Converged: {len(results)} / {len(sweep_points)} points")

    # ---- Step 6: Save results ----
    outfile = 'cycle_deck_full_envelope.csv'
    results.to_csv(outfile, index=False)
    print(f"Results saved to {outfile}")
