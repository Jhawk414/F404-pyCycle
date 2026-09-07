import numpy as np

import openmdao.api as om

import pycycle.api as pyc


class MixedFlowTurbofan(pyc.Cycle):

    def initialize(self):
        self.options.declare('afterburn', default=True, types=bool,
                             desc='True = FAR_ab balance active (wet/AB mode). '
                                  'False = afterburner FAR fixed at 0 (dry mode).')
        super().initialize()

    def setup(self):
        design = self.options['design']
        afterburn = self.options['afterburn']

        USE_TABULAR = True

        if USE_TABULAR:
            self.options['thermo_method'] = 'TABULAR'
            self.options['thermo_data'] = pyc.AIR_JETA_TAB_SPEC
            FUEL_TYPE = "FAR"
        else:
            self.options['thermo_method'] = 'TABULAR'
            self.options['thermo_data'] = pyc.species_data.janaf
            FUEL_TYPE = "Jet-A(g)"

        self.add_subsystem('fc', pyc.FlightConditions())
        # Inlet Components
        self.add_subsystem('inlet', pyc.Inlet())
        self.add_subsystem('inlet_duct', pyc.Duct())
        # Fan Components - Split here for CFD integration Add a CFDStart Component
        self.add_subsystem('fan', pyc.Compressor(map_data=pyc.AXI5,
                                             map_extrap=True),promotes_inputs=[('Nmech','LP_Nmech')])
        self.add_subsystem('splitter', pyc.Splitter())
        # Core Stream components
        self.add_subsystem('splitter_core_duct', pyc.Duct())
        # self.add_subsystem('lpc', pyc.Compressor(map_data=pyc.LPCMap, map_extrap=True),
        #                                      promotes_inputs=[('Nmech','LP_Nmech')])
        # self.add_subsystem('lpc_duct', pyc.Duct())
        self.add_subsystem('hpc', pyc.Compressor(map_data=pyc.HPCMap,
                                        bleed_names=['cool1'],map_extrap=True),promotes_inputs=[('Nmech','HP_Nmech')])
        self.add_subsystem('bld3', pyc.BleedOut(bleed_names=['cool3']))

        self.add_subsystem('burner', pyc.Combustor(fuel_type=FUEL_TYPE))

        self.add_subsystem('hpt', pyc.Turbine(map_data=pyc.HPTMap,
                                          bleed_names=['cool3'],map_extrap=True),promotes_inputs=[('Nmech','HP_Nmech')])
        self.add_subsystem('hpt_duct', pyc.Duct())
        self.add_subsystem('lpt', pyc.Turbine(map_data=pyc.LPTMap,
                                        bleed_names=['cool1'],map_extrap=True), promotes_inputs=[('Nmech','LP_Nmech')])
        self.add_subsystem('lpt_duct', pyc.Duct())
        # Bypass Components
        self.add_subsystem('bypass_duct', pyc.Duct())
        # Mixer component
        self.add_subsystem('mixer', pyc.Mixer(designed_stream=1))
        self.add_subsystem('mixer_duct', pyc.Duct())
        # Afterburner Components — in dry mode it's just a pipe (Duct), not a
        # Combustor. A Combustor with no fuel addition produces a rank-deficient
        # Jacobian (every output equation collapses to a copy of the input),
        # which crashes the OD linear solve at part-power dry conditions.
        if afterburn:
            self.add_subsystem('afterburner', pyc.Combustor(fuel_type=FUEL_TYPE))
        else:
            self.add_subsystem('afterburner', pyc.Duct())

        # Nozzle
        self.add_subsystem('mixed_nozz', pyc.Nozzle(nozzType='CD', lossCoef='Cfg'))

        # Mechanical components
        self.add_subsystem('lp_shaft', pyc.Shaft(num_ports=2),promotes_inputs=[('Nmech','LP_Nmech')]) #OG: 3
        self.add_subsystem('hp_shaft', pyc.Shaft(num_ports=2),promotes_inputs=[('Nmech','HP_Nmech')])

        # Aggregating component — only one burner in dry mode (no afterburner fuel)
        n_burners = 2 if afterburn else 1
        self.add_subsystem('perf', pyc.Performance(num_nozzles=1, num_burners=n_burners))

        # Connect flow paths
        self.pyc_connect_flow('fc.Fl_O', 'inlet.Fl_I')
        self.pyc_connect_flow('inlet.Fl_O', 'inlet_duct.Fl_I')
        self.pyc_connect_flow('inlet_duct.Fl_O', 'fan.Fl_I')
        self.pyc_connect_flow('fan.Fl_O', 'splitter.Fl_I')
        # Core connections
        self.pyc_connect_flow('splitter.Fl_O1', 'splitter_core_duct.Fl_I') # splitter Fl_O1 goes thru core, Fl_O2 is bypass
        self.pyc_connect_flow('splitter_core_duct.Fl_O', 'hpc.Fl_I') # connect to hpc.Fl_I

        self.pyc_connect_flow('hpc.Fl_O', 'bld3.Fl_I')

        self.pyc_connect_flow('bld3.Fl_O', 'burner.Fl_I')
        self.pyc_connect_flow('burner.Fl_O', 'hpt.Fl_I')

        self.pyc_connect_flow('hpt.Fl_O', 'hpt_duct.Fl_I')
        self.pyc_connect_flow('hpt_duct.Fl_O', 'lpt.Fl_I')
        self.pyc_connect_flow('lpt.Fl_O', 'lpt_duct.Fl_I')
        self.pyc_connect_flow('lpt_duct.Fl_O','mixer.Fl_I1')
        # Bypass Connections
        self.pyc_connect_flow('splitter.Fl_O2', 'bypass_duct.Fl_I') # splitter Fl_O1 goes thru core, Fl_O2 is bypass
        self.pyc_connect_flow('bypass_duct.Fl_O', 'mixer.Fl_I2')

        #Mixer Connections
        self.pyc_connect_flow('mixer.Fl_O', 'mixer_duct.Fl_I')
        # Afterburner
        self.pyc_connect_flow('mixer_duct.Fl_O','afterburner.Fl_I')

        # Nozzle
        self.pyc_connect_flow('afterburner.Fl_O','mixed_nozz.Fl_I')

        # Connect cooling flows
        self.pyc_connect_flow('hpc.cool1', 'lpt.cool1', connect_stat=False)
        self.pyc_connect_flow('bld3.cool3', 'hpt.cool3', connect_stat=False)

        # Make additional model connections
        self.connect('inlet.Fl_O:tot:P', 'perf.Pt2')
        self.connect('hpc.Fl_O:tot:P', 'perf.Pt3')
        self.connect('burner.Wfuel', 'perf.Wfuel_0')
        if afterburn:
            self.connect('afterburner.Wfuel', 'perf.Wfuel_1')
        self.connect('inlet.F_ram', 'perf.ram_drag')
        self.connect('mixed_nozz.Fg', 'perf.Fg_0')

        # Attach Element Torques to Shaft Ports
        self.connect('fan.trq', 'lp_shaft.trq_0')
        #self.connect('lpc.trq', 'lp_shaft.trq_1')
        self.connect('hpc.trq', 'hp_shaft.trq_0')
        self.connect('hpt.trq', 'hp_shaft.trq_1')
        self.connect('lpt.trq', 'lp_shaft.trq_1') #LP spool hot section
        self.connect('fc.Fl_O:stat:P', 'mixed_nozz.Ps_exhaust')

        # Add BALANCE components to close the implicit components
        balance = self.add_subsystem('balance', om.BalanceComp())
        if design:
            balance.add_balance('W', lower=25, upper=200., units='lbm/s', eq_units='lbf') #OG lower = 1e-3
            self.connect('balance.W', 'fc.W')
            self.connect('perf.Fn', 'balance.lhs:W')
            # self.add_subsystem('wDV',IndepVarComp('wDes',100,units='lbm/s'))
            # self.connect('wDV.wDes','fc.W')

            balance.add_balance('BPR', eq_units=None, lower=0.25, upper=0.80, val=0.65)
            self.connect('balance.BPR', 'splitter.BPR')
            self.connect('mixer.ER', 'balance.lhs:BPR')

            balance.add_balance('FAR_core', eq_units='degR', lower=1e-4, val=.017)
            self.connect('balance.FAR_core', 'burner.Fl_I:FAR')
            self.connect('burner.Fl_O:tot:T', 'balance.lhs:FAR_core')

            if afterburn:
                balance.add_balance('FAR_ab', eq_units='degR', lower=1e-4, val=.017)
                self.connect('balance.FAR_ab', 'afterburner.Fl_I:FAR')
                self.connect('afterburner.Fl_O:tot:T', 'balance.lhs:FAR_ab')

            balance.add_balance('hpt_PR', val=2.0, lower=1.001, upper=3.0, eq_units='hp', use_mult=True, mult_val=-1)
            self.connect('balance.hpt_PR', 'hpt.PR')
            self.connect('hp_shaft.pwr_in', 'balance.lhs:hpt_PR')
            self.connect('hp_shaft.pwr_out', 'balance.rhs:hpt_PR')

            balance.add_balance('lpt_PR', val=2.5, lower=1.001, upper=3.5, eq_units='hp', use_mult=True, mult_val=-1)
            self.connect('balance.lpt_PR', 'lpt.PR')
            self.connect('lp_shaft.pwr_in', 'balance.lhs:lpt_PR')
            self.connect('lp_shaft.pwr_out', 'balance.rhs:lpt_PR')

        else:

            balance.add_balance('W', lower=25, upper=200., units='lbm/s', eq_units='inch**2') #OG lower = 1e-3
            self.connect('balance.W', 'fc.W')
            self.connect('mixed_nozz.Throat:stat:area', 'balance.lhs:W')

            balance.add_balance('BPR', lower=0.1, upper=1.0, val=0.34, eq_units='psi')
            self.connect('balance.BPR', 'splitter.BPR')
            self.connect('mixer.Fl_I1_calc:stat:P', 'balance.lhs:BPR')
            self.connect('bypass_duct.Fl_O:stat:P', 'balance.rhs:BPR')

            balance.add_balance('FAR_core', eq_units='degR', lower=1e-4, upper=.06, val=.017)
            self.connect('balance.FAR_core', 'burner.Fl_I:FAR')
            self.connect('burner.Fl_O:tot:T', 'balance.lhs:FAR_core')

            if afterburn:
                balance.add_balance('FAR_ab', eq_units='degR', lower=1e-4, upper=.06, val=.017)
                self.connect('balance.FAR_ab', 'afterburner.Fl_I:FAR')
                self.connect('afterburner.Fl_O:tot:T', 'balance.lhs:FAR_ab')

            balance.add_balance('LP_Nmech', val=1., units='rpm', lower=500., eq_units='hp', use_mult=True, mult_val=-1)
            self.connect('balance.LP_Nmech', 'LP_Nmech')
            self.connect('lp_shaft.pwr_in', 'balance.lhs:LP_Nmech')
            self.connect('lp_shaft.pwr_out', 'balance.rhs:LP_Nmech')

            balance.add_balance('HP_Nmech', val=1., units='rpm', lower=500., eq_units='hp', use_mult=True, mult_val=-1)
            self.connect('balance.HP_Nmech', 'HP_Nmech')
            self.connect('hp_shaft.pwr_in', 'balance.lhs:HP_Nmech')
            self.connect('hp_shaft.pwr_out', 'balance.rhs:HP_Nmech')

        # Off design
        newton = self.nonlinear_solver = om.NewtonSolver()
        newton.options['atol'] = 1e-5 #1e-6
        newton.options['rtol'] = 1e-9 #1e-10
        newton.options['iprint'] = 1 #2
        newton.options['maxiter'] = 50
        newton.options['solve_subsystems'] = True
        newton.options['max_sub_solves'] = 100 #100
        newton.options['reraise_child_analysiserror'] = False
        # Raise AnalysisError when Newton fails to drive residual below atol/rtol
        # within maxiter. Without this, the solver silently returns whatever
        # bound-clipped or stalled state it landed in — and SweepRunner would
        # report it as "converged", producing garbage rows in the cycle deck.
        newton.options['err_on_non_converge'] = True
        # ArmijoGoldsteinLS with maxiter=0 by default — skips the Armijo
        # backtracking loop entirely and behaves like BoundsEnforceLS (fast).
        # SweepRunner toggles maxiter to 3 on per-point failure to enable
        # backtracking as a fallback strategy. This avoids paying Armijo's
        # overhead on the ~95% of points that converge cleanly without it.
        newton.linesearch = om.ArmijoGoldsteinLS(bound_enforcement='scalar')
        newton.linesearch.options['maxiter'] = 0  # SweepRunner bumps to 3 on retry
        newton.linesearch.options['rho'] = 0.5    # halve step on rejection
        newton.linesearch.options['c'] = 0.1      # Armijo sufficient-decrease constant
        newton.linesearch.options['iprint'] = -1  # suppress per-backtrack residual lines


        self.linear_solver = om.DirectSolver(assemble_jac=True)

        super().setup()
