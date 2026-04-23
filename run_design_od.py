"""
Run the F404 mixed-flow turbofan at its design point (SLS) and a single
off-design point (RTO). This script preserves the original MFTF_od_CRZ.py
behavior for regression testing.
"""
import time

import openmdao.api as om

from mp_cycle import MPMixedFlowTurbofan
from printer import page_viewer


if __name__ == "__main__":

    prob = om.Problem()

    prob.model = mp_mixedflow = MPMixedFlowTurbofan()

    prob.setup()

    # ---- Design point values ----
    prob.set_val('DESIGN.fc.alt', 0.0, units='ft')
    prob.set_val('DESIGN.fc.MN', 0.01)

    prob.set_val('DESIGN.balance.rhs:W', 17700, units='lbf') #Target SLS Thrust
    prob.set_val('DESIGN.balance.rhs:FAR_core', 3100, units='degR') # Target Tt4
    #prob.set_val('DESIGN.balance.rhs:FAR_ab', 3500, units='degR') # Target Tt7

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
    prob['DESIGN.balance.lpt_PR'] = 3.55 #3.5

    prob['DESIGN.mixer.balance.P_tot'] = 20

    # ---- OD point: RTO conditions ----
    pt = mp_mixedflow.od_pt  # 'OD'

    prob.set_val(pt+'.fc.alt', 0.0, units='ft')
    prob.set_val(pt+'.fc.MN', 0.1)
    prob.set_val(pt+'.balance.rhs:FAR_core', 3150, units='degR')

    # OD initial guesses
    prob[pt+'.fc.balance.Pt'] = 14.7 #psia
    prob[pt+'.fc.balance.Tt'] = 519 # degR

    prob[pt+'.balance.FAR_core'] = 0.025
    prob[pt+'.balance.FAR_ab'] = 0.025
    prob[pt+'.balance.BPR'] = 0.35 #2.5
    prob[pt+'.balance.W'] = 100
    prob[pt+'.balance.HP_Nmech'] = 15000
    prob[pt+'.balance.LP_Nmech'] = 10000

    prob[pt+'.mixer.balance.P_tot'] = 18 #OG: 15
    prob[pt+'.hpt.PR'] = 2.523 #
    prob[pt+'.lpt.PR'] = 2.401 #

    prob[pt+'.fan.map.RlineMap'] = 2.0
    prob[pt+'.hpc.map.RlineMap'] = 2.0

    # ---- Run ----
    st = time.time()

    prob.set_solver_print(level=-1)
    prob.set_solver_print(level=2, depth=1)

    prob.run_model()

    for pt_name in ['DESIGN', pt]:
        page_viewer(prob, pt_name)

    print()
    print("time", time.time() - st)
