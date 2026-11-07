import math
from dataclasses import replace

import numpy as np
import pytest

from evlab.core import circuit, drive
from evlab.core.session import td5_ex1

RPM = 60 / (2 * math.pi)


@pytest.fixture
def m():
    return td5_ex1()


@pytest.fixture
def settings():
    return drive.DriveSettings(i_max=20.0)


def _r1(m, r1=0.5, layout="tp3"):
    return replace(m, r1=r1, layout=layout)


# --- V/f law ---------------------------------------------------------------------

def test_vf_law(m):
    assert drive.vf_voltage(m, 25.0) == pytest.approx(115.0)
    assert drive.vf_voltage(m, 50.0) == pytest.approx(230.0)
    assert drive.vf_voltage(m, 80.0) == 230.0
    assert drive.vf_voltage(m, 25.0, boost=10.0) == pytest.approx(10 + 220 * 0.5)
    assert drive.vf_voltage(m, 50.0, boost=10.0) == pytest.approx(230.0)
    assert drive.vf_voltage(m, np.array([1e-6, 25.0]), boost=10.0)[0] == pytest.approx(10.0, abs=1e-3)
    with pytest.raises(ValueError, match="boost"):
        drive.vf_voltage(m, 10.0, boost=230.0)
    with pytest.raises(ValueError, match="f"):
        drive.vf_voltage(m, 0.0)


# --- breakdown under the law -----------------------------------------------------

@pytest.mark.parametrize("motor", [td5_ex1(), _r1(td5_ex1()), _r1(td5_ex1(), layout="terminals")],
                         ids=["TD5", "R1", "R1-terminals"])
def test_breakdown_at_fn_without_boost_equals_circuit(motor):
    t = drive.breakdown_torque(motor, motor.f_rated)
    assert t == circuit.breakdown(motor, method="closed")[1]  # same closed form, bit for bit
    assert t == pytest.approx(circuit.breakdown(motor)[1], rel=1e-9)  # numeric maximisation


def test_breakdown_times_omega_squared_constant_above_base(m):
    """R1 = 0, V = Vn: T_bd = 3pVn²/(2·X(f)·ω) ∝ 1/f², so T_bd·Ω_s² is constant."""
    f = np.linspace(50.0, 100.0, 51)
    t_bd = drive.breakdown_torque(m, f)
    omega_s = 2 * math.pi * f / m.pole_pairs
    k = t_bd * omega_s**2
    assert np.ptp(k) / k.mean() < 0.01
    # same on the envelope points above base speed
    e = drive.envelope(m, drive.DriveSettings(i_max=20.0))
    above = e.f > m.f_rated
    k = e.torque_breakdown[above] * (2 * math.pi * e.f[above] / m.pole_pairs) ** 2
    assert np.ptp(k) / k.mean() < 0.01


def test_breakdown_torque_constant_below_fn_without_r1(m):
    f = np.linspace(5.0, 50.0, 10)
    t_bd = drive.breakdown_torque(m, f)
    assert np.allclose(t_bd, circuit.breakdown(m)[1], rtol=1e-12)


# --- envelope ----------------------------------------------------------------------

@pytest.mark.parametrize("motor", [td5_ex1(), _r1(td5_ex1())], ids=["TD5", "R1"])
@pytest.mark.parametrize("st", [drive.DriveSettings(i_max=20.0), drive.DriveSettings(i_max=30.0),
                                drive.DriveSettings(i_max=20.0, boost=4.0, margin=0.9, f_max=120.0)],
                         ids=["20A", "30A", "boost"])
def test_envelope_properties(motor, st):
    e = drive.envelope(motor, st)
    assert np.all(e.torque >= 0)
    assert np.all(np.diff(e.omega) > 0)
    assert e.omega[0] == 0.0  # starts at standstill
    # continuous: the largest jump between neighbours shrinks with the grid step
    jump = np.max(np.abs(np.diff(e.torque)))
    fine = drive.envelope(motor, replace(st, n_points=4 * st.n_points))
    assert np.max(np.abs(np.diff(fine.torque))) < 0.4 * jump
    assert jump < 0.03 * e.torque.max()
    assert 0 < e.base_speed <= e.end_constant_power <= e.omega_max
    # limits respected at every point
    assert np.all(e.i1 <= st.i_max * (1 + 1e-9))
    assert np.all(e.torque <= st.margin * e.torque_breakdown * (1 + 1e-9))
    assert np.all(e.slip > 0) and np.all(e.slip <= 1.0) and np.all(e.f <= st.f_max * (1 + 1e-12))
    assert e.binding[-1] == "frequency" and np.all(e.binding[:-1] != "frequency")
    # the torque really is the circuit torque at the operating point
    k = len(e.omega) // 2
    assert e.torque[k] == pytest.approx(circuit.torque(motor, e.slip[k], v_phase=e.v[k], f=e.f[k]))
    assert e.omega[k] == pytest.approx(circuit.mechanical_speed(motor, e.slip[k], f=e.f[k]))
    assert np.allclose(e.power, e.torque * e.omega)
    assert e.omega_max == pytest.approx(2 * math.pi * st.f_max / motor.pole_pairs * (1 - e.slip[-1]))


def test_zones_found_from_the_curve(m, settings):
    e = drive.envelope(m, settings)
    z = e.zone()
    assert set(np.unique(z)) == {1, 2, 3}
    assert np.all(np.diff(z) >= 0)  # 1 → 2 → 3 in speed order
    # the laws behind the zones: T ≈ const, T ∝ 1/Ω, then steeper (breakdown)
    s1 = np.nanmedian(e.slope[(z == 1) & (e.omega > 0)])
    s2 = np.nanmedian(e.slope[z == 2])
    s3 = np.nanmedian(e.slope[z == 3])
    assert abs(s1) < 0.1
    assert -1.4 < s2 < -0.9
    assert s3 < -1.5
    # constant power in zone 2 (within 15 %: TD5 slip changes a lot)
    p2 = e.power[z == 2]
    assert np.ptp(p2) / p2.mean() < 0.15
    # base speed is near the rated synchronous speed under load (f ≈ fn), not imposed
    assert e.f[np.argmin(np.abs(e.omega - e.base_speed))] == pytest.approx(m.f_rated, rel=0.05)


def test_large_current_limit_has_no_constant_power_zone(m):
    e = drive.envelope(m, drive.DriveSettings(i_max=30.0))  # 0,8·T_bd needs ~26 A
    assert np.sum(e.zone() == 2) <= 1
    assert e.end_constant_power == pytest.approx(e.base_speed, rel=0.05)


def test_envelope_is_the_best_torque_at_each_speed(m):
    """No (f, g) pair inside the limits gives more torque at a speed than the envelope."""
    st = drive.DriveSettings(i_max=60.0, margin=1.0)
    e = drive.envelope(m, st)
    om = 1200 / RPM
    t_env = float(e.torque_at(om))
    fr = np.linspace(0.05, 30.0, 3000)
    f = m.pole_pairs * om / (2 * math.pi) + fr
    ok = f <= st.f_max
    f, fr = f[ok], fr[ok]
    g, v = fr / f, drive.vf_voltage(m, f)
    t = circuit.torque(m, g, v_phase=v, f=f)
    feasible = (circuit.stator_current(m, g, v_phase=v, f=f) <= st.i_max) & (t <= circuit.max_torque(m, v_phase=v, f=f))
    assert t[feasible].max() <= t_env * (1 + 1e-6)
    assert t[feasible].max() == pytest.approx(t_env, rel=1e-3)
    # e.g. 50 Hz at g = 0,2 gives 87,1 N·m at 1200 tr/min: the envelope must be above it
    assert t_env > circuit.torque(m, 0.2)


def test_standstill_torque(m):
    e = drive.envelope(m, drive.DriveSettings(i_max=20.0))
    assert e.omega[0] == 0.0 and e.slip[0] == pytest.approx(1.0)
    assert e.torque[0] == pytest.approx(e.torque[1], rel=0.01)


def test_no_field_weakening_when_f_max_is_fn(m):
    e = drive.envelope(m, drive.DriveSettings(i_max=20.0, f_max=50.0))
    assert e.base_speed == e.end_constant_power == e.omega_max
    assert set(np.unique(e.zone())) == {1}
    assert e.f[-1] == pytest.approx(50.0)


def test_boost_raises_starting_torque_with_r1(m):
    mm = _r1(m)
    t0 = drive.envelope(mm, drive.DriveSettings(i_max=20.0)).torque[0]
    t4 = drive.envelope(mm, drive.DriveSettings(i_max=20.0, boost=4.0)).torque[0]
    assert t4 > t0


def test_torque_at_interpolates(m, settings):
    e = drive.envelope(m, settings)
    k = 100
    assert e.torque_at(e.omega[k]) == pytest.approx(e.torque[k])
    assert np.isnan(e.torque_at(e.omega_max * 1.01))


def test_kpis(m, settings):
    e = drive.envelope(m, settings)
    assert e.p_max == pytest.approx(e.power.max())
    assert e.torque_at_max_speed == e.torque[-1]
    assert 1100 < e.base_speed * RPM < 1400


# --- validation -------------------------------------------------------------------

@pytest.mark.parametrize("kw", [dict(i_max=0.0), dict(i_max=20.0, margin=0.0), dict(i_max=20.0, margin=1.2),
                                dict(i_max=20.0, boost=-1.0), dict(i_max=20.0, f_max=0.0),
                                dict(i_max=math.nan), dict(i_max=20.0, n_points=3)])
def test_settings_validation(kw):
    with pytest.raises(ValueError):
        drive.DriveSettings(**kw)


def test_current_limit_below_no_load_current(m):
    with pytest.raises(ValueError, match="no-load current"):
        drive.envelope(m, drive.DriveSettings(i_max=4.0))  # I0 ≈ 5,1 A


# --- démo drive settings (A16) -------------------------------------------------------

def test_demo_settings_are_a16():
    s = drive.demo_settings()
    assert (s.i_max, s.boost, s.margin, s.f_max) == (20.0, 0.0, 0.8, 100.0)
    assert drive.demo_fields(s) == ("i_max", "boost", "margin", "f_max")
    assert drive.demo_settings(n_points=50).n_points == 50


def test_demo_fields_one_flag_per_field():
    s = drive.demo_settings()
    assert drive.demo_fields(replace(s, i_max=35.0)) == ("boost", "margin", "f_max")
    assert drive.demo_fields(replace(s, n_points=50)) == drive.demo_fields(s)  # resolution is not a setting
    assert drive.demo_fields(drive.DriveSettings(i_max=35.0, boost=5.0, margin=0.9, f_max=120.0)) == ()
