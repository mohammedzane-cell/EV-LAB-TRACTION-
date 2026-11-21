"""core/characteristics.py against independent closed forms (TD5 Ex 1, R1 = 0) and physical limits."""

import math

import pytest

from evlab.core import characteristics as ch
from evlab.core import circuit
from evlab.core.session import td5_ex1

V, F, P, R2, X = 230.0, 50.0, 2, 2.0, 4.0
W = 2 * math.pi * F


def test_points_of_td5_match_the_closed_forms():
    m = td5_ex1()
    c = ch.characteristics(m)
    assert c.omega_sync == pytest.approx(W / P)
    # R1 = 0, Γ circuit: the rotor branch sees V directly
    assert c.start_torque == pytest.approx(3 * P / W * V**2 * R2 / (R2**2 + X**2), rel=1e-9)
    assert c.breakdown_slip == pytest.approx(R2 / X, rel=1e-6)
    assert c.breakdown_torque == pytest.approx(3 * P * V**2 / (2 * X * W), rel=1e-6)  # 126,3 N·m
    assert c.breakdown_speed == pytest.approx(W / P * (1 - R2 / X), rel=1e-6)
    assert 0 < c.start_power_factor < 1 and c.no_load_current < c.start_current


def test_sensitivities_of_td5_match_the_closed_forms():
    s = ch.sensitivity(td5_ex1())
    # T_max = 3pV²/(2Xω): ∝ 1/X, independent of R'2, Xm, Rf
    assert s["breakdown_torque"]["x_leak"] == pytest.approx(-1.0, abs=1e-6)
    for p in ("r2p", "x_m", "r_fe"):
        assert s["breakdown_torque"][p] == pytest.approx(0.0, abs=1e-6)
    # g_c = R'2/X
    assert s["breakdown_slip"]["r2p"] == pytest.approx(1.0, abs=1e-6)
    assert s["breakdown_slip"]["x_leak"] == pytest.approx(-1.0, abs=1e-6)
    # T_start = 3p/ω·V²R'2/(R'2² + X²)
    assert s["start_torque"]["r2p"] == pytest.approx(1 - 2 * R2**2 / (R2**2 + X**2), abs=1e-6)  # 0,6
    assert s["start_torque"]["x_leak"] == pytest.approx(-2 * X**2 / (R2**2 + X**2), abs=1e-6)  # −1,6
    # R1 = 0: no relative change exists, S = 0 by definition
    assert all(s[o]["r1"] == 0.0 for o in ch.OUTPUTS)


def test_sensitivity_with_r1_against_a_direct_difference():
    m = td5_ex1().__class__(**{**td5_ex1().__dict__, "r1": 0.5})
    s = ch.sensitivity(m)
    t0 = circuit.breakdown(m)[1]
    t1 = circuit.breakdown(m.__class__(**{**m.__dict__, "r1": 0.5 * 1.01}))[1]
    assert s["breakdown_torque"]["r1"] == pytest.approx((t1 - t0) / t0 / 0.01, rel=0.02)
    assert s["breakdown_torque"]["r1"] < 0  # stator resistance lowers the breakdown torque


def test_rotor_temperature_correction():
    m = td5_ex1()
    hot = ch.rotor_at_temperature(m, 273.15 + 100, 273.15 + 20, "aluminium")
    assert hot.r2p == pytest.approx(2.0 * (225 + 100) / (225 + 20))
    cu = ch.rotor_at_temperature(m, 273.15 + 75, 273.15 + 20, "cuivre")
    assert cu.r2p == pytest.approx(2.0 * 309.5 / 254.5)
    assert ch.rotor_at_temperature(m, 300.0, 300.0).r2p == m.r2p
    # a hotter rotor: same breakdown torque (R1 = 0), larger breakdown slip
    assert circuit.breakdown(hot)[1] == pytest.approx(circuit.breakdown(m)[1], rel=1e-6)
    assert circuit.breakdown(hot)[0] > circuit.breakdown(m)[0]


def test_point_at_speed_and_invalid_inputs():
    m = td5_ex1()
    op = ch.point_at_speed(m, W / P * 0.97)
    assert float(op.slip) == pytest.approx(0.03)
    with pytest.raises(ValueError):
        ch.point_at_speed(m, -1.0)
    with pytest.raises(ValueError):
        ch.point_at_speed(m, 2 * W)  # above synchronous: generating
    with pytest.raises(ValueError):
        ch.rotor_at_temperature(m, 300.0, 293.15, "fer")
    with pytest.raises(ValueError):
        ch.sensitivity(m, slip_ref=1.5)
    with pytest.raises(ValueError):
        ch.characteristics("moteur")
