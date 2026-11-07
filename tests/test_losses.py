import math
import time
from dataclasses import replace

import numpy as np
import pytest

from evlab.core import circuit, drive, losses
from evlab.core.session import td5_ex1

DRIVE = drive.DriveSettings(i_max=20.0)
OFF = losses.LossSettings(mechanical=False, inverter=False)


@pytest.fixture
def m():
    return td5_ex1()


def _demo(m):  # the motor of the demo files: R1 identified at 75 °C, p_mec = 60 W
    return replace(m, r1=0.5, p_mech=60.0, r1_temperature_k=348.15, is_demo=True)


def _grid(n_t=40, n_w=30, t_max=90.0, w_max=270.0):
    return np.linspace(1.0, t_max, n_t), np.linspace(5.0, w_max, n_w)


# --- the map and tab 1 tell the same story ----------------------------------------

@pytest.mark.parametrize("motor", [td5_ex1(), _demo(td5_ex1())], ids=["TD5", "demo"])
@pytest.mark.parametrize("g", [0.04, 0.1, 0.2])
def test_efficiency_at_50hz_equals_circuit(motor, g):
    t = circuit.torque(motor, g)
    w = circuit.mechanical_speed(motor, g)
    r1_hot = replace(motor, r1_temperature_k=None)  # no temperature correction either
    wide = drive.DriveSettings(i_max=60.0, margin=1.0)  # the drive limits must contain the point
    emap = losses.efficiency_map(r1_hot, np.array([t]), np.array([w]), wide, OFF)
    assert emap.f[0, 0] == pytest.approx(50.0, rel=1e-6)
    assert emap.eta[0, 0] == pytest.approx(circuit.efficiency(motor, g), rel=1e-3)


def test_beta_does_not_matter_at_fn(m):
    t, w = circuit.torque(m, 0.1), circuit.mechanical_speed(m, 0.1)
    a = losses.efficiency_map(m, np.array([t]), np.array([w]), DRIVE, replace(OFF, beta=1.2))
    b = losses.efficiency_map(m, np.array([t]), np.array([w]), DRIVE, replace(OFF, beta=2.0))
    assert a.eta[0, 0] == pytest.approx(b.eta[0, 0], rel=1e-6)


# --- balance, range, envelope -------------------------------------------------------

@pytest.mark.parametrize("motor", [td5_ex1(), _demo(td5_ex1()), replace(_demo(td5_ex1()), layout="terminals")],
                         ids=["TD5", "demo", "terminals"])
def test_losses_sum_to_input_minus_output(motor):
    st = losses.LossSettings(winding_temperature_k=393.15)  # 120 °C
    emap = losses.efficiency_map(motor, *_grid(), DRIVE, st)
    ok = emap.valid
    assert ok.sum() > 100
    total = emap.p_cu1 + emap.p_cu2 + emap.p_fe + emap.p_mech + emap.p_inv
    resid = np.abs(emap.p_in - emap.p_out - total)[ok] / emap.p_in[ok]
    assert resid.max() < 1e-9
    assert np.all((emap.eta[ok] > 0) & (emap.eta[ok] < 1))
    for name in ("eta", "p_cu1", "p_cu2", "p_fe", "p_mech", "p_inv", "p_in", "p_out"):
        assert np.all(np.isnan(getattr(emap, name)[~ok])), name
    assert np.all(np.isfinite(emap.eta[ok]))


def test_nan_outside_envelope(m):
    env = drive.envelope(m, DRIVE)
    torque = np.array([10.0, 60.0, 200.0])
    speed = np.array([50.0, 150.0, env.omega_max * 1.1])
    emap = losses.efficiency_map(m, torque, speed, DRIVE, OFF, envelope=env)
    assert np.isfinite(emap.eta[0, 0]) and np.isfinite(emap.eta[1, 0])
    assert np.isnan(emap.eta[2, 0])  # 200 N·m is above the envelope
    assert np.all(np.isnan(emap.eta[:, 2]))  # beyond the maximum speed
    assert emap.valid[1, 1] == bool(60.0 <= env.torque_at(150.0))


def test_solution_delivers_the_requested_torque(m):
    motor = _demo(m)
    emap = losses.efficiency_map(motor, *_grid(), DRIVE)
    ok = emap.valid
    tt, ww = np.meshgrid(emap.torque, emap.speed, indexing="ij")
    assert np.allclose(emap.p_out[ok] / ww[ok], tt[ok], rtol=1e-6)
    # under the V/f law, at the solved frequency
    assert np.allclose(emap.v[ok], drive.vf_voltage(motor, emap.f[ok]))


# --- individual loss terms ------------------------------------------------------------

def test_mechanical_losses_scaling(m):
    motor = _demo(m)
    st = losses.LossSettings(friction_share=0.5)
    w0 = 2 * math.pi * 50 / 2
    assert losses.mechanical_loss(motor, w0, st) == pytest.approx(60.0)
    assert losses.mechanical_loss(motor, 2 * w0, st) == pytest.approx(0.5 * 60 * 2 + 0.5 * 60 * 4)
    assert losses.mechanical_loss(motor, w0, replace(st, mechanical=False)) == 0.0
    assert losses.mechanical_loss(m, w0, st) == 0.0  # TD5 Ex 1: negligible


def test_iron_loss_frequency_law(m):
    st = losses.LossSettings(beta=1.5)
    assert losses.iron_resistance(m, 50.0, st) == pytest.approx(230.0)
    # P_fe ∝ f^β·B² with B ∝ E/f  ⇔  Rf(f) = Rf·(f/fn)^(2 − β)
    assert losses.iron_resistance(m, 100.0, st) == pytest.approx(230.0 * 2**0.5)
    assert losses.iron_resistance(m, 100.0, replace(st, beta=2.0)) == pytest.approx(230.0)


def test_r1_temperature_correction(m):
    motor = _demo(m)  # R1 = 0.5 Ω at 75 °C
    st = losses.LossSettings(winding_temperature_k=393.15)
    assert losses.stator_resistance(motor, st) == pytest.approx(0.5 * (234.5 + 120) / (234.5 + 75))
    assert losses.stator_resistance(motor, losses.LossSettings()) == 0.5
    with pytest.raises(ValueError, match="r1_temperature_k"):
        losses.stator_resistance(replace(motor, r1_temperature_k=None), st)
    hot = losses.efficiency_map(motor, *_grid(), DRIVE, st)
    cold = losses.efficiency_map(motor, *_grid(), DRIVE, losses.LossSettings(winding_temperature_k=293.15))
    both = hot.valid & cold.valid
    assert np.all(hot.p_cu1[both] > cold.p_cu1[both])


def test_inverter_losses(m):
    st = losses.LossSettings(mechanical=False, inverter_fixed_w=50.0, inverter_fraction=0.02)
    emap = losses.efficiency_map(m, *_grid(10, 8), DRIVE, st)
    ok = emap.valid
    p_motor = emap.p_in - emap.p_inv
    assert np.allclose(emap.p_inv[ok], 50.0 + 0.02 * p_motor[ok])


# --- speed ----------------------------------------------------------------------

def test_160_by_120_map_under_one_second(m):
    motor = _demo(m)
    torque, speed = np.linspace(1.0, 90.0, 160), np.linspace(5.0, 275.0, 120)
    losses.efficiency_map(motor, torque[:4], speed[:4], DRIVE)  # warm-up (imports, caches)
    t0 = time.perf_counter()
    emap = losses.efficiency_map(motor, torque, speed, DRIVE)
    elapsed = time.perf_counter() - t0
    assert emap.eta.shape == (160, 120)
    assert elapsed < 1.0, f"{elapsed:.3f} s"


# --- validation -----------------------------------------------------------------

@pytest.mark.parametrize("kw", [dict(beta=0.0), dict(beta=3.5), dict(friction_share=1.5),
                                dict(inverter_fixed_w=-1.0), dict(inverter_fraction=1.0),
                                dict(winding_temperature_k=0.0)])
def test_settings_validation(kw):
    with pytest.raises(ValueError):
        losses.LossSettings(**kw)


def test_grid_validation(m):
    with pytest.raises(ValueError, match="speed"):
        losses.efficiency_map(m, np.array([10.0]), np.array([0.0]), DRIVE)
    with pytest.raises(ValueError, match="torque"):
        losses.efficiency_map(m, np.array([-1.0]), np.array([100.0]), DRIVE)
    with pytest.raises(ValueError, match="1-D"):
        losses.efficiency_map(m, np.ones((2, 2)), np.array([100.0]), DRIVE)


def test_default_grid_and_best_point(m):
    motor = _demo(m)
    env = drive.envelope(motor, DRIVE)
    st = losses.LossSettings()
    t, w = losses.default_grid(motor, env, st, 40, 30)
    assert t.shape == (40,) and w.shape == (30,)
    assert w[-1] == env.omega_max and t[-1] == pytest.approx(1.05 * losses.shaft_torque_limit(motor, env, st).max())
    assert t[0] == 0.0  # the map covers coasting (zero shaft torque)
    emap = losses.efficiency_map(motor, t, w, DRIVE, st, envelope=env)
    eta, tb, wb = losses.best_point(emap)
    assert eta == np.nanmax(emap.eta)
    assert tb in t and wb in w
    with pytest.raises(ValueError):
        losses.default_grid(motor, env, st, 1, 30)


@pytest.mark.parametrize("p_mech", [0.0, 60.0])
def test_zero_torque_row_is_valid_with_zero_output(m, p_mech):
    motor = replace(_demo(m), p_mech=p_mech)
    env = drive.envelope(motor, DRIVE)
    st = losses.LossSettings(winding_temperature_k=348.15)
    t, w = losses.default_grid(motor, env, st, 20, 15)
    emap = losses.efficiency_map(motor, t, w, DRIVE, st, envelope=env)
    assert emap.valid[0].all()
    assert np.all(emap.p_out[0] == 0.0) and np.all(emap.eta[0] == 0.0)
    assert np.all(emap.p_in[0] > 0)  # no-load losses: iron, inverter P_0, mechanical
    total = emap.p_cu1 + emap.p_cu2 + emap.p_fe + emap.p_mech + emap.p_inv
    assert np.allclose(emap.p_in[0] - emap.p_out[0], total[0], rtol=1e-9)


def test_shaft_limit_below_electromagnetic(m):
    motor = _demo(m)
    env = drive.envelope(motor, DRIVE)
    lim = losses.shaft_torque_limit(motor, env, losses.LossSettings())
    assert np.all(lim[1:] < env.torque[1:]) and lim[0] == env.torque[0]


# --- the map honours the drive limits with its own (hot R1, Rf(f)) circuit -------------

@pytest.mark.parametrize("t_w", [None, 423.15], ids=["T_id", "150C"])
@pytest.mark.parametrize("beta", [1.0, 1.5, 2.0])
def test_map_respects_current_and_margin_limits(beta, t_w):
    motor = _demo(td5_ex1())
    st = losses.LossSettings(beta=beta, winding_temperature_k=t_w)
    env = drive.envelope(motor, DRIVE)
    t, w = losses.default_grid(motor, env, st, 80, 60)
    emap = losses.efficiency_map(motor, t, w, DRIVE, st, envelope=env)
    ok = emap.valid
    assert ok.sum() > 1000
    assert np.nanmax(emap.i1) <= DRIVE.i_max * (1 + 1e-6)
    # electromagnetic torque below margin·T_bd of the same circuit (hot R1, Rf(f))
    hot = replace(motor, r1=losses.stator_resistance(motor, st))
    rfe = losses.iron_resistance(motor, emap.f[ok], st)
    t_bd = circuit.max_torque(hot, v_phase=emap.v[ok], f=emap.f[ok], r_fe=rfe)
    tt, ww = np.meshgrid(emap.torque, emap.speed, indexing="ij")
    t_em = tt[ok] + emap.p_mech[ok] / ww[ok]
    assert np.all(t_em <= DRIVE.margin * t_bd * (1 + 1e-6))


def test_hot_winding_shrinks_the_map():
    motor = _demo(td5_ex1())
    env = drive.envelope(motor, DRIVE)
    cold = losses.LossSettings(beta=2.0)
    hot = losses.LossSettings(beta=2.0, winding_temperature_k=423.15)
    t, w = losses.default_grid(motor, env, cold, 80, 60)
    a = losses.efficiency_map(motor, t, w, DRIVE, cold, envelope=env)
    b = losses.efficiency_map(motor, t, w, DRIVE, hot, envelope=env)
    assert b.valid.sum() < a.valid.sum()
    assert not np.any(b.valid & ~a.valid)


# --- démo loss settings (A19, A21) ----------------------------------------------------

def test_demo_fields_of_the_loss_settings():
    st = losses.LossSettings()
    assert (st.beta, st.inverter_fixed_w, st.inverter_fraction) == (1.5, 50.0, 0.02)
    assert losses.demo_fields(st) == ("beta", "inverter_fixed_w", "inverter_fraction")
    assert losses.demo_fields(replace(st, inverter_fixed_w=30.0)) == ("beta", "inverter_fraction")
    assert losses.demo_fields(replace(st, inverter=False)) == ("beta",)  # no inverter loss, nothing démo there
    assert losses.demo_fields(replace(st, beta=2.0, inverter=False)) == ()
