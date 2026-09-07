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
import openmdao.api as om
import pandas as pd

log = logging.getLogger(__name__)

# OD BalanceComp bounds — must mirror engine_model.py off-design block.
# Used by SweepRunner._state_at_bounds() to flag bound-clipped solutions
# that Newton would otherwise report as "converged".
_OD_BOUNDS = {
    'balance.W':         (25.,   200.),
    'balance.BPR':       (0.1,   1.0),
    'balance.FAR_core':  (1e-4,  0.06),
    'balance.LP_Nmech':  (500.,  None),  # no upper bound in BalanceComp
    'balance.HP_Nmech':  (500.,  None),
}
_OD_FAR_AB_BOUNDS = (1e-4, 0.06)  # only present when afterburn=True

# Fraction of bound width within which a state is considered saturated.
_BOUND_TOL_FRAC = 0.01

# Burner/afterburner exit temperature must be within this many degR of the
# requested target for the run to count as a real solution.
_TARGET_TOL_DEGR = 5.0


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
        # Snapshot of the most recently converged OD state — used to restore a
        # clean warm-start before retrying a failed point with safe linesearch.
        self._last_good_state = None

    def _od_newton(self):
        """Get the OD subsystem's Newton solver."""
        return self.prob.model._get_subsystem(self.od_pt).nonlinear_solver

    def _set_linesearch_mode(self, mode):
        """Toggle linesearch backtracking on the OD Newton.

        'fast' (maxiter=0): no Armijo backtracking — fast path.
        'safe' (maxiter=3): up to 3 Armijo backtracks — robust fallback for
                            points that fail with the fast linesearch.
        """
        self._od_newton().linesearch.options['maxiter'] = (
            0 if mode == 'fast' else 5
        )

    def _snapshot_state(self):
        """Capture the FULL OD output vector (all implicit Newton states).

        A previous version of this code snapshotted only a dozen named primary
        balance states (W, BPR, FAR_core, etc.).  That's insufficient: pyCycle
        has many nested implicit states inside its sub-components — every
        Nozzle/Mixer has a `staticMN.ps_resid` with an implicit Ps state, every
        compressor/turbine has internal map states, etc.  When Newton failed
        at a cold corner, those sub-Newton states were left at exploded values,
        and a partial restore of just the primary states left the model in an
        inconsistent state that immediately blew up gamma to non-physical
        values on the next run.

        Snapshotting `_outputs.asarray()` captures the entire OD subsystem's
        output vector, which contains every implicit Newton state in one shot.
        """
        od_group = self.prob.model._get_subsystem(self.od_pt)
        return od_group._outputs.asarray().copy()

    def _restore_state(self, snap):
        """Restore the full OD output vector captured by _snapshot_state."""
        od_group = self.prob.model._get_subsystem(self.od_pt)
        od_group._outputs.asarray()[:] = snap

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

    def _state_at_bounds(self):
        """Return True if any OD BalanceComp state is at/near its bound.

        Newton can satisfy `_iter_count < maxiter` while the state is clipped
        at a BalanceComp lower/upper bound — producing a residual minimum
        that's not a real solution. Bound saturation is the dead-giveaway.
        """
        pt = self.od_pt
        bounds = dict(_OD_BOUNDS)
        if self.afterburn:
            bounds['balance.FAR_ab'] = _OD_FAR_AB_BOUNDS
        for key, (lo, hi) in bounds.items():
            try:
                val = float(self.prob[f'{pt}.{key}'])
            except Exception:
                continue
            if hi is not None:
                tol = _BOUND_TOL_FRAC * (hi - lo)
                if val > hi - tol or val < lo + tol:
                    return True
            else:
                # Half-bounded — only check the lower bound, scale tol off lo.
                if val < lo * (1.0 + _BOUND_TOL_FRAC):
                    return True
        return False

    def _target_met(self, power):
        """Verify the FAR balances actually drove T4 (and T7, if wet) to target.

        Belt-and-suspenders against false-converged states where Newton
        reports success but the burner/afterburner exit temps are far from
        the requested target — e.g. stalled-LP-spool basins.
        """
        pt = self.od_pt
        try:
            t4 = float(self.prob.get_val(f'{pt}.burner.Fl_O:tot:T', units='degR'))
        except Exception:
            return False
        if self.afterburn:
            if abs(t4 - self.mil_Tt4) > _TARGET_TOL_DEGR:
                return False
            try:
                t7 = float(self.prob.get_val(f'{pt}.afterburner.Fl_O:tot:T',
                                             units='degR'))
            except Exception:
                return False
            return abs(t7 - power) <= _TARGET_TOL_DEGR
        return abs(t4 - power) <= _TARGET_TOL_DEGR

    def _run_bridge(self):
        """Run a bridge point, accepting any forward progress.

        Bridges exist only to warm-start Newton toward the next real sweep
        point — they do not need to converge to their intermediate target.
        Partial progress (e.g. T7 moved from 3800 toward 3766 without fully
        landing on 3766) is still a better warm-start than the previous state.

        Only hard failures (bound saturation / NaN) trigger a state restore;
        an unconverged-but-sane intermediate state is kept.  To allow partial
        convergence without an AnalysisError, err_on_non_converge is
        temporarily disabled for the duration of this run.
        """
        newton = self._od_newton()
        newton.options['err_on_non_converge'] = False
        try:
            self.prob.run_model()
        except Exception:
            return False
        finally:
            newton.options['err_on_non_converge'] = True
        return not self._state_at_bounds()

    def _run_point(self, power=None):
        """Run the model. Return True only if Newton actually converged.

        Three independent checks must pass:
          1. prob.run_model() didn't raise AnalysisError (Newton hit atol/rtol).
          2. No BalanceComp state is clipped at its lower/upper bound.
          3. The burner/AB exit temps match the requested power target.

        `power` may be None — in that case the target check is skipped (used
        when re-verifying state after a bridge restore, where power doesn't
        correspond to the most recently set conditions).
        """
        try:
            self.prob.run_model()
        except om.AnalysisError:
            return False
        if self._state_at_bounds():
            return False
        if power is not None and not self._target_met(power):
            return False
        return True

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
        power_label = "Tt7" if self.afterburn else "Tt4"
        n_total = len(sweep_points)

        for i, pt_cond in enumerate(sweep_points):
            # Check if bridge points are needed
            if prev_pt is not None:
                needs_bridge = any(
                    abs(pt_cond[key] - prev_pt[key]) > bridge_threshold.get(key, float('inf'))
                    for key in ('alt', 'dTs', 'power')
                )
                if needs_bridge:
                    bridges = generate_bridge_points(prev_pt, pt_cond, max_bridge_steps)
                    for j, bp in enumerate(bridges, 1):
                        print(f"  [BRIDGE {j}/{len(bridges)}] alt={bp['alt']:6.0f} ft  "
                              f"dTs={bp['dTs']:+5.1f} R  MN={self.mach:.3f}  "
                              f"{power_label}={bp['power']:6.1f} R")
                        self._set_od_conditions(bp['alt'], bp['dTs'], bp['power'])
                        bridge_ok = self._run_bridge()
                        if not bridge_ok and self._last_good_state is not None:
                            # Hard failure (bound saturation / NaN) — restore
                            # so the next bridge doesn't inherit blown-up state.
                            self._restore_state(self._last_good_state)

            # Run the actual sweep point — fast linesearch first, fall back to
            # safe (Armijo backtracking) only if the fast attempt diverges.
            print(f"  [SWEEP  {i+1:3d}/{n_total}] alt={pt_cond['alt']:6.0f} ft  "
                  f"dTs={pt_cond['dTs']:+5.1f} R  MN={self.mach:.3f}  "
                  f"{power_label}={pt_cond['power']:6.1f} R", end="", flush=True)
            self._set_od_conditions(pt_cond['alt'], pt_cond['dTs'], pt_cond['power'])

            self._set_linesearch_mode('fast')
            converged = self._run_point(power=pt_cond['power'])
            mode_used = 'fast'

            if not converged:
                # Restore last known-good state (Newton may have left NaNs/junk
                # in the state vector) and retry with safe linesearch.
                if self._last_good_state is not None:
                    self._restore_state(self._last_good_state)
                self._set_od_conditions(pt_cond['alt'], pt_cond['dTs'], pt_cond['power'])
                self._set_linesearch_mode('safe')
                converged = self._run_point(power=pt_cond['power'])
                self._set_linesearch_mode('fast')  # restore default for next point
                mode_used = 'safe'

            if converged:
                row = extract_od_results(self.prob, self.od_pt, afterburn=self.afterburn)
                results.append(row)
                self._last_good_state = self._snapshot_state()
                tag = "" if mode_used == 'fast' else " (safe)"
                print(f"  → converged{tag}")
            else:
                # Both attempts failed — restore last-good state so the next
                # sweep point doesn't warm-start from corrupted state and
                # cascade more false convergences.
                if self._last_good_state is not None:
                    self._restore_state(self._last_good_state)
                print("  → FAILED")
                log.warning("Point did not converge: alt=%.0f dTs=%.1f power=%.0f",
                            pt_cond['alt'], pt_cond['dTs'], pt_cond['power'])

            prev_pt = pt_cond

        log.info("Sweep complete: %d / %d points converged",
                 len(results), len(sweep_points))

        return pd.DataFrame(results)
