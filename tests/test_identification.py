import math
from dataclasses import replace

import numpy as np
import pytest
from scipy.optimize import brentq

from evlab.core import circuit
from evlab.core import identification as ident
from evlab.core.session import MotorParams, td5_ex1


def _motor(r1=0.8):
    return MotorParams(v_phase=230, f_rated=50, pole_pairs=2, r1=r1,
                       r2p=2.0, x_leak=4.0, x_m=46.0, r_fe=230.0)


def _no_load(m, v=None, p_mech=0.0):
    """Physical no-load point: the motor runs at the slip g0 where the internal
    mechanical power equals p_mech (g0 = 0 when p_mech = 0)."""
    g0 = 0.0
    if p_mech > 0:
        g0 = brentq(lambda g: circuit.operating_point(m, g, v_phase=v).p_mech - p_mech, 1e-9, 0.2)
    op = circuit.operating_point(m, g0, v_phase=v)
    return ident.NoLoadTest(v_phase=v or m.v_phase, i_line=op.i1, p_total=op.p_in, f=m.f_rated)


def _locked(m, v=40.0, f=None):
    op = circuit.operating_point(m, 1.0, v_phase=v, f=f)
    return ident.LockedRotorTest(v_phase=v, i_line=op.i1, p_total=op.p_in, f=f or m.f_rated)


def _dc(r1, i=5.0):
    return ident.DcTest(v_dc=2 * r1 * i, i_dc=i)


# --- DC test -------------------------------------------------------------------

def test_r1_from_dc_star():
    assert ident.r1_from_dc(ident.DcTest(v_dc=8.0, i_dc=5.0)) == pytest.approx(0.8)


@pytest.mark.parametrize("v, i", [(0.0, 5.0), (8.0, 0.0), (-1.0, 5.0), (math.nan, 1.0)])
def test_dc_validation(v, i):
    with pytest.raises(ValueError):
        ident.DcTest(v_dc=v, i_dc=i)


# --- mechanical loss separation -------------------------------------------------

def test_mechanical_losses_intercept():
    v0 = np.array([100.0, 150.0, 200.0, 230.0])
    p0p = 0.012 * v0**2 + 45.0
    assert ident.mechanical_losses(v0, p0p) == pytest.approx(45.0)


def test_mechanical_losses_from_circuit_points():
    m = _motor()
    p_mec = 60.0
    tests = [_no_load(m, v=v, p_mech=p_mec) for v in (120.0, 160.0, 200.0, 230.0)]
    v0 = np.array([t.v_phase for t in tests])
    p0p = np.array([t.p_total - 3 * m.r1 * t.i_line**2 for t in tests])
    # P_fe = 3E²/Rf, not exactly ∝ V² when R1 ≠ 0: intercept is close, not exact
    assert ident.mechanical_losses(v0, p0p) == pytest.approx(p_mec, abs=1.0)


def test_mechanical_losses_negative_intercept_raises():
    v0 = np.array([100.0, 200.0])
    with pytest.raises(ValueError, match="negative"):
        ident.mechanical_losses(v0, 0.01 * v0**2 - 20.0)


@pytest.mark.parametrize("v0, p", [([230.0], [100.0]), ([230.0, 230.0], [100.0, 100.0]), ([100.0, 200.0], [1.0])])
def test_mechanical_losses_validation(v0, p):
    with pytest.raises(ValueError):
        ident.mechanical_losses(np.array(v0), np.array(p))


# --- no-load test ----------------------------------------------------------------

def test_no_load_td5_classical_is_exact_when_r1_zero():
    m = td5_ex1()
    r_fe, x_m = ident.no_load_branch(_no_load(m), r1=0.0, method="classical")
    assert r_fe == pytest.approx(230.0)
    assert x_m == pytest.approx(46.0)


def test_no_load_exact_with_r1():
    m = _motor()
    r_fe, x_m = ident.no_load_branch(_no_load(m), r1=m.r1, method="exact")
    assert r_fe == pytest.approx(230.0, rel=1e-12)
    assert x_m == pytest.approx(46.0, rel=1e-12)


def test_no_load_exact_with_p_mech_is_close():
    # Residual error = rotor copper loss and rotor reactive power at g0 (≈ g0·p_mec).
    m = _motor()
    t = _no_load(m, p_mech=50.0)
    r_fe, x_m = ident.no_load_branch(t, r1=m.r1, p_mech=50.0, method="exact")
    assert r_fe == pytest.approx(230.0, rel=2e-3)
    assert x_m == pytest.approx(46.0, rel=2e-3)


def test_no_load_classical_with_r1_is_approximate():
    m = _motor()
    r_fe, x_m = ident.no_load_branch(_no_load(m), r1=m.r1, method="classical")
    assert r_fe == pytest.approx(230.0, rel=0.05)
    assert x_m == pytest.approx(46.0, rel=0.05)
    assert x_m != pytest.approx(46.0, rel=1e-6)


def test_no_load_losses_must_exceed_r1_and_mech():
    t = ident.NoLoadTest(v_phase=230, i_line=5.0, p_total=100.0, f=50)
    with pytest.raises(ValueError, match="iron"):
        ident.no_load_branch(t, r1=0.8, p_mech=60.0)


def test_power_factor_above_one_raises():
    with pytest.raises(ValueError, match="power factor"):
        ident.NoLoadTest(v_phase=230, i_line=1.0, p_total=1000.0, f=50)


def test_unknown_method():
    with pytest.raises(ValueError, match="method"):
        ident.no_load_branch(_no_load(td5_ex1()), r1=0.0, method="magic")


# --- locked-rotor test ------------------------------------------------------------

def test_locked_rotor_exact():
    m = _motor()
    r2p, x = ident.locked_rotor(_locked(m), r1=m.r1, r_fe=230.0, x_m=46.0, f_rated=50, method="exact")
    assert r2p == pytest.approx(2.0)
    assert x == pytest.approx(4.0)


def test_locked_rotor_exact_at_other_frequency():
    m = _motor()
    r2p, x = ident.locked_rotor(_locked(m, v=20.0, f=25.0), r1=m.r1, r_fe=230.0, x_m=46.0,
                                f_rated=50, method="exact")
    assert r2p == pytest.approx(2.0)
    assert x == pytest.approx(4.0)  # referred back to 50 Hz


def test_locked_rotor_classical_neglects_magnetising_branch():
    m = _motor()
    t = _locked(m)
    r2p, x = ident.locked_rotor(t, r1=m.r1, f_rated=50, method="classical")
    r_cc = t.p_total / (3 * t.i_line**2)
    z_cc = t.v_phase / t.i_line
    assert r2p == pytest.approx(r_cc - m.r1)
    assert x == pytest.approx(math.sqrt(z_cc**2 - r_cc**2))
    # Zm in parallel lowers the measured impedance: both are underestimated (~13 %)
    assert 1.7 < r2p < 2.0
    assert 3.5 < x < 4.0


def test_locked_rotor_exact_needs_branch():
    with pytest.raises(ValueError, match="r_fe"):
        ident.locked_rotor(_locked(_motor()), r1=0.8, f_rated=50, method="exact")


def test_locked_rotor_r1_too_large():
    m = _motor()
    with pytest.raises(ValueError, match="R'2"):
        ident.locked_rotor(_locked(m), r1=10.0, f_rated=50, method="classical")


# --- full identification ------------------------------------------------------------

def test_identify_exact_roundtrip():
    m = _motor()
    res = ident.identify(
        dc=_dc(m.r1),
        no_load=_no_load(m),
        locked=_locked(m),
        pole_pairs=2,
        method="exact",
        source="TP3",
    )
    for name in ("r1", "r2p", "x_leak", "x_m", "r_fe"):
        assert getattr(res, name) == pytest.approx(getattr(m, name)), name
    assert res.v_phase == 230 and res.f_rated == 50 and res.pole_pairs == 2
    assert res.source == "TP3"
    assert circuit.max_torque(res) == pytest.approx(circuit.max_torque(m))


def test_identify_exact_with_p_mech_is_close():
    m = _motor()
    res = ident.identify(dc=_dc(m.r1), no_load=_no_load(m, p_mech=40.0), locked=_locked(m),
                         pole_pairs=2, p_mech=40.0, method="exact")
    for name in ("r2p", "x_leak", "x_m", "r_fe"):
        assert getattr(res, name) == pytest.approx(getattr(m, name), rel=2e-3), name


@pytest.mark.parametrize("method", ["exact", "classical"])
def test_identify_td5(method):
    m = td5_ex1()
    res = ident.identify(dc=None, no_load=_no_load(m), locked=_locked(m),
                         pole_pairs=2, method=method)
    assert res.r1 == 0.0
    assert res.r_fe == pytest.approx(230.0)  # no-load: exact for both when R1 = 0
    assert res.x_m == pytest.approx(46.0)
    if method == "exact":
        assert circuit.breakdown_slip(res) == pytest.approx(0.5)
        assert circuit.max_torque(res) == pytest.approx(126.3, abs=0.05)
    else:
        # magnetising branch neglected at g = 1: g_c 0.47 instead of 0.5
        assert circuit.breakdown_slip(res) == pytest.approx(0.5, rel=0.07)
        assert circuit.max_torque(res) == pytest.approx(126.3, rel=0.1)


def test_identify_demo_flag():
    m = td5_ex1()
    res = ident.identify(dc=None, no_load=_no_load(m), locked=_locked(m),
                         pole_pairs=2, is_demo=True)
    assert res.is_demo


# --- least-squares fit ------------------------------------------------------------

def _points(m, slips=(0.0, 0.02, 0.05, 0.1, 0.3, 1.0)):
    pts = []
    for g in slips:
        v = 40.0 if g == 1.0 else m.v_phase
        op = circuit.operating_point(m, g, v_phase=v)
        pts.append(ident.LoadPoint(v_phase=v, f=m.f_rated, slip=g, i_line=op.i1, p_total=op.p_in))
    return pts


def test_fit_recovers_circuit_from_bad_start():
    m = _motor()
    start = MotorParams(v_phase=230, f_rated=50, pole_pairs=2, r1=m.r1,
                        r2p=3.0, x_leak=6.0, x_m=30.0, r_fe=400.0)
    res = ident.fit_circuit(_points(m), start)
    assert res.success
    for name in ("r2p", "x_leak", "x_m", "r_fe"):
        assert getattr(res.motor, name) == pytest.approx(getattr(m, name), rel=1e-5), name
    assert res.motor.r1 == m.r1
    assert res.rms_relative_error < 1e-6
    assert res.motor.source == "fit"


def test_fit_starting_from_classical_identification():
    m = _motor()
    start = ident.identify(dc=_dc(m.r1), no_load=_no_load(m), locked=_locked(m),
                           pole_pairs=2, method="classical")
    res = ident.fit_circuit(_points(m), start)
    assert res.motor.r2p == pytest.approx(2.0, rel=1e-5)
    assert res.motor.x_leak == pytest.approx(4.0, rel=1e-5)


def test_fit_corrects_p_mech_residual():
    m = _motor()
    nl = _no_load(m, p_mech=40.0)
    start = ident.identify(dc=_dc(m.r1), no_load=nl, locked=_locked(m),
                           pole_pairs=2, p_mech=40.0)
    res = ident.fit_circuit(_points(m), start)
    for name in ("r2p", "x_leak", "x_m", "r_fe"):
        assert getattr(res.motor, name) == pytest.approx(getattr(m, name), rel=1e-6), name


def test_fit_with_noise_stays_close():
    m = _motor()
    rng = np.random.default_rng(0)
    pts = [ident.LoadPoint(v_phase=p.v_phase, f=p.f, slip=p.slip,
                           i_line=p.i_line * (1 + 0.005 * rng.standard_normal()),
                           p_total=p.p_total * (1 + 0.005 * rng.standard_normal()))
           for p in _points(m, slips=np.linspace(0, 1, 15))]
    res = ident.fit_circuit(pts, m)
    assert res.motor.r2p == pytest.approx(2.0, rel=0.05)
    assert res.motor.x_leak == pytest.approx(4.0, rel=0.05)
    assert 0 < res.rms_relative_error < 0.02


def test_fit_needs_enough_points():
    m = _motor()
    with pytest.raises(ValueError, match="at least"):
        ident.fit_circuit(_points(m, slips=(0.02,)), m)


def test_load_point_validation():
    with pytest.raises(ValueError, match="i_line"):
        ident.LoadPoint(v_phase=230, f=50, slip=0.02, i_line=0.0, p_total=100.0)
    with pytest.raises(ValueError, match="slip"):
        ident.LoadPoint(v_phase=230, f=50, slip=math.nan, i_line=1.0, p_total=100.0)


# --- terminals layout ----------------------------------------------------------------

def _motor_terminals(r1=0.8):
    return replace(_motor(r1), layout="terminals")


def test_no_load_exact_terminals_does_not_subtract_r1_loss():
    m = _motor_terminals()
    t = _no_load(m)
    # terminals layout: R1 carries no current at g = 0, P0 = P_fe exactly
    assert t.p_total == pytest.approx(3 * 230**2 / 230)
    r_fe, x_m = ident.no_load_branch(t, r1=m.r1, method="exact", layout="terminals")
    assert r_fe == pytest.approx(230.0, rel=1e-12)
    assert x_m == pytest.approx(46.0, rel=1e-12)


def test_locked_rotor_exact_terminals():
    m = _motor_terminals()
    r2p, x = ident.locked_rotor(_locked(m), r1=m.r1, f_rated=50, r_fe=230.0, x_m=46.0,
                                method="exact", layout="terminals")
    assert r2p == pytest.approx(2.0, rel=1e-12)
    assert x == pytest.approx(4.0, rel=1e-12)


def test_identify_exact_terminals_roundtrip():
    m = _motor_terminals()
    res = ident.identify(dc=_dc(m.r1), no_load=_no_load(m), locked=_locked(m),
                         pole_pairs=2, method="exact", layout="terminals")
    assert res.layout == "terminals"
    for name in ("r1", "r2p", "x_leak", "x_m", "r_fe"):
        assert getattr(res, name) == pytest.approx(getattr(m, name), rel=1e-12), name


def test_wrong_layout_gives_wrong_circuit():
    # data from a TP3 motor identified with the terminals formulas: R'2 is off
    m = _motor(0.8)
    res = ident.identify(dc=_dc(m.r1), no_load=_no_load(m), locked=_locked(m),
                         pole_pairs=2, method="exact", layout="terminals")
    assert res.r2p != pytest.approx(2.0, rel=1e-3)


def test_fit_keeps_layout_of_start():
    m = _motor_terminals()
    start = replace(m, r2p=3.0, x_leak=6.0, x_m=30.0, r_fe=400.0)
    res = ident.fit_circuit(_points(m), start)
    assert res.motor.layout == "terminals"
    assert res.motor.r2p == pytest.approx(2.0, rel=1e-6)


def test_bad_layout():
    with pytest.raises(ValueError, match="layout"):
        ident.no_load_branch(_no_load(td5_ex1()), r1=0.0, layout="star")


# --- full chain on generated bench records (tests/fixtures/td5_records.py) ----------

from fixtures.td5_records import (  # noqa: E402
    CASE_A, CASE_B, LOCKED_FRACTION, PARAMS, T_COLD, T_HOT, error_table, format_table, make_records,
)


def test_r1_cold_to_hot():
    r_cold = 0.411
    r_hot = ident.r1_at_temperature(r_cold, T_COLD, T_HOT)
    assert r_hot == pytest.approx(r_cold * (234.5 + 75.0) / (234.5 + 20.0))
    # same as going through R20 with R(T) = R20·(234.5 + T)/254.5
    assert r_hot == pytest.approx(circuit.copper_resistance(r_cold, T_HOT))
    assert ident.r1_at_temperature(1.0, 313.15, 293.15) == pytest.approx(254.5 / 274.5)


@pytest.mark.parametrize("args", [(0.0, 293.15, 348.15), (-1.0, 293.15, 348.15),
                                  (1.0, 0.0, 348.15), (1.0, 293.15, math.nan)])
def test_r1_at_temperature_validation(args):
    with pytest.raises(ValueError):
        ident.r1_at_temperature(*args)


def test_no_hot_temperature_means_no_correction():
    rec = replace(make_records(CASE_B), t_hot_k=None)  # TD5 style: "hot resistance" measured directly
    rep = ident.run_identification(rec)
    assert rep.r1_hot == rep.r1_cold == pytest.approx(CASE_B.motor.r1 * 254.5 / 309.5)


def test_from_line_divides_by_sqrt3():
    t = ident.NoLoadTest.from_line(u_line=380.0, i_line=3.7, p_total=350.0, f=50.0)
    assert t.v_phase == pytest.approx(380.0 / math.sqrt(3))
    t = ident.LockedRotorTest.from_line(u_line=87.4, i_line=6.9, p_total=370.0, f=50.0)
    assert t.v_phase == pytest.approx(87.4 / math.sqrt(3))


def test_case_a_records_are_td5():
    rec = make_records(CASE_A)
    assert rec.dc is None and rec.p_mech == 0.0
    rated = rec.rated_no_load()
    assert rated.v_phase == pytest.approx(230.0)
    assert rated.p_total == pytest.approx(3 * 230**2 / 230)  # P0 = iron losses only


@pytest.mark.parametrize("case", [CASE_A, CASE_B], ids=["A", "B"])
def test_noise_free_exact_within_1pct(case):
    rep = ident.run_identification(make_records(case), method="exact")
    for name, ref, got, err in error_table(case.motor, rep.motor):
        if err is None:
            assert got == pytest.approx(ref, abs=1e-9), name
        else:
            assert abs(err) < 1.0, f"{name}: {err:+.3f} %"


def test_noise_free_classical_case_a():
    m = CASE_A.motor
    rep = ident.run_identification(make_records(CASE_A), method="classical")
    # no-load: exact when R1 = 0
    assert rep.motor.r_fe == pytest.approx(m.r_fe, rel=1e-9)
    assert rep.motor.x_m == pytest.approx(m.x_m, rel=1e-9)
    # locked rotor: the classical formula reads Zcc = R'2 + jX, but the measured
    # Zcc also contains Zm in parallel. Its error is that of the formula itself:
    z_cc = circuit.impedance(m, 1.0, v_phase=LOCKED_FRACTION * m.v_phase)
    assert rep.motor.r2p == pytest.approx(z_cc.real - m.r1, rel=1e-9)
    assert rep.motor.x_leak == pytest.approx(z_cc.imag, rel=1e-9)
    assert rep.motor.r2p < m.r2p and rep.motor.x_leak < m.x_leak


def test_noise_free_classical_case_b():
    m = CASE_B.motor
    rep = ident.run_identification(make_records(CASE_B), method="classical")
    assert rep.r1_cold == pytest.approx(m.r1 * 254.5 / 309.5)
    assert rep.motor.r1 == pytest.approx(m.r1, rel=1e-12)  # hot R1 recovered
    assert rep.p_mech == pytest.approx(CASE_B.p_mech, rel=0.05)
    assert rep.motor.r_fe == pytest.approx(m.r_fe, rel=0.01)
    assert rep.motor.x_m == pytest.approx(m.x_m, rel=0.01)
    assert rep.motor.is_demo is False  # the chain does not know; the caller labels it


def test_report_contents():
    rep = ident.run_identification(make_records(CASE_B))
    assert rep.method == "exact"
    assert 0 < rep.cos_phi0 < rep.cos_phi_cc < 1
    assert rep.p_fe == pytest.approx(3 * rep.e0**2 / rep.motor.r_fe)
    assert rep.n_no_load == 8


@pytest.mark.parametrize("method", ["classical", "exact"])
@pytest.mark.parametrize("case", [CASE_A, CASE_B], ids=["A", "B"])
def test_noisy_records_report_errors(case, method):
    """2 % Gaussian noise on every measured value, fixed seed: errors are reported, not asserted."""
    rec = make_records(case, noise=0.02, seed=2026)
    rep = ident.run_identification(rec, method=method)
    rows = error_table(case.motor, rep.motor)
    print("\n" + format_table(f"{case.name} — {method}, 2 % noise, seed 2026", rows))
    for name, ref, got, err in rows:
        assert math.isfinite(got) and got >= 0, name
    # deterministic with a fixed seed
    again = ident.run_identification(make_records(case, noise=0.02, seed=2026), method=method)
    assert again.motor == rep.motor


# --- bad inputs ------------------------------------------------------------------

@pytest.mark.parametrize("cls", [ident.NoLoadTest, ident.LockedRotorTest])
@pytest.mark.parametrize("kw", [dict(p_total=-100.0), dict(i_line=0.0), dict(u_line=0.0),
                                dict(i_line=-2.0), dict(f=0.0), dict(p_total=math.nan)])
def test_bad_records(cls, kw):
    args = dict(u_line=380.0, i_line=3.7, p_total=350.0, f=50.0) | kw
    with pytest.raises(ValueError):
        cls.from_line(**args)


@pytest.mark.parametrize("kw", [dict(i_dc=0.0), dict(v_dc=-1.0), dict(temperature_k=-5.0)])
def test_bad_dc(kw):
    with pytest.raises(ValueError):
        ident.DcTest(**(dict(v_dc=4.0, i_dc=5.0) | kw))


def test_records_validation():
    rec = make_records(CASE_B)
    with pytest.raises(ValueError, match="no-load"):
        replace(rec, no_load=())
    with pytest.raises(ValueError, match="distinct"):
        ident.run_identification(replace(rec, no_load=rec.no_load[-2:-1]))  # p_mech=None needs a series
    with pytest.raises(ValueError, match="rated"):
        replace(rec, v_rated=290.0)  # closest point 253 V: more than 10 % away
    with pytest.raises(ValueError, match="t_hot_k"):
        replace(rec, t_hot_k=-1.0)
    with pytest.raises(ValueError, match="p_mech"):
        replace(rec, p_mech=-1.0)
