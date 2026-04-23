"""
Sweep utilities for F404 cycle deck generation.

Provides:
- build_snake_sweep(): Generates an ordered sweep matrix with snake-pattern traversal
- generate_bridge_points(): Creates intermediate points for smooth solver transitions
- extract_od_results(): Pulls key performance outputs from a converged OD solution
- SweepRunner: Orchestrates the full sweep loop with warm-starting and bridge points
"""
import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


def build_snake_sweep(alts, dTs_values, powers):
    """
    Build an ordered sweep matrix using a snake (boustrophedon) pattern.

    At each altitude, dTs is swept in alternating directions so that
    consecutive points are always neighbors — minimizing jumps that
    can cause Newton solver convergence issues.

    Ordering (outermost → innermost):
        power → altitude → dTs (snake)

    Parameters
    ----------
    alts : array-like
        Altitudes in ft, sorted ascending.
    dTs_values : array-like
        Delta-ISA temperature offsets in degR, sorted ascending.
    powers : array-like
        Power levels (Tt4 in degR), ordered as desired (e.g. high → low).

    Returns
    -------
    list of dict
        Each entry: {'alt': float, 'dTs': float, 'power': float}
        Ordered for minimal inter-point jumps.
    """
    sweep = []
    for power in powers:
        for i, alt in enumerate(alts):
            # Reverse dTs direction on odd altitude indices (snake)
            dTs_ordered = dTs_values if (i % 2 == 0) else dTs_values[::-1]
            for dTs in dTs_ordered:
                sweep.append({'alt': float(alt), 'dTs': float(dTs), 'power': float(power)})
    return sweep


def generate_bridge_points(pt_from, pt_to, n_steps):
    """
    Linearly interpolate bridge points between two sweep conditions.

    Bridge points help the Newton solver transition across large jumps
    in altitude or temperature. Their results are discarded — they exist
    solely to provide a warm-start path.

    Parameters
    ----------
    pt_from : dict
        Starting point {'alt', 'dTs', 'power'}.
    pt_to : dict
        Target point {'alt', 'dTs', 'power'}.
    n_steps : int
        Number of intermediate steps (not including from/to).

    Returns
    -------
    list of dict
        Intermediate points, excluding pt_from and pt_to.
    """
    bridges = []
    for k in range(1, n_steps + 1):
        frac = k / (n_steps + 1)
        bridges.append({
            'alt': pt_from['alt'] + frac * (pt_to['alt'] - pt_from['alt']),
            'dTs': pt_from['dTs'] + frac * (pt_to['dTs'] - pt_from['dTs']),
            'power': pt_from['power'] + frac * (pt_to['power'] - pt_from['power']),
        })
    return bridges


def extract_od_results(prob, pt, afterburn=True):
    """
    Extract key performance parameters from a converged OD solution.

    Parameters
    ----------
    prob : openmdao.api.Problem
        The solved problem.
    pt : str
        Point name (e.g. 'OD').
    afterburn : bool
        True if the problem was built with afterburn=True (FAR_ab balance exists).
        False for dry mode — FAR_ab is reported as 0.0.

    Returns
    -------
    dict
        Performance results.
    """
    return {
        'alt':       float(prob.get_val(f'{pt}.fc.alt', units='ft')),
        'dTs':       float(prob.get_val(f'{pt}.fc.dTs', units='degR')),
        'MN':        float(prob.get_val(f'{pt}.fc.MN')),
        'Fn':        float(prob.get_val(f'{pt}.perf.Fn', units='lbf')),
        'Fg':        float(prob.get_val(f'{pt}.perf.Fg', units='lbf')),
        'TSFC':      float(prob.get_val(f'{pt}.perf.TSFC')),
        'W':         float(prob.get_val(f'{pt}.balance.W', units='lbm/s')),
        'BPR':       float(prob.get_val(f'{pt}.balance.BPR')),
        'FAR_core':  float(prob.get_val(f'{pt}.balance.FAR_core')),
        'FAR_ab':    float(prob.get_val(f'{pt}.balance.FAR_ab')) if afterburn else 0.0,
        'OPR':       float(prob[f'{pt}.fan.PR'] * prob[f'{pt}.hpc.PR']),
        'fan_PR':    float(prob[f'{pt}.fan.PR']),
        'hpc_PR':    float(prob[f'{pt}.hpc.PR']),
        'hpt_PR':    float(prob[f'{pt}.hpt.PR']),
        'lpt_PR':    float(prob[f'{pt}.lpt.PR']),
        'T4':        float(prob.get_val(f'{pt}.burner.Fl_O:tot:T', units='degR')),
        'T7':        float(prob.get_val(f'{pt}.afterburner.Fl_O:tot:T', units='degR')),
        'LP_Nmech':  float(prob.get_val(f'{pt}.balance.LP_Nmech', units='rpm')),
        'HP_Nmech':  float(prob.get_val(f'{pt}.balance.HP_Nmech', units='rpm')),
    }


class SweepRunner:
    """
    Runs a sequential OD sweep on a configured, design-converged problem.

    The solver state from the previous point carries over to the next
    (warm-starting). When the jump between consecutive points exceeds
    a threshold, bridge points are automatically inserted and discarded.

    Parameters
    ----------
    prob : openmdao.api.Problem
        Problem with DESIGN already converged via prob.run_model().
    od_pt : str
        Name of the OD point in the model (default 'OD').
    mach : float
        Mach number to use for all sweep points.
    afterburn : bool
        True = wet mode: 'power' in sweep points is T7 (degR); Tt4 is fixed at mil_Tt4.
        False = dry mode: 'power' in sweep points is Tt4 (degR); afterburner is off.
    mil_Tt4 : float
        Core burner exit temp (degR) held fixed during a wet sweep (mil power).
        Ignored in dry mode.
    """

    def __init__(self, prob, od_pt='OD', mach=0.01, afterburn=True, mil_Tt4=3100.):
        self.prob = prob
        self.od_pt = od_pt
        self.mach = mach
        self.afterburn = afterburn
        self.mil_Tt4 = mil_Tt4

    def _set_od_conditions(self, alt, dTs, power):
        """Set flight conditions and power level on the OD point.

        In dry mode, 'power' is the Tt4 target (degR).
        In wet mode, 'power' is the T7 (Tt7) target (degR); Tt4 is fixed at mil_Tt4.
        """
        pt = self.od_pt
        self.prob.set_val(f'{pt}.fc.alt', alt, units='ft')
        self.prob.set_val(f'{pt}.fc.dTs', dTs, units='degR')
        self.prob.set_val(f'{pt}.fc.MN', self.mach)
        if self.afterburn:
            self.prob.set_val(f'{pt}.balance.rhs:FAR_core', self.mil_Tt4, units='degR')
            self.prob.set_val(f'{pt}.balance.rhs:FAR_ab', power, units='degR')
        else:
            self.prob.set_val(f'{pt}.balance.rhs:FAR_core', power, units='degR')

    def _run_point(self):
        """Run the model and return True if converged."""
        self.prob.run_model()
        # Check Newton solver convergence via the OD subsystem
        od_sys = self.prob.model._get_subsystem(self.od_pt)
        solver = od_sys.nonlinear_solver
        return solver.iter_count < solver.options['maxiter']

    def run_sweep(self, sweep_points, bridge_threshold=None, max_bridge_steps=5):
        """
        Execute the sweep, collecting results for each real (non-bridge) point.

        Parameters
        ----------
        sweep_points : list of dict
            Ordered sweep points from build_snake_sweep().
            Each dict has keys: 'alt', 'dTs', 'power'.
        bridge_threshold : dict, optional
            Max allowed jump per variable before bridge points are inserted.
            Example: {'alt': 5000, 'dTs': 30}
            Defaults to {'alt': 5000, 'dTs': 30} if not provided.
        max_bridge_steps : int
            Number of intermediate bridge points when threshold is exceeded.

        Returns
        -------
        pandas.DataFrame
            One row per converged sweep point with performance columns.
        """
        if bridge_threshold is None:
            bridge_threshold = {'alt': 5000, 'dTs': 30}

        results = []
        prev_pt = None

        for i, pt_cond in enumerate(sweep_points):
            # Check if bridge points are needed
            if prev_pt is not None:
                needs_bridge = any(
                    abs(pt_cond[key] - prev_pt[key]) > bridge_threshold.get(key, float('inf'))
                    for key in ('alt', 'dTs', 'power')
                )
                if needs_bridge:
                    bridges = generate_bridge_points(prev_pt, pt_cond, max_bridge_steps)
                    for bp in bridges:
                        self._set_od_conditions(bp['alt'], bp['dTs'], bp['power'])
                        self._run_point()  # discard result
                        log.debug("Bridge point: alt=%.0f dTs=%.1f power=%.0f",
                                  bp['alt'], bp['dTs'], bp['power'])

            # Run the actual sweep point
            self._set_od_conditions(pt_cond['alt'], pt_cond['dTs'], pt_cond['power'])
            converged = self._run_point()

            if converged:
                row = extract_od_results(self.prob, self.od_pt, afterburn=self.afterburn)
                results.append(row)
            else:
                log.warning("Point did not converge: alt=%.0f dTs=%.1f power=%.0f",
                            pt_cond['alt'], pt_cond['dTs'], pt_cond['power'])

            prev_pt = pt_cond

            if (i + 1) % 25 == 0:
                log.info("Sweep progress: %d / %d points", i + 1, len(sweep_points))

        log.info("Sweep complete: %d / %d points converged",
                 len(results), len(sweep_points))

        return pd.DataFrame(results)
