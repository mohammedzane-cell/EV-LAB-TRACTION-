"""A complete Snapshot built from the demo files through the core (for the report and Excel tests)."""

from __future__ import annotations

import datetime as dt
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

from evlab.core import drive, losses, thermal, vehicle
from evlab.core import identification as ident
from evlab.core import optimise as op
from evlab.core import winding as wd
from evlab.io.cycles import load_cycle
from evlab.io.loaders import load_bench_tests, load_load_points, reference_motor
from evlab.io.snapshot import Snapshot, complete

DATA = Path(__file__).resolve().parents[2] / "data"


@lru_cache(maxsize=1)
def demo_snapshot() -> Snapshot:
    bench = load_bench_tests(DATA / "bench_tests_demo.csv")
    rec = ident.TestRecords(dc=bench.dc, t_hot_k=bench.winding_temperature_k, no_load=bench.no_load,
                            locked=bench.locked, pole_pairs=2, v_rated=230.0, f_rated=50.0, p_mech=None)
    ic = ident.compare_methods(rec, "both", points=load_load_points(DATA / "load_points_demo.csv").points,
                               reference=reference_motor(bench.meta), is_demo=True, source="Identification TP3")
    motor = ic.published
    d = drive.DriveSettings(i_max=20.0)
    st = losses.LossSettings(winding_temperature_k=motor.r1_temperature_k)
    env = drive.envelope(motor, d)
    cycle = load_cycle(DATA / "cycle_demo.csv")
    veh0 = vehicle.demo_quadricycle()
    sizing = vehicle.size_vehicle(motor, env, st, veh0, cycle)
    veh = replace(veh0, gear_ratio=sizing.gear_ratio)
    th = thermal.demo_thermal()
    s = complete(Snapshot(group="Groupe test", date=dt.date(2026, 11, 6), motor=motor, drive_settings=d,
                          loss_settings=st, thermal_params=th, winding=wd.Winding(36, 4, 3, 7), identification=ic,
                          envelope=env, vehicle=veh, cycle=cycle, sizing=sizing))
    problem = op.Problem(motor, d, st, veh, cycle, th)
    evals = [op.evaluate(problem, op.Design(g, b, 0.85, k)) for g, b, k in
             ((3.6, 2.0, 1.0), (4.0, 5.0, 0.95), (4.3, 7.0, 1.02), (3.2, 0.0, 1.0))]
    pareto = op.ParetoResult(tuple(op.non_dominated(evals)), op.evaluate(problem, problem.baseline()), (),
                             tuple(evals))
    return replace(s, pareto=pareto)
