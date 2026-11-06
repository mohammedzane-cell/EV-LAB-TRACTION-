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
    # continuous: no jump larger than 2 % of the peak torque between neighbours
    assert np.max(np.abs(np.diff(e.torque))) < 0.02 * e.torque.max()
    assert 0 < e.base_speed <= e.end_constant_power <= e.omega_max
    # limits respected at every point
    assert np.all(e.i1 <= st.i_max * (1 + 1e-9))
    assert np.all(e.torque <= st.margin * e.torque_breakdown * (1 + 1e-9))
    assert np.all(e.slip > 0) and np.all(e.slip <= np.minimum(e.slip_breakdown, 1.0) + 1e-12)
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
    assert not np.any(e.zone() == 2)
    assert e.end_constant_power == pytest.approx(e.base_speed, rel=0.05)


def test_no_field_weakening_when_f_max_is_fn(m):
    e = drive.envelope(m, drive.DriveSettings(i_max=20.0, f_max=50.0))
    assert e.base_speed == e.end_constant_power == e.omega_max
    assert set(np.unique(e.zone())) == {1}


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
