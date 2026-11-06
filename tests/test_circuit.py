import math
import warnings
from dataclasses import replace

import numpy as np
import pytest

from evlab.core import circuit
from evlab.core.session import MotorParams, td5_ex1

W = 2 * math.pi * 50
LAYOUTS = ("tp3", "terminals")


@pytest.fixture
def m():
    return td5_ex1()


def _motor(layout, r1=1.0):
    return MotorParams(v_phase=230, f_rated=50, pole_pairs=2, r1=r1,
                       r2p=2.0, x_leak=4.0, x_m=46.0, r_fe=230.0, layout=layout)


def _direct(m, g):
    """Plain textbook solve of the circuit, scalar, written independently of circuit.py.

    Returns (I1, I'2, magnetising-branch voltage) as complex phasors.
    """
    v = m.v_phase
    z_m = 1 / (1 / m.r_fe + 1 / complex(0, m.x_m))
    if m.layout == "tp3":
        z2 = complex(m.r2p / g, m.x_leak)
        i1 = v / (m.r1 + z_m * z2 / (z_m + z2))
        e = v - m.r1 * i1
        return i1, e / z2, e
    z2 = complex(m.r1 + m.r2p / g, m.x_leak)
    i2 = v / z2
    return v / z_m + i2, i2, v


# --- TD5 Ex 1 reference values (R1 = 0) --------------------------------------------

@pytest.mark.parametrize("layout", LAYOUTS)
def test_td5_breakdown_numeric(m, layout):
    g_c, t_max = circuit.breakdown(replace(m, layout=layout))
    assert g_c == pytest.approx(0.5, rel=1e-3)
    assert t_max == pytest.approx(126.3, rel=1e-3)


def test_td5_breakdown_closed_form_values(m):
    g_c, t_max = circuit.breakdown(m, method="closed")
    assert g_c == pytest.approx(2.0 / 4.0)
    assert t_max == pytest.approx(3 * 2 * 230**2 / (2 * 4 * W))


@pytest.mark.parametrize("layout", LAYOUTS)
def test_td5_numeric_matches_closed_form(m, layout):
    mm = replace(m, layout=layout)
    g_n, t_n = circuit.breakdown(mm)
    g_c, t_c = circuit.breakdown(mm, method="closed")
    assert g_n == pytest.approx(g_c, rel=1e-6)
    assert t_n == pytest.approx(t_c, rel=1e-9)


def test_td5_layouts_identical_when_r1_zero(m):
    g = np.linspace(-1, 2, 61)
    a, b = replace(m, layout="tp3"), replace(m, layout="terminals")
    for fn in (circuit.impedance, circuit.stator_current, circuit.rotor_current,
               circuit.torque, circuit.input_power, circuit.power_factor):
        assert np.allclose(fn(a, g), fn(b, g), rtol=1e-12, atol=0), fn.__name__


def test_td5_nominal_point(m):
    # TD5 Ex 1: 1350 tr/min, p = 2 -> g = 0.1; Is = V/Rf + V/(jXm) + V/(2/g + j4)
    assert circuit.slip_from_speed(m, 1350 * 2 * math.pi / 60) == pytest.approx(0.1)
    i_s = 230 / 230 + 230 / 46j + 230 / complex(20, 4)
    assert circuit.stator_current(m, 0.1) == pytest.approx(abs(i_s))
    assert circuit.power_factor(m, 0.1) == pytest.approx(i_s.real / abs(i_s))
    assert circuit.impedance(m, 0.1) == pytest.approx(230 / i_s)


def test_torque_formula(m):
    g = 0.04
    i2 = circuit.rotor_current(m, g)
    assert circuit.torque(m, g) == pytest.approx((3 * 2 / W) * (2.0 / g) * i2**2)


# --- both layouts with R1 != 0, against an independent solve ----------------------

@pytest.mark.parametrize("layout", LAYOUTS)
@pytest.mark.parametrize("g", [0.02, 0.3, 1.0, 1.8, -0.05, -0.4])
def test_currents_match_direct_solve(layout, g):
    m = _motor(layout)
    i1, i2, _ = _direct(m, g)
    assert circuit.impedance(m, g) == pytest.approx(m.v_phase / i1, rel=1e-12)
    assert circuit.stator_current(m, g) == pytest.approx(abs(i1), rel=1e-12)
    assert circuit.rotor_current(m, g) == pytest.approx(abs(i2), rel=1e-12)
    assert circuit.power_factor(m, g) == pytest.approx(i1.real / abs(i1), rel=1e-12)
    assert circuit.input_power(m, g) == pytest.approx(3 * m.v_phase * i1.real, rel=1e-12)
    t = (3 * 2 / W) * (m.r2p / g) * abs(i2) ** 2
    assert circuit.torque(m, g) == pytest.approx(t, rel=1e-12)


def test_layouts_differ_when_r1_nonzero():
    a, b = _motor("tp3"), _motor("terminals")
    assert circuit.stator_current(a, 0.0) != pytest.approx(circuit.stator_current(b, 0.0))
    assert circuit.breakdown(a)[1] != pytest.approx(circuit.breakdown(b)[1])


@pytest.mark.parametrize("layout", LAYOUTS)
def test_breakdown_numeric_matches_closed_form_with_r1(layout):
    m = _motor(layout)
    g_n, t_n = circuit.breakdown(m)
    g_c, t_c = circuit.breakdown(m, method="closed")
    assert g_n == pytest.approx(g_c, rel=1e-6)
    assert t_n == pytest.approx(t_c, rel=1e-9)
    # brute force on the independent solve
    g = np.linspace(0.05, 1.0, 20001)
    t = np.array([(3 * 2 / W) * (2.0 / gi) * abs(_direct(m, gi)[1]) ** 2 for gi in g])
    assert g[np.argmax(t)] == pytest.approx(g_c, abs=1e-4)
    assert t.max() == pytest.approx(t_c, rel=1e-7)


def test_breakdown_terminals_closed_form():
    m = _motor("terminals")
    g_c, t_c = circuit.breakdown(m, method="closed")
    assert g_c == pytest.approx(2.0 / math.hypot(1.0, 4.0))
    assert t_c == pytest.approx(3 * 2 * 230**2 / (2 * W * (1.0 + math.hypot(1.0, 4.0))))


def test_thevenin(m):
    v_th, z_th = circuit.thevenin(m)
    assert v_th == pytest.approx(230.0) and z_th == 0
    tp = _motor("tp3")
    z_m = 1 / (1 / 230 + 1 / 46j)
    v_th, z_th = circuit.thevenin(tp)
    assert v_th == pytest.approx(230 * z_m / (1 + z_m))
    assert z_th == pytest.approx(z_m / (1 + z_m))
    v_th, z_th = circuit.thevenin(_motor("terminals"))
    assert v_th == pytest.approx(230.0) and z_th == pytest.approx(1.0)


# --- no-load, generator, sign conventions -------------------------------------------

@pytest.mark.parametrize("layout", LAYOUTS)
def test_no_load_and_generator(layout):
    m = _motor(layout)
    assert circuit.torque(m, 0.0) == 0.0
    assert circuit.rotor_current(m, 0.0) == 0.0
    assert circuit.efficiency(m, 0.0) == 0.0
    assert circuit.stator_current(m, 0.0) > 0
    for g in (0.01, 0.1, 0.5):
        assert circuit.torque(m, -g) < 0
        assert circuit.torque(m, g) > 0
    assert circuit.input_power(m, -0.1) < 0  # power returned to the supply
    assert circuit.power_factor(m, -0.1) < 0


@pytest.mark.parametrize("layout", LAYOUTS)
def test_no_division_warnings(layout):
    m = _motor(layout)
    g = np.array([-2.0, -1.0, -1e-9, 0.0, 1e-12, 0.5, 1.0, 3.0])
    with warnings.catch_warnings(), np.errstate(all="raise"):
        warnings.simplefilter("error")
        for fn in (circuit.impedance, circuit.stator_current, circuit.rotor_current,
                   circuit.power_factor, circuit.torque, circuit.mechanical_speed,
                   circuit.input_power, circuit.efficiency):
            out = np.asarray(fn(m, g))
            assert out.shape == g.shape
            assert np.all(np.isfinite(out)), fn.__name__
        op = circuit.operating_point(m, g)
        assert np.all(np.isfinite(op.p_gap))


@pytest.mark.parametrize("layout", LAYOUTS)
def test_scalar_in_scalar_out(layout):
    m = _motor(layout)
    for fn in (circuit.stator_current, circuit.torque, circuit.efficiency, circuit.mechanical_speed):
        assert isinstance(fn(m, 0.05), float)
    assert isinstance(circuit.impedance(m, 0.05), complex)


# --- power balance ----------------------------------------------------------------

@pytest.mark.parametrize("layout", LAYOUTS)
def test_power_balance(layout):
    m = _motor(layout)
    g = np.concatenate([np.linspace(-1.5, 2.0, 71), [0.0]])
    op = circuit.operating_point(m, g)
    losses = op.p_cu1 + op.p_fe + op.p_cu2
    scale = 3 * m.v_phase * op.i1
    assert np.max(np.abs(op.p_in - (op.p_mech + losses)) / scale) < 1e-9
    assert np.allclose(op.p_gap, op.p_cu2 + op.p_mech, rtol=1e-12)
    assert np.allclose(op.torque, op.p_gap / m.omega_sync, rtol=1e-12)
    assert np.allclose(op.p_mech, op.torque * op.omega_mech, rtol=1e-12, atol=1e-9)


def test_loss_location_depends_on_layout():
    tp, te = _motor("tp3"), _motor("terminals")
    g = 0.05
    i1, i2, e = _direct(tp, g)
    op = circuit.operating_point(tp, g)
    assert op.p_cu1 == pytest.approx(3 * 1.0 * abs(i1) ** 2)      # R1 carries I1
    assert op.p_fe == pytest.approx(3 * abs(e) ** 2 / 230)
    i1, i2, _ = _direct(te, g)
    op = circuit.operating_point(te, g)
    assert op.p_cu1 == pytest.approx(3 * 1.0 * abs(i2) ** 2)      # R1 carries I'2
    assert op.p_fe == pytest.approx(3 * 230**2 / 230)
    assert circuit.operating_point(te, 0.0).p_cu1 == 0.0           # no R1 loss at no-load


def test_tp3_no_load_r1_loss():
    m = _motor("tp3")
    op = circuit.operating_point(m, 0.0)
    assert op.p_cu1 == pytest.approx(3 * 1.0 * op.i1**2)  # TP3: P0 = 3·R1·I0² + P_fe
    assert op.p_in == pytest.approx(op.p_cu1 + op.p_fe)


# --- efficiency -----------------------------------------------------------------

@pytest.mark.parametrize("layout", LAYOUTS)
def test_efficiency(layout):
    m = _motor(layout)
    g = 0.05
    assert circuit.efficiency(m, g) == pytest.approx(
        (1 - g) * circuit.operating_point(m, g).p_gap / circuit.input_power(m, g))
    g = -0.05
    op = circuit.operating_point(m, g)
    assert circuit.efficiency(m, g) == pytest.approx(op.p_in / op.p_mech)  # P_elec out / P_mech in
    assert circuit.efficiency(m, 1.0) == 0.0   # locked rotor: no mechanical output
    assert circuit.efficiency(m, 1.5) == 0.0   # plugging: no useful output
    eta = circuit.efficiency(m, np.linspace(-1, 1, 201))
    assert np.all((eta >= 0) & (eta < 1))


# --- speed and V/f override -------------------------------------------------------

def test_mechanical_speed(m):
    assert circuit.mechanical_speed(m, 0.0) == pytest.approx(W / 2)
    assert circuit.mechanical_speed(m, 0.03) == pytest.approx(0.97 * W / 2)
    assert circuit.mechanical_speed(m, -0.1) > W / 2
    assert circuit.slip_from_speed(m, circuit.mechanical_speed(m, 0.03)) == pytest.approx(0.03)


def test_constant_v_over_f_same_rotor_frequency(m):
    assert circuit.torque(m, 0.08, v_phase=115.0, f=25.0) == pytest.approx(circuit.torque(m, 0.04))


# --- validation -----------------------------------------------------------------

@pytest.mark.parametrize("g", [math.nan, math.inf, [0.1, math.nan]])
def test_bad_slip(m, g):
    with pytest.raises(ValueError, match="slip"):
        circuit.torque(m, g)


@pytest.mark.parametrize("kw", [{"v_phase": 0.0}, {"v_phase": -1.0}, {"f": 0.0}, {"f": math.nan}])
def test_bad_supply(m, kw):
    with pytest.raises(ValueError):
        circuit.stator_current(m, 0.04, **kw)


def test_bad_breakdown_method(m):
    with pytest.raises(ValueError, match="method"):
        circuit.breakdown(m, method="guess")


# --- copper temperature correction ---------------------------------------------

def test_copper_resistance():
    assert circuit.copper_resistance(1.0, 293.15) == pytest.approx(1.0)
    assert circuit.copper_resistance(1.0, 393.15) == pytest.approx((234.5 + 120.0) / 254.5)


@pytest.mark.parametrize("r, t", [(0.0, 300.0), (-1.0, 300.0), (1.0, 0.0), (1.0, -5.0)])
def test_copper_resistance_validation(r, t):
    with pytest.raises(ValueError):
        circuit.copper_resistance(r, t)


# --- broadcasting over supply arrays (needed by drive and losses maps) -------------

@pytest.mark.parametrize("layout", LAYOUTS)
def test_broadcast_over_supply_arrays(layout):
    m = _motor(layout)
    g = np.array([0.02, 0.1, 0.3, -0.05])
    f = np.array([10.0, 50.0, 80.0, 25.0])
    v = 230.0 * np.minimum(f / 50.0, 1.0)
    rfe = np.array([150.0, 230.0, 300.0, 200.0])
    op = circuit.operating_point(m, g, v_phase=v, f=f, r_fe=rfe)
    for k in range(4):
        mk = replace(m, r_fe=float(rfe[k]))
        ok = circuit.operating_point(mk, g[k], v_phase=v[k], f=f[k])
        for name in ("i1", "i2", "torque", "p_in", "p_fe", "p_cu1", "p_gap", "omega_mech"):
            assert getattr(op, name)[k] == pytest.approx(getattr(ok, name), rel=1e-12), name
    t = circuit.torque(m, g, v_phase=v, f=f)
    assert t[2] == pytest.approx(circuit.torque(m, 0.3, v_phase=v[2], f=80.0))
    gc = circuit.breakdown_slip(m, f=f)
    tm = circuit.max_torque(m, v_phase=v, f=f)
    assert gc[1] == pytest.approx(circuit.breakdown_slip(m)) and tm.shape == (4,)
    assert tm[0] == pytest.approx(circuit.breakdown(m, v_phase=v[0], f=10.0, method="closed")[1])


def test_broadcast_validation(m):
    with pytest.raises(ValueError, match="f"):
        circuit.torque(m, 0.1, f=np.array([50.0, -1.0]))
    with pytest.raises(ValueError, match="r_fe"):
        circuit.operating_point(m, 0.1, r_fe=np.array([0.0]))
    with pytest.raises(ValueError, match="scalar"):
        circuit.breakdown(m, f=np.array([40.0, 50.0]))
