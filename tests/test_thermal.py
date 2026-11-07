import math
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from evlab.core import drive, losses, thermal, vehicle
from evlab.core.session import td5_ex1
from evlab.io.cycles import load_cycle

DATA = Path(__file__).resolve().parents[1] / "data"
P = thermal.demo_thermal()
TA = P.t_ambient_k


def _a_matrix(p):
    return np.array([[-1 / (p.r_ws * p.c_w), 1 / (p.r_ws * p.c_w)],
                     [1 / (p.r_ws * p.c_s), -(1 / p.r_ws + 1 / p.r_sa) / p.c_s]])


# --- steady state -------------------------------------------------------------------

def test_steady_state_constant_losses():
    pw, ps = 300.0, 900.0
    tw, ts = thermal.steady_state(P, pw, ps)
    assert ts == pytest.approx(TA + P.r_sa * (pw + ps))
    assert tw == pytest.approx(ts + P.r_ws * pw)


@pytest.mark.parametrize("copper_ref", [None, 348.15])
def test_simulation_reaches_steady_state(copper_ref):
    pw, ps = 300.0, 900.0
    n = 20_000  # s, ≫ slow time constant
    res = thermal.simulate(P, np.full(n, pw), np.full(n, ps), copper_ref_k=copper_ref)
    tw, ts = thermal.steady_state(P, pw, ps, copper_ref_k=copper_ref)
    assert res.t_w[-1] == pytest.approx(tw, abs=0.1)
    assert res.t_s[-1] == pytest.approx(ts, abs=0.1)


def test_copper_feedback_raises_winding_temperature():
    """With R1(T), losses at 75 °C grow when the winding runs hotter: the steady state solves a linear system."""
    pw, ps = 300.0, 900.0
    tw0, _ = thermal.steady_state(P, pw, ps)
    tw1, ts1 = thermal.steady_state(P, pw, ps, copper_ref_k=348.15)
    k = (234.5 + tw1 - 273.15) / (234.5 + 75.0)
    assert tw1 > tw0
    assert ts1 == pytest.approx(TA + P.r_sa * (pw * k + ps))
    assert tw1 == pytest.approx(ts1 + P.r_ws * pw * k)


# --- time constants -------------------------------------------------------------

def test_time_constants_match_eigenvalues():
    tau = thermal.time_constants(P)
    lam = np.sort(np.linalg.eigvals(_a_matrix(P)).real)
    assert tau[0] == pytest.approx(-1 / lam[0], rel=1e-9)  # fast
    assert tau[1] == pytest.approx(-1 / lam[1], rel=1e-9)  # slow
    assert tau[0] < tau[1]


@pytest.mark.parametrize("method", ["implicit", "rk45"])
def test_step_response_decays_with_the_slow_time_constant(method):
    """Late in a step response, ln(T_ss − T_w) falls with slope −1/τ_slow (within 1 %)."""
    pw, ps = 300.0, 900.0
    n = 12_000
    res = thermal.simulate(P, np.full(n, pw), np.full(n, ps), method=method)
    tw_ss, _ = thermal.steady_state(P, pw, ps)
    _, tau_slow = thermal.time_constants(P)
    sel = (res.t > 4 * thermal.time_constants(P)[0]) & (res.t < 3 * tau_slow)
    slope = np.polyfit(res.t[sel], np.log(tw_ss - res.t_w[sel]), 1)[0]
    assert -1 / slope == pytest.approx(tau_slow, rel=0.01)


# --- integrators on the demo cycle --------------------------------------------------

@pytest.fixture(scope="module")
def cycle_losses():
    m = replace(td5_ex1(), r1=0.5, p_mech=60.0, r1_temperature_k=348.15, is_demo=True)
    d = drive.DriveSettings(i_max=20.0)
    st = losses.LossSettings(winding_temperature_k=348.15)
    env = drive.envelope(m, d)
    t, w = losses.default_grid(m, env, st, 100, 80)
    emap = losses.efficiency_map(m, t, w, d, st, envelope=env)
    cyc = load_cycle(DATA / "cycle_demo.csv")
    veh = vehicle.demo_quadricycle(gear_ratio=3.5)
    res = vehicle.simulate(cyc, veh, m, env, emap, st)
    return thermal.cycle_losses(res, emap), emap, res


def test_cycle_losses_from_the_map(cycle_losses):
    (p_cu1, p_frame), emap, res = cycle_losses
    assert p_cu1.shape == res.t.shape == p_frame.shape
    assert np.all(p_cu1 >= 0) and np.all(p_frame >= 0)
    assert np.all(p_cu1[res.omega == 0] == 0) and np.all(p_frame[res.omega == 0] == 0)
    k = int(np.argmax(res.torque))
    cu2 = vehicle.LossTable(emap, "p_cu2")(res.torque[k], res.omega[k])
    fe = vehicle.LossTable(emap, "p_fe")(res.torque[k], res.omega[k])
    assert p_frame[k] == pytest.approx(cu2 + fe)


def test_explicit_and_implicit_agree_on_the_demo_cycle(cycle_losses):
    (p_cu1, p_frame), emap, _ = cycle_losses
    kw = dict(copper_ref_k=348.15, n_cycles=5)
    imp = thermal.simulate(P, p_cu1, p_frame, method="implicit", **kw)
    exp = thermal.simulate(P, p_cu1, p_frame, method="rk45", **kw)
    assert np.max(np.abs(imp.t_w - exp.t_w)) < 0.5
    assert np.max(np.abs(imp.t_s - exp.t_s)) < 0.5
    assert imp.t.size == 5 * p_cu1.size + 1


def test_n_cycles_back_to_back_heat_up(cycle_losses):
    (p_cu1, p_frame), _, _ = cycle_losses
    one = thermal.simulate(P, p_cu1, p_frame, n_cycles=1, copper_ref_k=348.15)
    ten = thermal.simulate(P, p_cu1, p_frame, n_cycles=10, copper_ref_k=348.15)
    assert ten.summary.t_max > one.summary.t_max
    assert np.allclose(ten.t_w[: one.t_w.size], one.t_w)  # same start
    # T mean is the mean over the last cycle
    last = ten.t >= ten.t[-1] - p_cu1.size
    assert ten.summary.t_mean == pytest.approx(np.mean(ten.t_w[last][1:]), rel=1e-12)


# --- insulation life --------------------------------------------------------------

def test_insulation_life_ten_kelvin_rule():
    l155 = thermal.insulation_life(155 + 273.15, "F")
    assert l155 == pytest.approx(thermal.L_REF_HOURS)
    assert thermal.insulation_life(145 + 273.15, "F") == pytest.approx(2 * l155)
    assert thermal.insulation_life(165 + 273.15, "F") == pytest.approx(l155 / 2)
    assert thermal.insulation_life(130 + 273.15, "B") == pytest.approx(l155)
    assert thermal.order_of_magnitude(3.7e5) == 1e5
    with pytest.raises(ValueError, match="class"):
        thermal.insulation_life(400.0, "Z")


def test_summary(cycle_losses):
    (p_cu1, p_frame), _, _ = cycle_losses
    res = thermal.simulate(P, p_cu1, p_frame, n_cycles=3, copper_ref_k=348.15, insulation_class="F")
    s = res.summary
    assert s.t_max == pytest.approx(res.t_w.max())
    assert s.margin == pytest.approx(155 + 273.15 - s.t_max)
    last_cycle = res.t_w[-p_cu1.size:]  # the samples at the end of each step of the last cycle
    assert s.life_hours == pytest.approx(thermal.insulation_life(last_cycle, "F"), rel=1e-12)
    assert s.life_hours <= thermal.insulation_life(s.t_mean, "F")  # ageing is convex in T


def test_insulation_life_from_the_mean_ageing_rate_two_levels():
    t = np.r_[np.full(50, 60 + 273.15), np.full(50, 160 + 273.15)]  # 50 % at 60 °C, 50 % at 160 °C
    life = thermal.insulation_life(t, "F")
    expected = thermal.L_REF_HOURS / (0.5 * 2 ** ((60 - 155) / 10) + 0.5 * 2 ** ((160 - 155) / 10))
    assert life == pytest.approx(expected, rel=1e-12)
    assert life == pytest.approx(28_257, rel=1e-4)
    # the mean temperature (110 °C) would give 16 times more
    assert thermal.insulation_life(110 + 273.15, "F") / life == pytest.approx(16.0, rel=0.01)
    # constant profile = scalar rule
    assert thermal.insulation_life(np.full(7, 145 + 273.15), "F") == pytest.approx(2 * thermal.L_REF_HOURS)


@pytest.mark.parametrize("bad", [np.array([]), np.array([400.0, -1.0]), np.array([np.nan])])
def test_insulation_life_profile_validation(bad):
    with pytest.raises(ValueError):
        thermal.insulation_life(bad, "F")


def test_steady_state_thermal_runaway_raises():
    # 234,5 rule at 20 °C: P_w grows by P_w/254,5 per kelvin, while the network removes
    # 1/(R_ws + R_sa) = 7,14 W/K: no steady state above 254,5/0,14 = 1818 W
    for pw in (1900.0, 2400.0, 3000.0):
        with pytest.raises(ValueError, match="emballement thermique"):
            thermal.steady_state(P, pw, 100.0, copper_ref_k=293.15)
    tw, ts = thermal.steady_state(P, 300.0, 900.0, copper_ref_k=293.15)  # normal case still solves
    assert tw > ts > TA


# --- cooling-curve fit (for TP3 timed resistance readings) ------------------------

def test_fit_cooling_curve_recovers_time_constant():
    tau, t0, ta = 900.0, 393.15, TA
    t = np.arange(0.0, 3600.0, 60.0)
    temp = ta + (t0 - ta) * np.exp(-t / tau)
    r20 = 0.42
    r = r20 * (234.5 + temp - 273.15) / 254.5
    fit_tau, fit_t0 = thermal.fit_cooling_curve(t, r, r_ref=r20, t_ref_k=293.15, t_ambient_k=ta)
    assert fit_tau == pytest.approx(tau, rel=1e-6)
    assert fit_t0 == pytest.approx(t0, abs=1e-6)


# --- validation -------------------------------------------------------------------

@pytest.mark.parametrize("kw", [dict(c_w=0.0), dict(r_sa=-1.0), dict(t_ambient_k=0.0)])
def test_params_validation(kw):
    with pytest.raises(ValueError):
        replace(P, **kw)


def test_simulate_validation():
    with pytest.raises(ValueError, match="method"):
        thermal.simulate(P, np.ones(3), np.ones(3), method="euler")
    with pytest.raises(ValueError, match="same length"):
        thermal.simulate(P, np.ones(3), np.ones(4))
    with pytest.raises(ValueError, match="n_cycles"):
        thermal.simulate(P, np.ones(3), np.ones(3), n_cycles=0)
