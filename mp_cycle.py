import pycycle.api as pyc

from engine_model import MixedFlowTurbofan


class MPMixedFlowTurbofan(pyc.MPCycle):

    def setup(self):

        # Create design instance of model
        self.pyc_add_pnt('DESIGN', MixedFlowTurbofan(design=True, thermo_method='TABULAR'))

        self.set_input_defaults('DESIGN.balance.rhs:BPR', 0.34, units=None) # defined as 1 over 2 (# 1.05)
        self.set_input_defaults('DESIGN.inlet.MN', 0.751)
        self.set_input_defaults('DESIGN.inlet_duct.MN', 0.4463)
        self.set_input_defaults('DESIGN.fan.MN', 0.4578)
        self.set_input_defaults('DESIGN.splitter.MN1', 0.3104)
        self.set_input_defaults('DESIGN.splitter.MN2', 0.4518)
        self.set_input_defaults('DESIGN.splitter_core_duct.MN', 0.3121)
        # self.set_input_defaults('DESIGN.lpc.MN', 0.3059)
        # self.set_input_defaults('DESIGN.lpc_duct.MN', 0.3563)
        self.set_input_defaults('DESIGN.hpc.MN', 0.2442)
        self.set_input_defaults('DESIGN.bld3.MN', 0.3000)
        self.set_input_defaults('DESIGN.burner.MN', 0.1025)
        self.set_input_defaults('DESIGN.hpt.MN', 0.3650)
        self.set_input_defaults('DESIGN.hpt_duct.MN', 0.3063)
        self.set_input_defaults('DESIGN.lpt.MN', 0.4127)
        self.set_input_defaults('DESIGN.lpt_duct.MN', 0.4463)
        self.set_input_defaults('DESIGN.bypass_duct.MN', 0.4463)
        self.set_input_defaults('DESIGN.mixer_duct.MN', 0.4463)
        self.set_input_defaults('DESIGN.afterburner.MN', 0.1025)
        self.set_input_defaults('DESIGN.LP_Nmech', 10000, units='rpm')
        self.set_input_defaults('DESIGN.HP_Nmech', 14000, units='rpm')

        # Cycle parameters shared across all points
        self.pyc_add_cycle_param('balance.rhs:FAR_ab', 3400 ,units='degR')
        self.pyc_add_cycle_param('hp_shaft.HPX', 250, units='hp')
        self.pyc_add_cycle_param('inlet.ram_recovery', 0.9990)
        self.pyc_add_cycle_param('inlet_duct.dPqP', 0.0107)
        self.pyc_add_cycle_param('splitter_core_duct.dPqP', 0.0048)
        # self.pyc_add_cycle_param('lpc_duct.dPqP', 0.0101)
        #self.pyc_add_cycle_param('burner.dPqP', 0.0540)
        self.pyc_add_cycle_param('hpt_duct.dPqP', 0.0051)
        self.pyc_add_cycle_param('lpt_duct.dPqP', 0.0107)
        self.pyc_add_cycle_param('bypass_duct.dPqP', 0.015) #0.0107
        self.pyc_add_cycle_param('mixer_duct.dPqP', 0.0107)
        #self.pyc_add_cycle_param('afterburner.dPqP', 0.0540)
        #self.pyc_add_cycle_param('mixed_nozz.Cfg', 0.9933)
        self.pyc_add_cycle_param('hpc.cool1:frac_W', 0.050708) #0.050708
        self.pyc_add_cycle_param('hpc.cool1:frac_P', 0.5)
        self.pyc_add_cycle_param('hpc.cool1:frac_work', 0.5)

        self.pyc_add_cycle_param('bld3.cool3:frac_W', 0.11) #0.067214
        self.pyc_add_cycle_param('hpt.cool3:frac_P', 1.0)
        self.pyc_add_cycle_param('lpt.cool1:frac_P', 1.0)

        # Single generic OD point — conditions set by calling script via prob.set_val()
        self.od_pt = 'OD'
        self.pyc_add_pnt(self.od_pt, MixedFlowTurbofan(design=False, thermo_method='TABULAR'))

        # Map scalars: transfer design compressor/turbine map scaling to OD
        self.pyc_connect_des_od('fan.s_PR', 'fan.s_PR')
        self.pyc_connect_des_od('fan.s_Wc', 'fan.s_Wc')
        self.pyc_connect_des_od('fan.s_eff', 'fan.s_eff')
        self.pyc_connect_des_od('fan.s_Nc', 'fan.s_Nc')

        self.pyc_connect_des_od('hpc.s_PR', 'hpc.s_PR')
        self.pyc_connect_des_od('hpc.s_Wc', 'hpc.s_Wc')
        self.pyc_connect_des_od('hpc.s_eff', 'hpc.s_eff')
        self.pyc_connect_des_od('hpc.s_Nc', 'hpc.s_Nc')

        self.pyc_connect_des_od('hpt.s_PR', 'hpt.s_PR')
        self.pyc_connect_des_od('hpt.s_Wp', 'hpt.s_Wp')
        self.pyc_connect_des_od('hpt.s_eff', 'hpt.s_eff')
        self.pyc_connect_des_od('hpt.s_Np', 'hpt.s_Np')

        self.pyc_connect_des_od('lpt.s_PR', 'lpt.s_PR')
        self.pyc_connect_des_od('lpt.s_Wp', 'lpt.s_Wp')
        self.pyc_connect_des_od('lpt.s_eff', 'lpt.s_eff')
        self.pyc_connect_des_od('lpt.s_Np', 'lpt.s_Np')

        # Flow areas: transfer design station areas to OD
        self.pyc_connect_des_od('mixed_nozz.Throat:stat:area', 'balance.rhs:W')
        self.pyc_connect_des_od('inlet.Fl_O:stat:area', 'inlet.area')
        self.pyc_connect_des_od('fan.Fl_O:stat:area', 'fan.area')
        self.pyc_connect_des_od('splitter.Fl_O1:stat:area', 'splitter.area1')
        self.pyc_connect_des_od('splitter.Fl_O2:stat:area', 'splitter.area2')
        self.pyc_connect_des_od('splitter_core_duct.Fl_O:stat:area', 'splitter_core_duct.area')
        # self.pyc_connect_des_od('lpc.Fl_O:stat:area', 'lpc.area')
        # self.pyc_connect_des_od('lpc_duct.Fl_O:stat:area', 'lpc_duct.area')
        self.pyc_connect_des_od('hpc.Fl_O:stat:area', 'hpc.area')
        self.pyc_connect_des_od('bld3.Fl_O:stat:area', 'bld3.area')
        self.pyc_connect_des_od('burner.Fl_O:stat:area', 'burner.area')
        self.pyc_connect_des_od('hpt.Fl_O:stat:area', 'hpt.area')
        self.pyc_connect_des_od('hpt_duct.Fl_O:stat:area', 'hpt_duct.area')
        self.pyc_connect_des_od('lpt.Fl_O:stat:area', 'lpt.area')
        self.pyc_connect_des_od('lpt_duct.Fl_O:stat:area', 'lpt_duct.area')
        self.pyc_connect_des_od('bypass_duct.Fl_O:stat:area', 'bypass_duct.area')
        self.pyc_connect_des_od('mixer.Fl_O:stat:area', 'mixer.area')
        self.pyc_connect_des_od('mixer.Fl_I1_calc:stat:area', 'mixer.Fl_I1_stat_calc.area')
        self.pyc_connect_des_od('mixer_duct.Fl_O:stat:area', 'mixer_duct.area')
        self.pyc_connect_des_od('afterburner.Fl_O:stat:area', 'afterburner.area')

        super().setup()
