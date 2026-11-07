import math
from dataclasses import replace

import numpy as np
import pytest

from evlab.core import drive, losses, vehicle
from evlab.core.session import td5_ex1
from evlab.core.vehicle import Cycle
from evlab.io.cycles import load_cycle
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
DRIVE = drive.DriveSettings(i_max=20.0)
LOSS = losses.LossSettings()
KMH = 1 / 3.6


@pytest.fixture(scope="module")
def motor():
    return replace(td5_ex1(), r1=0.5, p_mech=60.0, r1_temperature_k=348.15, is_demo=True)


@pytest.fixture(scope="module")
def env(motor):
    return drive.envelope(motor, DRIVE)


@pytest.fixture(scope="module")
def emap(motor, env):
    t, w = losses.default_grid(motor, env, LOSS, 80, 60)
    return losses.efficiency_map(motor, t, w, DRIVE, LOSS, envelope=env)


@pytest.fixture(scope="module")
def demo_cycle():
    return load_cycle(DATA / "cycle_demo.csv")


# --- road load ------------------------------------------------------------------

def test_road_force_terms():
    veh = vehicle.demo_quadricycle(gear_ratio=4.0)
    v, a, th = 10.0, 0.5, math.radians(3)
    f = vehicle.road_force(veh, v, a, th)
    exp = (veh.mass * a + 0.5 * vehicle.RHO_AIR * veh.cx_s * v**2
           + veh.crr * veh.mass * vehicle.G_EARTH * math.cos(th) + veh.mass * vehicle.G_EARTH * math.sin(th))
    assert f == pytest.approx(exp)
    assert vehicle.road_force(veh, 0.0, 0.0, 0.0) == 0.0  # held at standstill


def test_motor_torque_and_speed():
    veh = vehicle.demo_quadricycle(gear_ratio=4.0)
    assert vehicle.motor_speed(veh, 10.0) == pytest.approx(4.0 * 10.0 / veh.wheel_radius)
    t_trac = vehicle.motor_torque(veh, 500.0)
    t_brake = vehicle.motor_torque(veh, -500.0)
    assert t_trac == pytest.approx(500 * veh.wheel_radius / (4.0 * veh.gear_efficiency))
    assert t_brake == pytest.approx(-500 * veh.wheel_radius * veh.gear_efficiency / 4.0)


# --- sizing ---------------------------------------------------------------------

@pytest.mark.parametrize("pmr, cls", [(10.0, 1), (22.0, 1), (22.01, 2), (34.0, 2), (34.5, 3), (120.0, 3)])
def test_wltc_class(pmr, cls):
    assert vehicle.wltc_class(pmr) == cls


def test_sizing_demo_quadricycle(motor, env, demo_cycle):
    veh = vehicle.demo_quadricycle()
    s = vehicle.size_vehicle(motor, env, LOSS, veh, demo_cycle)
    p_rated = float(np.max(losses.shaft_torque_limit(motor, env, LOSS) * env.omega))
    assert s.rated_power == pytest.approx(p_rated)
    assert s.pmr == pytest.approx(p_rated / veh.mass)
    assert s.wltc_class == vehicle.wltc_class(s.pmr) == 1
    v_max = vehicle.cycle_stats(demo_cycle).v_max
    assert s.gear_ratio_max == pytest.approx(vehicle.SPEED_MARGIN * veh.wheel_radius * env.omega_max / v_max)
    assert s.gear_ratio <= s.gear_ratio_max  # the top speed sits inside the envelope
    assert s.feasible and s.min_margin >= 1.0


def _hard_cycle():
    """0 → 60 km/h at a steady 0,7 m/s², cruise, stop: hard acceleration at high speed."""
    v_top = 60 * KMH
    up = np.arange(0.0, v_top, 0.7)
    v = np.concatenate([[0.0] * 5, up, [v_top] * 20, np.linspace(v_top, 0, 20), [0.0] * 5])
    return Cycle(t=np.arange(float(v.size)), v=v, name="dure", is_demo=True)


def test_top_speed_ratio_alone_is_not_enough(motor, env, emap):
    """At G_max, hard accelerations near top speed land where the torque falls ~Ω^-1.7."""
    cyc = _hard_cycle()
    veh = vehicle.demo_quadricycle()
    s = vehicle.size_vehicle(motor, env, LOSS, veh, cyc)
    at_max = vehicle.simulate(cyc, replace(veh, gear_ratio=s.gear_ratio_max), motor, env, emap, LOSS)
    at_best = vehicle.simulate(cyc, replace(veh, gear_ratio=s.gear_ratio), motor, env, emap, LOSS)
    assert at_max.summary.n_outside > 0
    assert s.gear_ratio < s.gear_ratio_max
    assert at_best.summary.n_outside < at_max.summary.n_outside
    assert at_best.summary.n_outside == 0 if s.feasible else at_best.summary.n_outside > 0


def test_proposed_ratio_keeps_every_point_inside(motor, env, emap, demo_cycle):
    veh = vehicle.demo_quadricycle()
    s = vehicle.size_vehicle(motor, env, LOSS, veh, demo_cycle)
    res = vehicle.simulate(demo_cycle, replace(veh, gear_ratio=s.gear_ratio), motor, env, emap, LOSS)
    assert res.summary.n_outside == 0
    assert np.all(res.omega <= env.omega_max)


WLTC1 = DATA / "wltc_class1.csv"


@pytest.mark.skipif(not WLTC1.exists(), reason="data/wltc_class1.csv not provided yet")
def test_proposed_ratio_on_wltc_class1(motor, env, emap):
    cyc = load_cycle(WLTC1)
    veh = vehicle.demo_quadricycle()
    s = vehicle.size_vehicle(motor, env, LOSS, veh, cyc)
    assert s.wltc_class == 1
    res = vehicle.simulate(cyc, replace(veh, gear_ratio=s.gear_ratio), motor, env, emap, LOSS)
    assert res.summary.n_outside == 0


def test_too_long_gear_is_flagged(motor, env, emap, demo_cycle):
    veh = vehicle.demo_quadricycle(gear_ratio=8.0)  # top speed beyond the envelope
    res = vehicle.simulate(demo_cycle, veh, motor, env, emap, LOSS)
    assert res.summary.n_outside > 0
    assert res.outside.sum() == res.summary.n_outside


# --- energy ---------------------------------------------------------------------

def test_constant_speed_flat_road_matches_analytical(motor, env, emap):
    veh = vehicle.demo_quadricycle(gear_ratio=4.0)
    v = 40 * KMH
    cyc = Cycle(t=np.arange(0.0, 601.0), v=np.full(601, v), name="constant", is_demo=True)
    res = vehicle.simulate(cyc, veh, motor, env, emap, LOSS)
    f = 0.5 * vehicle.RHO_AIR * veh.cx_s * v**2 + veh.crr * veh.mass * vehicle.G_EARTH
    t_m = f * veh.wheel_radius / (veh.gear_ratio * veh.gear_efficiency)
    w_m = veh.gear_ratio * v / veh.wheel_radius
    exact = losses.efficiency_map(motor, np.array([t_m]), np.array([w_m]), DRIVE, LOSS, envelope=env)
    p_loss = float(exact.p_in[0, 0] - exact.p_out[0, 0])  # motor + inverter losses at that point
    analytical = (f * v / veh.gear_efficiency + p_loss + veh.aux_power) * 600.0
    assert res.summary.energy_j == pytest.approx(analytical, rel=0.005)


@pytest.mark.parametrize("regen", [True, False])
def test_energy_balance_closes(motor, env, emap, demo_cycle, regen):
    veh = vehicle.demo_quadricycle(gear_ratio=4.0, regen=regen)
    res = vehicle.simulate(demo_cycle, veh, motor, env, emap, LOSS)
    b = res.balance
    lhs = b["battery"]
    rhs = b["kinetic"] + b["aero"] + b["rolling"] + b["grade"] + b["gear"] + b["friction_brake"] \
        + b["motor_inverter"] + b["auxiliaries"]
    assert abs(lhs - rhs) / abs(lhs) < 1e-6
    assert b["kinetic"] == pytest.approx(0.0, abs=1e-6 * abs(lhs))  # cycle starts and ends at rest


def test_no_regen_when_off(motor, env, emap, demo_cycle):
    off = vehicle.simulate(demo_cycle, vehicle.demo_quadricycle(gear_ratio=4.0, regen=False), motor, env, emap, LOSS)
    on = vehicle.simulate(demo_cycle, vehicle.demo_quadricycle(gear_ratio=4.0, regen=True), motor, env, emap, LOSS)
    assert np.all(off.p_battery >= 0)
    assert np.all(off.torque >= 0)
    assert off.summary.regen_percent == 0.0
    assert on.summary.regen_percent > 0
    assert on.summary.energy_j < off.summary.energy_j
    assert np.any(on.p_battery < 0)


def test_regen_torque_capped_by_envelope(motor, env, emap, demo_cycle):
    veh = vehicle.demo_quadricycle(gear_ratio=4.0, regen=True)
    res = vehicle.simulate(demo_cycle, veh, motor, env, emap, LOSS)
    lim = np.interp(res.omega, env.omega, losses.shaft_torque_limit(motor, env, LOSS))
    assert np.all(res.torque >= -lim - 1e-9)


def test_summary(motor, env, emap, demo_cycle):
    res = vehicle.simulate(demo_cycle, vehicle.demo_quadricycle(gear_ratio=4.0), motor, env, emap, LOSS)
    s = res.summary
    assert s.distance_m == pytest.approx(vehicle.cycle_stats(demo_cycle).distance)
    assert s.wh_per_km == pytest.approx(s.energy_j / 3600 / (s.distance_m / 1000))
    assert s.regen_percent == pytest.approx(100 * s.energy_regen_j / s.energy_traction_j)
    assert s.energy_j == pytest.approx(s.energy_traction_j - s.energy_regen_j)
    assert 30 < s.wh_per_km < 300  # quadricycle, sanity only


def test_validation():
    with pytest.raises(ValueError, match="mass"):
        vehicle.Vehicle(mass=0.0, cx_s=0.6, crr=0.012, wheel_radius=0.27, gear_ratio=4.0)
    with pytest.raises(ValueError, match="gear_efficiency"):
        vehicle.Vehicle(mass=600, cx_s=0.6, crr=0.012, wheel_radius=0.27, gear_ratio=4.0, gear_efficiency=1.2)
    with pytest.raises(ValueError, match="increasing"):
        Cycle(t=np.array([0.0, 0.0]), v=np.array([0.0, 1.0]), name="x", is_demo=False)
    with pytest.raises(ValueError, match="pmr"):
        vehicle.wltc_class(-1.0)


# --- acceleration ---------------------------------------------------------------

def test_acceleration_time_constant_force(motor, env):
    """Without drag, t = ∫ m dv / (F(v) − F_roll) lies between m·v/(F_max − F_roll) and m·v/(F_min − F_roll)."""
    veh = replace(vehicle.demo_quadricycle(gear_ratio=3.5), cx_s=1e-9)
    v = 20 * KMH
    w_end = veh.gear_ratio * v / veh.wheel_radius
    assert w_end < env.base_speed  # constant-torque zone
    lim = losses.shaft_torque_limit(motor, env, LOSS)
    sel = env.omega <= w_end
    t = vehicle.acceleration_time(veh, motor, env, LOSS, v)
    f_roll = veh.crr * veh.mass * vehicle.G_EARTH
    # bounds from the min and max torque over the speed range
    f_lo = lim[sel].min() * veh.gear_ratio * veh.gear_efficiency / veh.wheel_radius - f_roll
    f_hi = lim[sel].max() * veh.gear_ratio * veh.gear_efficiency / veh.wheel_radius - f_roll
    assert veh.mass * v / f_hi <= t <= veh.mass * v / f_lo
    # and the quadrature converges
    assert vehicle.acceleration_time(veh, motor, env, LOSS, v, n=4000) == pytest.approx(t, rel=1e-3)


def test_acceleration_time_unreachable(motor, env):
    veh = vehicle.demo_quadricycle(gear_ratio=12.0)  # top speed below 50 km/h
    assert vehicle.acceleration_time(veh, motor, env, LOSS, 50 * KMH) == math.inf


def test_torque_margin(motor, env, emap, demo_cycle):
    """T_limit/T_demand over the traction points: ≥ 1 ⇔ the cycle stays inside the envelope."""
    veh = vehicle.demo_quadricycle()
    s = vehicle.size_vehicle(motor, env, LOSS, veh, demo_cycle)
    g = np.array([s.gear_ratio, 1.0, 50.0])
    margin = vehicle.torque_margin(demo_cycle, veh, motor, env, LOSS, g)
    assert margin.shape == (3,) and margin[0] == pytest.approx(s.min_margin) and margin[0] >= 1.0
    assert margin[2] == 0.0  # G = 50: top speed beyond Ω_max
    assert margin[1] < 1.0  # G = 1: not enough torque at the wheel
    short = vehicle.simulate(demo_cycle, replace(veh, gear_ratio=1.0), motor, env, emap, LOSS)
    assert short.summary.n_outside > 0
