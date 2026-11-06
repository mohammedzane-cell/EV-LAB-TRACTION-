import math

import numpy as np
import pytest

from evlab.core import circuit
from evlab.core.session import MotorParams, td5_ex1

W = 2 * math.pi * 50


@pytest.fixture
def m():
    return td5_ex1()


# --- TD5 Ex 1 reference values -------------------------------------------------

def test_breakdown_slip_td5(m):
    assert circuit.breakdown_slip(m) == pytest.approx(0.5)


def test_max_torque_td5(m):
    t_max = circuit.max_torque(m)
    assert t_max == pytest.approx(3 * 2 * 230**2 / (2 * 4 * W))
    assert t_max == pytest.approx(126.3, abs=0.05)


def test_torque_at_breakdown_equals_max(m):
    assert circuit.torque(m, 0.5) == pytest.approx(circuit.max_torque(m))


def test_torque_formula(m):
    g = 0.04
    i2 = circuit.rotor_current(m, g)
    expected = (3 * 2 / W) * (2.0 / g) * i2**2
    assert circuit.torque(m, g) == pytest.approx(expected)


def test_rotor_current_value(m):
    g = 0.04
    assert circuit.rotor_current(m, g) == pytest.approx(230 / math.hypot(2 / g, 4))


def test_breakdown_is_a_maximum(m):
    g = np.linspace(0.01, 1.0, 2000)
    t = circuit.torque(m, g)
    assert g[np.argmax(t)] == pytest.approx(0.5, abs=1e-3)
    assert t.max() <= circuit.max_torque(m) + 1e-9


# --- general behaviour ---------------------------------------------------------

def test_zero_slip_gives_zero_torque_and_current(m):
    assert circuit.torque(m, 0.0) == 0.0
    assert circuit.rotor_current(m, 0.0) == 0.0


def test_negative_slip_is_generating(m):
    assert circuit.torque(m, -0.05) < 0


def test_vectorised(m):
    g = np.array([0.0, 0.02, 0.5, 1.0])
    t = circuit.torque(m, g)
    assert t.shape == (4,)
    assert t[0] == 0.0


def test_breakdown_with_r1():
    m = MotorParams(v_phase=230, f_rated=50, pole_pairs=2, r1=1.0,
                    r2p=2.0, x_leak=4.0, x_m=46, r_fe=230)
    gc = circuit.breakdown_slip(m)
    assert gc == pytest.approx(2.0 / math.hypot(1.0, 4.0))
    g = np.linspace(0.05, 1.0, 5000)
    assert g[np.argmax(circuit.torque(m, g))] == pytest.approx(gc, abs=1e-3)
    assert circuit.torque(m, gc) == pytest.approx(circuit.max_torque(m))


def test_supply_override_scales_reactance(m):
    # Halving V and f at constant slip frequency: with R1=0 the torque at the
    # same rotor frequency f*g is unchanged (constant V/f, constant flux).
    g50 = 0.04
    g25 = 0.08
    t50 = circuit.torque(m, g50)
    t25 = circuit.torque(m, g25, v_phase=115.0, f=25.0)
    assert t25 == pytest.approx(t50)


def test_slip_speed_roundtrip(m):
    omega = 0.97 * m.omega_sync
    g = circuit.slip_from_speed(m, omega)
    assert g == pytest.approx(0.03)
    assert circuit.speed_from_slip(m, g) == pytest.approx(omega)


# --- operating point and power balance ----------------------------------------

def test_magnetising_currents(m):
    op = circuit.operating_point(m, 0.04)
    assert op.i_fe == pytest.approx(230 / 230)
    assert op.i_mu == pytest.approx(230 / 46)


def test_power_balance(m):
    op = circuit.operating_point(m, 0.04)
    assert op.p_in == pytest.approx(op.p_fe + op.p_cu1 + op.p_gap)
    assert op.p_gap == pytest.approx(op.p_cu2 + op.p_mech)
    assert op.p_cu2 == pytest.approx(0.04 * op.p_gap)
    assert op.torque == pytest.approx(op.p_gap / m.omega_sync)
    assert op.p_fe == pytest.approx(3 * 230**2 / 230)
    assert 0 < op.power_factor < 1


def test_stator_current_is_phasor_sum(m):
    op = circuit.operating_point(m, 0.04)
    z2 = complex(2 / 0.04, 4)
    i1 = 230 / 230 + 230 / complex(0, 46) + 230 / z2
    assert op.i1 == pytest.approx(abs(i1))


def test_operating_point_rejects_zero_slip(m):
    with pytest.raises(ValueError, match="slip"):
        circuit.operating_point(m, 0.0)


# --- validation ----------------------------------------------------------------

@pytest.mark.parametrize("g", [math.nan, math.inf])
def test_bad_slip(m, g):
    with pytest.raises(ValueError, match="slip"):
        circuit.torque(m, g)


@pytest.mark.parametrize("kw", [{"v_phase": 0.0}, {"v_phase": -1.0}, {"f": 0.0}, {"f": -50.0}])
def test_bad_supply(m, kw):
    with pytest.raises(ValueError):
        circuit.torque(m, 0.04, **kw)


# --- copper temperature correction ---------------------------------------------

def test_copper_resistance_at_20c_is_unchanged():
    assert circuit.copper_resistance(1.0, 293.15) == pytest.approx(1.0)


def test_copper_resistance_at_120c():
    expected = 1.0 * (234.5 + 120.0) / 254.5
    assert circuit.copper_resistance(1.0, 393.15) == pytest.approx(expected)


@pytest.mark.parametrize("r, t", [(0.0, 300.0), (-1.0, 300.0), (1.0, 0.0), (1.0, -5.0)])
def test_copper_resistance_validation(r, t):
    with pytest.raises(ValueError):
        circuit.copper_resistance(r, t)
