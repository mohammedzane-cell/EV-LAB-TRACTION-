"""Design optimisation of the drive and the vehicle on the tested models (stage 8, tab 7).

No new physics: every evaluation chains core.drive (envelope), core.losses
(40 × 30 map), core.vehicle (cycle energy, sizing margin, 0–50 km/h) and
core.thermal (winding temperature over N cycles) on a design:
  gear_ratio G, boost (V/f low-speed voltage, V), margin (usable fraction of the
  breakdown torque), k_n (rewinding: turns × k_n with the same copper area, so
  R1, R'2, Rf, Xm and X all scale by k_n²; rated voltage, inverter current limit
  and f_max fixed).
Objectives: Wh/km on the selected cycle and the 0–50 km/h time (both minimised).
Constraints: every cycle point inside the envelope (worst torque margin ≥ 1),
winding T max ≤ class limit − 20 K, stator current ≤ inverter limit, 50 km/h reachable.

Method: scipy.optimize.differential_evolution (seeded, deferred updating, worker
pool). Constraints by a feasibility-first penalty: an infeasible design scores
PENALTY + its normalised violation, so any feasible design beats any infeasible
one. The Pareto front is traced by an ε-constraint sweep: minimise Wh/km subject
to t_0–50 ≤ ε for ε between the two anchors. Every evaluation is logged.
"""

from __future__ import annotations

import math
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field, replace
from functools import lru_cache
from multiprocessing import get_context
from typing import Callable, Sequence

import numpy as np
from scipy.optimize import differential_evolution

from evlab.core import drive, losses, thermal, vehicle
from evlab.core.session import MotorParams

VARIABLES = ("gear_ratio", "boost", "margin", "k_n")
PENALTY = 1e6
T_LIMIT_MARGIN_K = 20.0  # winding T max ≤ class limit − 20 K
V_ACCEL = 50.0 / 3.6  # 0–50 km/h, m/s
MAP_GRID = (40, 30)
ENVELOPE_POINTS = 150
BUDGET = 1500  # evaluations per Pareto point (one differential-evolution run)


def generations(budget: int, popsize: int, n_free: int) -> int:
    """maxiter so that one run costs about `budget` evaluations: popsize·n_free·(maxiter + 1) ≈ budget."""
    for name, v in (("budget", budget), ("popsize", popsize), ("n_free", n_free)):
        if not isinstance(v, int) or v < 1:
            raise ValueError(f"{name} must be an integer >= 1, got {v!r}")
    return max(1, round(budget / (popsize * n_free)) - 1)


def run_evaluations(popsize: int, n_free: int, maxiter: int) -> int:
    """Evaluations of one run (fixed: no early stop): popsize·n_free·(maxiter + 1)."""
    return popsize * n_free * (maxiter + 1)


@dataclass(frozen=True)
class Design:
    """A design point: gear ratio G, boost (V), margin (0–1], rewinding factor k_n."""

    gear_ratio: float
    boost: float
    margin: float
    k_n: float

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.gear_ratio, self.boost, self.margin, self.k_n)


@dataclass(frozen=True)
class Problem:
    """Everything an evaluation needs (picklable, hashable parts are cached per process).

    Attributes:
        motor: identified motor (k_n = 1).  drive: inverter limits and baseline V/f law.
        loss_settings: loss model.  vehicle: baseline vehicle.  cycle: selected cycle.
        thermal: network.  insulation_class: A…H.  n_thermal_cycles: cycles back to back.
    """

    motor: MotorParams
    drive: drive.DriveSettings
    loss_settings: losses.LossSettings
    vehicle: vehicle.Vehicle
    cycle: vehicle.Cycle
    thermal: thermal.ThermalParams
    insulation_class: str = "F"
    n_thermal_cycles: int = 10

    @property
    def t_winding_limit(self) -> float:
        """Allowed winding T max, K: class temperature − 20 K."""
        return thermal.INSULATION_CLASSES[self.insulation_class] + thermal.T_ZERO_C - T_LIMIT_MARGIN_K

    def baseline(self) -> Design:
        return Design(self.vehicle.gear_ratio, self.drive.boost, self.drive.margin, 1.0)


def rewound(m: MotorParams, k_n: float) -> MotorParams:
    """Motor with its turns scaled by k_n at the same copper area: every impedance × k_n²."""
    if not math.isfinite(k_n) or k_n <= 0:
        raise ValueError(f"k_n must be > 0, got {k_n!r}")
    k2 = k_n * k_n
    src = m.source if k_n == 1.0 else f"{m.source} · rebobiné k_N = {k_n:.3f}"
    return replace(m, r1=m.r1 * k2, r2p=m.r2p * k2, x_leak=m.x_leak * k2, x_m=m.x_m * k2,
                   r_fe=m.r_fe * k2, source=src)


@dataclass(frozen=True)
class Evaluation:
    """KPIs of one design (inf / NaN where not computable) and its feasibility."""

    design: Design
    wh_per_km: float
    t_0_50: float
    min_margin: float
    t_winding_max: float
    i_cycle_max: float
    violation: float  # normalised sum of constraint violations (0 when feasible), ε excluded
    feasible: bool
    message: str
    elapsed: float

    def score(self, objective: str, eps: float | None = None) -> float:
        """Scalar for the optimiser: objective if feasible (and t_0–50 ≤ ε), else PENALTY + violation."""
        v = self.violation
        if eps is not None and math.isfinite(self.t_0_50):
            v += max(0.0, (self.t_0_50 - eps) / eps)
        elif eps is not None:
            v += 1.0
        if not self.feasible or v > 0:
            return PENALTY + v
        return self.wh_per_km if objective == "wh_per_km" else self.t_0_50


@lru_cache(maxsize=512)
def _motor_side(motor: MotorParams, dsettings: drive.DriveSettings, st: losses.LossSettings):
    """Envelope and coarse loss map of a (rewound) motor under a V/f law — cached per process."""
    env = drive.envelope(motor, dsettings)
    t, w = losses.default_grid(motor, env, st, *MAP_GRID)
    return env, losses.efficiency_map(motor, t, w, dsettings, st, envelope=env)


def evaluate(problem: Problem, design: Design) -> Evaluation:
    """All KPIs and constraints of a design, using only the tested models."""
    t0 = time.perf_counter()
    nan = math.nan
    try:
        m = rewound(problem.motor, design.k_n)
        dset = replace(problem.drive, boost=design.boost, margin=design.margin, n_points=ENVELOPE_POINTS)
        veh = replace(problem.vehicle, gear_ratio=design.gear_ratio)
        env, emap = _motor_side(m, dset, problem.loss_settings)
    except ValueError as exc:  # e.g. no-load current above the inverter limit
        return Evaluation(design, nan, math.inf, nan, nan, nan, 10.0, False, str(exc), time.perf_counter() - t0)
    st = problem.loss_settings
    margin = float(vehicle.torque_margin(problem.cycle, veh, m, env, st, np.array([design.gear_ratio]))[0])
    res = vehicle.simulate(problem.cycle, veh, m, env, emap, st)
    t050 = vehicle.acceleration_time(veh, m, env, st, V_ACCEL)
    moving = res.omega > 0
    i_cycle = float(np.max(np.where(moving, vehicle.LossTable(emap, "i1")(res.torque, res.omega), 0.0)))
    pc, pf = thermal.cycle_losses(res, emap)
    th = thermal.simulate(problem.thermal, pc, pf, n_cycles=problem.n_thermal_cycles,
                          copper_ref_k=thermal.map_copper_temperature(emap, m.r1_temperature_k),
                          insulation_class=problem.insulation_class)
    t_max = th.summary.t_max
    violation = (max(0.0, 1.0 - margin)
                 + max(0.0, (t_max - problem.t_winding_limit) / 10.0)
                 + max(0.0, (i_cycle - problem.drive.i_max) / problem.drive.i_max)
                 + (1.0 if not math.isfinite(t050) else 0.0))
    msgs = []
    if margin < 1:
        msgs.append(f"cycle outside the envelope (margin {margin:.3f})")
    if t_max > problem.t_winding_limit:
        msgs.append(f"winding {t_max - 273.15:.1f} °C above the limit")
    if i_cycle > problem.drive.i_max:
        msgs.append(f"current {i_cycle:.1f} A above the inverter limit")
    if not math.isfinite(t050):
        msgs.append("50 km/h not reachable")
    return Evaluation(design, res.summary.wh_per_km, t050, margin, t_max, i_cycle, violation,
                      violation == 0.0, "; ".join(msgs) or "ok", time.perf_counter() - t0)


@dataclass(frozen=True)
class Bounds:
    """(low, high) for each variable; low == high fixes it."""

    gear_ratio: tuple[float, float]
    boost: tuple[float, float] = (0.0, 0.0)
    margin: tuple[float, float] = (0.8, 0.8)
    k_n: tuple[float, float] = (1.0, 1.0)

    def __post_init__(self) -> None:
        for name in VARIABLES:
            lo, hi = getattr(self, name)
            if not (math.isfinite(lo) and math.isfinite(hi)) or lo > hi:
                raise ValueError(f"bounds of {name} must be finite with low <= high, got {(lo, hi)}")
        if self.gear_ratio[0] <= 0 or self.k_n[0] <= 0:
            raise ValueError("gear_ratio and k_n bounds must be > 0")
        if self.boost[0] < 0 or not 0 < self.margin[0] <= self.margin[1] <= 1:
            raise ValueError("boost must be >= 0 and margin within (0, 1]")

    def free(self) -> list[str]:
        return [n for n in VARIABLES if getattr(self, n)[0] < getattr(self, n)[1]]

    def design(self, x: Sequence[float]) -> Design:
        vals = {n: getattr(self, n)[0] for n in VARIABLES}
        vals.update(dict(zip(self.free(), (float(v) for v in x))))
        return Design(**vals)


class Cancelled(Exception):
    """Raised inside the evaluation map when the user cancels."""


def _evaluate_point(args) -> Evaluation:
    problem, design = args
    return evaluate(problem, design)


class _LoggingMap:
    """Map passed to differential_evolution as `workers`: evaluates designs (serially or in a
    process pool), keeps every Evaluation in the log, returns the scores in order."""

    def __init__(self, problem: Problem, bounds: Bounds, objective: str, eps: float | None,
                 pool: ProcessPoolExecutor | None, log: list[Evaluation],
                 progress: Callable[[int], None] | None, cancelled: Callable[[], bool] | None) -> None:
        self.problem, self.bounds, self.objective, self.eps = problem, bounds, objective, eps
        self.pool, self.log, self.progress, self.cancelled = pool, log, progress, cancelled

    def __call__(self, _func, xs) -> list[float]:
        # cancel between generations, once the initial population is evaluated (never an empty run)
        if self.log and self.cancelled is not None and self.cancelled():
            raise Cancelled()
        designs = [self.bounds.design(x) for x in xs]
        args = [(self.problem, d) for d in designs]
        if self.pool is None:
            records = [_evaluate_point(a) for a in args]
        else:
            records = list(self.pool.map(_evaluate_point, args, chunksize=max(1, len(args) // 16)))
        self.log.extend(records)
        if self.progress is not None:
            self.progress(len(self.log))
        return [r.score(self.objective, self.eps) for r in records]


def _score_only(x) -> float:  # never called: _LoggingMap evaluates the designs itself
    raise RuntimeError("evaluation goes through _LoggingMap")


@dataclass(frozen=True)
class RunResult:
    """One differential-evolution run: best logged evaluation, the log, and how it ended."""

    best: Evaluation
    log: tuple[Evaluation, ...]
    objective: str
    eps: float | None
    message: str


def optimise(problem: Problem, bounds: Bounds, objective: str = "wh_per_km", eps: float | None = None,
             seed: int = 0, popsize: int = 15, maxiter: int = 25, workers: int = -1,
             progress: Callable[[int], None] | None = None, cancelled: Callable[[], bool] | None = None,
             pool: ProcessPoolExecutor | None = None, budget: int | None = None) -> RunResult:
    """Minimise one objective ("wh_per_km" or "t_0_50") over the free variables, optionally with t_0_50 ≤ eps.

    Fixed budget: exactly popsize·n_free·(maxiter + 1) evaluations (tol = 0, no early stop); with
    `budget`, maxiter = generations(budget, popsize, n_free) (≈ budget evaluations). workers = 1 evaluates serially;
    workers = −1 (all cores) or n > 1 uses a process pool (or the given one).
    The result is the best evaluation of the log (feasible if any feasible design was met).
    """
    if objective not in ("wh_per_km", "t_0_50"):
        raise ValueError(f"objective must be 'wh_per_km' or 't_0_50', got {objective!r}")
    free = bounds.free()
    if not free:
        raise ValueError("no free variable: every bound has low == high")
    if budget is not None:
        maxiter = generations(budget, popsize, len(free))
    log: list[Evaluation] = []
    own_pool = None
    if pool is None and workers != 1:
        n = None if workers == -1 else workers
        own_pool = pool = ProcessPoolExecutor(max_workers=n, mp_context=get_context("spawn"))
    mapper = _LoggingMap(problem, bounds, objective, eps, pool, log, progress, cancelled)
    message = "ok"
    try:
        differential_evolution(
            _score_only, [getattr(bounds, n) for n in free], seed=seed, popsize=popsize, maxiter=maxiter,
            tol=0.0, atol=0.0, polish=False, updating="deferred", workers=mapper, init="latinhypercube",
        )
    except Cancelled:
        message = "cancelled"
    finally:
        if own_pool is not None:
            own_pool.shutdown()
    if not log:
        raise ValueError("cancelled before any evaluation")
    best = min(log, key=lambda r: r.score(objective, eps))
    return RunResult(best, tuple(log), objective, eps, message)


def non_dominated(points: Sequence[Evaluation]) -> list[Evaluation]:
    """Feasible points not dominated in (Wh/km, t_0_50), sorted by t_0_50."""
    feas = [p for p in points if p.feasible and math.isfinite(p.t_0_50)]
    out = [p for p in feas if not any(
        (q.wh_per_km <= p.wh_per_km and q.t_0_50 <= p.t_0_50)
        and (q.wh_per_km < p.wh_per_km or q.t_0_50 < p.t_0_50) for q in feas)]
    uniq = {(round(p.wh_per_km, 9), round(p.t_0_50, 9)): p for p in out}
    return sorted(uniq.values(), key=lambda p: p.t_0_50)


@dataclass(frozen=True)
class ParetoResult:
    """Pareto front (sorted by t_0_50), the baseline, every run and the whole evaluation log."""

    front: tuple[Evaluation, ...]
    baseline: Evaluation
    runs: tuple[RunResult, ...]
    log: tuple[Evaluation, ...] = field(repr=False)
    message: str = "ok"


def pareto_front(problem: Problem, bounds: Bounds, n_points: int = 6, seed: int = 0, popsize: int = 15,
                 maxiter: int = 25, workers: int = -1, progress: Callable[[int, int], None] | None = None,
                 cancelled: Callable[[], bool] | None = None, budget: int | None = BUDGET) -> ParetoResult:
    """ε-constraint sweep: anchors min Wh/km and min t_0_50, then min Wh/km with t_0_50 ≤ ε in between.

    Each Pareto point is one run of `budget` evaluations (default 1500, whatever the number of free
    variables); budget=None uses popsize and maxiter as given.

    progress(run index, evaluations so far) is called after each generation.
    """
    if not isinstance(n_points, int) or n_points < 2:
        raise ValueError(f"n_points must be an integer >= 2, got {n_points!r}")
    baseline = evaluate(problem, problem.baseline())
    runs: list[RunResult] = []
    pool = None
    if workers != 1:
        pool = ProcessPoolExecutor(max_workers=None if workers == -1 else workers, mp_context=get_context("spawn"))
    message = "ok"
    try:
        def run(k: int, objective: str, eps: float | None) -> RunResult:
            done = sum(len(r.log) for r in runs)
            cb = None if progress is None else (lambda n: progress(k, done + n))
            r = optimise(problem, bounds, objective, eps, seed=seed + k, popsize=popsize, maxiter=maxiter,
                         workers=workers, progress=cb, cancelled=cancelled, pool=pool, budget=budget)
            runs.append(r)
            return r

        a = run(0, "wh_per_km", None)
        b = run(1, "t_0_50", None) if a.message == "ok" else None
        if b is not None and b.message == "ok" and a.best.feasible and b.best.feasible:
            t_lo, t_hi = b.best.t_0_50, a.best.t_0_50
            for k, eps in enumerate(np.linspace(t_lo, t_hi, n_points)[1:-1], start=2):
                if run(k, "wh_per_km", float(eps)).message != "ok":
                    break
        if any(r.message != "ok" for r in runs):
            message = "cancelled"
    finally:
        if pool is not None:
            pool.shutdown()
    log = tuple(e for r in runs for e in r.log)
    front = non_dominated([r.best for r in runs] + list(log))
    return ParetoResult(tuple(front), baseline, tuple(runs), log, message)


def kpi_changes(baseline: Evaluation, design: Evaluation) -> dict[str, tuple[float, str]]:
    """Change of each KPI, design vs baseline: (value, "%") for ratios, (ΔT, "K") for the temperature.

    A percentage of an absolute temperature would be meaningless, so T max is compared in kelvin.
    """
    out = {k: (v, "%") for k, v in gains(baseline, design).items()}
    b, d = baseline.t_winding_max, design.t_winding_max
    out["t_winding_max"] = ((d - b) if math.isfinite(b) and math.isfinite(d) else math.nan, "K")
    return out


def gains(baseline: Evaluation, design: Evaluation) -> dict[str, float]:
    """Relative change in % of each KPI, design vs baseline (negative = lower)."""
    out = {}
    for k in ("wh_per_km", "t_0_50", "t_winding_max", "min_margin", "i_cycle_max"):
        b, d = getattr(baseline, k), getattr(design, k)
        out[k] = 100.0 * (d - b) / b if b and math.isfinite(b) and math.isfinite(d) else math.nan
    return out
