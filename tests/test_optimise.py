import math
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from evlab.core import drive, losses, thermal, vehicle
from evlab.core import optimise as op
from evlab.core.session import td5_ex1
from evlab.io.cycles import load_cycle

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="module")
def problem():
    m = replace(td5_ex1(), r1=0.5, p_mech=60.0, r1_temperature_k=348.15, is_demo=True)
    return op.Problem(m, drive.DriveSettings(i_max=20.0), losses.LossSettings(winding_temperature_k=348.15),
                      vehicle.demo_quadricycle(gear_ratio=3.53), load_cycle(DATA / "cycle_demo.csv"),
                      thermal.demo_thermal())


def test_rewinding_scales_every_impedance(problem):
    m = problem.motor
    r = op.rewound(m, 1.2)
    for n in ("r1", "r2p", "x_leak", "x_m", "r_fe"):
        assert getattr(r, n) == pytest.approx(1.44 * getattr(m, n))
    assert r.v_phase == m.v_phase and r.p_mech == m.p_mech
    assert op.rewound(m, 1.0) == m


def test_evaluation_uses_the_tested_models(problem):
    d = op.Design(3.53, 0.0, 0.8, 1.0)
    e = op.evaluate(problem, d)
    m = problem.motor
    dset = replace(problem.drive, n_points=op.ENVELOPE_POINTS)
    env = drive.envelope(m, dset)
    t, w = losses.default_grid(m, env, problem.loss_settings, *op.MAP_GRID)
    emap = losses.efficiency_map(m, t, w, dset, problem.loss_settings, envelope=env)
    res = vehicle.simulate(problem.cycle, problem.vehicle, m, env, emap, problem.loss_settings)
    assert e.wh_per_km == pytest.approx(res.summary.wh_per_km, rel=1e-12)
    assert e.t_0_50 == pytest.approx(vehicle.acceleration_time(problem.vehicle, m, env, problem.loss_settings,
                                                                50 / 3.6), rel=1e-12)
    assert e.feasible and e.violation == 0 and e.message == "ok"
    assert e.t_winding_max <= problem.t_winding_limit
    assert problem.t_winding_limit == pytest.approx(155 + 273.15 - 20)


def test_one_evaluation_is_fast(problem):
    times = []
    for k in range(3):
        op._motor_side.cache_clear()
        t0 = time.perf_counter()
        op.evaluate(problem, op.Design(3.5, 1.0 + k, 0.85, 1.0 + 0.02 * k))
        times.append(time.perf_counter() - t0)
    assert np.median(times) < 0.2, times


def test_infeasible_designs_are_flagged(problem):
    long_gear = op.evaluate(problem, op.Design(5.0, 0.0, 0.8, 1.0))
    assert not long_gear.feasible and "outside the envelope" in long_gear.message
    assert long_gear.score("wh_per_km") > op.PENALTY
    too_few_turns = op.evaluate(problem, op.Design(3.5, 0.0, 0.8, 0.4))  # I0 ∝ 1/k_n² exceeds 20 A
    assert not too_few_turns.feasible and "no-load current" in too_few_turns.message


# --- one variable: differential evolution = brute force -----------------------------

def test_gear_only_matches_brute_force(problem):
    bounds = op.Bounds(gear_ratio=(2.5, 4.5))
    res = op.optimise(problem, bounds, seed=1, popsize=15, maxiter=20, workers=1)
    sweep = [op.evaluate(problem, op.Design(g, 0.0, 0.8, 1.0)) for g in np.linspace(2.5, 4.5, 201)]
    best = min((e for e in sweep if e.feasible), key=lambda e: e.wh_per_km)
    assert res.best.feasible
    assert res.best.wh_per_km == pytest.approx(best.wh_per_km, rel=0.01)
    assert res.best.design.gear_ratio == pytest.approx(best.design.gear_ratio, rel=0.01)


# --- full problem -----------------------------------------------------------------

BOUNDS = op.Bounds(gear_ratio=(2.5, 4.5), boost=(0.0, 8.0), margin=(0.6, 0.95), k_n=(0.85, 1.2))


def test_optimum_satisfies_every_constraint(problem):
    res = op.optimise(problem, BOUNDS, seed=3, popsize=4, maxiter=4, workers=1)
    again = op.evaluate(problem, res.best.design)
    assert again.feasible
    assert again.min_margin >= 1.0
    assert again.t_winding_max <= problem.t_winding_limit
    assert again.i_cycle_max <= problem.drive.i_max
    assert math.isfinite(again.t_0_50)
    assert len(res.log) == 4 * 4 * (4 + 1)  # every evaluation logged: popsize·n_free·(maxiter + 1)


def test_same_seed_same_result(problem):
    a = op.optimise(problem, BOUNDS, seed=7, popsize=3, maxiter=2, workers=1)
    b = op.optimise(problem, BOUNDS, seed=7, popsize=3, maxiter=2, workers=1)
    assert a.best.design == b.best.design
    assert [e.design for e in a.log] == [e.design for e in b.log]


def test_process_pool_gives_the_same_result(problem):
    serial = op.optimise(problem, BOUNDS, seed=11, popsize=4, maxiter=2, workers=1)
    pooled = op.optimise(problem, BOUNDS, seed=11, popsize=4, maxiter=2, workers=2)
    assert pooled.best.design == serial.best.design
    assert pooled.best.wh_per_km == pytest.approx(serial.best.wh_per_km, rel=1e-12)


def test_eps_constraint(problem):
    eps = 11.9
    res = op.optimise(problem, BOUNDS, eps=eps, seed=5, popsize=4, maxiter=4, workers=1)
    assert res.best.feasible and res.best.t_0_50 <= eps * (1 + 1e-12)


def test_cancel(problem):
    calls = []

    def cancelled():
        calls.append(1)
        return len(calls) > 2

    res = op.optimise(problem, BOUNDS, seed=0, popsize=5, maxiter=20, workers=1, cancelled=cancelled)
    assert res.message == "cancelled"
    assert 0 < len(res.log) < 5 * 4 * 21
    # cancelled from the start: the initial population is still evaluated, the run returns
    early = op.optimise(problem, BOUNDS, seed=0, popsize=3, maxiter=20, workers=1, cancelled=lambda: True)
    assert early.message == "cancelled" and len(early.log) == 3 * 4


def test_pareto_front_and_baseline(problem):
    events = []
    pr = op.pareto_front(problem, BOUNDS, n_points=3, seed=2, popsize=4, workers=1, budget=64,
                         progress=lambda k, n: events.append((k, n)))  # 64 = 4·4·(3 + 1)
    assert len(pr.front) >= 2 and pr.message == "ok"
    t = [p.t_0_50 for p in pr.front]
    w = [p.wh_per_km for p in pr.front]
    assert t == sorted(t) and all(np.diff(w) <= 1e-12)  # faster costs energy along the front
    assert all(p.feasible for p in pr.front)
    b = pr.baseline
    assert b.feasible
    assert any(p.wh_per_km <= b.wh_per_km * (1 + 1e-9) and p.t_0_50 <= b.t_0_50 * (1 + 1e-9) for p in pr.front)
    assert len(pr.runs) == 3 and events and events[-1][1] == len(pr.log)


def test_non_dominated():
    d = op.Design(1, 0, 0.8, 1)
    mk = lambda w, t, ok=True: op.Evaluation(d, w, t, 1.2, 330, 10, 0 if ok else 1, ok, "", 0)
    pts = [mk(80, 12), mk(75, 13), mk(78, 13), mk(70, 14), mk(60, 10, ok=False)]
    front = op.non_dominated(pts)
    assert [(p.wh_per_km, p.t_0_50) for p in front] == [(80, 12), (75, 13), (70, 14)]


def test_gains():
    d = op.Design(1, 0, 0.8, 1)
    base = op.Evaluation(d, 80.0, 12.0, 1.2, 330.0, 15.0, 0, True, "", 0)
    new = op.Evaluation(d, 76.0, 12.6, 1.1, 333.0, 16.5, 0, True, "", 0)
    g = op.gains(base, new)
    assert g["wh_per_km"] == pytest.approx(-5.0) and g["t_0_50"] == pytest.approx(5.0)


def test_bounds_validation():
    with pytest.raises(ValueError):
        op.Bounds(gear_ratio=(4.0, 3.0))
    with pytest.raises(ValueError):
        op.Bounds(gear_ratio=(3.0, 4.0), margin=(0.5, 1.2))
    assert op.Bounds(gear_ratio=(3.0, 4.0)).free() == ["gear_ratio"]
    with pytest.raises(ValueError, match="free"):
        op.optimise(None, op.Bounds(gear_ratio=(3.0, 3.0)))


def test_kpi_changes_temperature_in_kelvin():
    d = op.Design(1, 0, 0.8, 1)
    base = op.Evaluation(d, 80.0, 12.0, 1.2, 334.65, 15.0, 0, True, "", 0)
    new = op.Evaluation(d, 76.0, 12.6, 1.1, 329.65, 16.5, 0, True, "", 0)
    ch = op.kpi_changes(base, new)
    assert ch["t_winding_max"] == (pytest.approx(-5.0), "K")
    assert ch["wh_per_km"] == (pytest.approx(-5.0), "%")


def test_generations_give_a_fixed_budget_per_point():
    for n_free in (1, 2, 3, 4):
        g = op.generations(op.BUDGET, 15, n_free)
        assert abs(op.run_evaluations(15, n_free, g) - 1500) <= 15 * n_free / 2  # ≈ 1500 for any n_free
    assert op.generations(1500, 15, 4) == 24 and op.run_evaluations(15, 4, 24) == 1500
    assert op.generations(10, 15, 4) == 1  # at least one generation
    with pytest.raises(ValueError, match="budget"):
        op.generations(0, 15, 4)
    with pytest.raises(ValueError, match="n_free"):
        op.generations(1500, 15, 0)


def test_budget_is_spent_whatever_the_free_variables(problem):
    """Same budget per Pareto point with 1 or 2 free variables; no early stop (tol = 0)."""
    one = op.Bounds(gear_ratio=(2.5, 4.5))
    two = op.Bounds(gear_ratio=(2.5, 4.5), margin=(0.6, 0.95))
    assert len(op.optimise(problem, one, seed=0, popsize=5, workers=1, budget=40).log) == 40
    assert len(op.optimise(problem, two, seed=0, popsize=5, workers=1, budget=40).log) == 40
    pr = op.pareto_front(problem, one, n_points=2, seed=0, popsize=5, workers=1, budget=40)
    assert [len(r.log) for r in pr.runs] == [40, 40]
