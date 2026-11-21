"""core/inverter.py against independent computations: numerical integration of the instantaneous device
losses over one fundamental period, and the volt-second balance of SVPWM."""

import math

import numpy as np
import pytest

from evlab.core import inverter as inv

P = inv.demo_inverter()


def _integrated(p, i_rms, v_phase, cos_phi, n=200_000):
    """Average losses of one leg, integrated over θ: upper IGBT + lower diode while i > 0 (the other half is
    symmetric), duty d = (1 + m·sin θ)/2. Independent of the closed forms."""
    m = 2 * math.sqrt(2) * v_phase / p.v_dc
    phi = math.acos(cos_phi)
    th = np.linspace(0, 2 * math.pi, n, endpoint=False)
    d = (1 + m * np.sin(th)) / 2
    i = math.sqrt(2) * i_rms * np.sin(th - phi)
    pos = i > 0
    igbt = np.where(pos, d * (p.v_ce0 * i + p.r_ce * i**2), 0.0).mean()
    diode = np.where(pos, (1 - d) * (p.v_f0 * i + p.r_f * i**2), 0.0).mean()
    sw_t = np.where(pos, p.f_sw * p.e_on_off * i / p.i_ref * p.v_dc / p.v_ref, 0.0).mean()
    sw_d = np.where(pos, p.f_sw * p.e_rr * i / p.i_ref * p.v_dc / p.v_ref, 0.0).mean()
    return igbt, diode, sw_t, sw_d


@pytest.mark.parametrize("i_rms, v_phase, cos_phi", [(10.0, 200.0, 0.85), (25.0, 120.0, 0.3), (5.0, 230.0, 1.0)])
def test_closed_forms_match_the_integration_over_a_period(i_rms, v_phase, cos_phi):
    loss = inv.losses(P, i_rms, v_phase, cos_phi)
    igbt, diode, sw_t, sw_d = _integrated(P, i_rms, v_phase, cos_phi)
    assert loss.conduction_igbt == pytest.approx(6 * igbt, rel=1e-4)
    assert loss.conduction_diode == pytest.approx(6 * diode, rel=1e-4)
    assert loss.switching_igbt == pytest.approx(6 * sw_t, rel=1e-4)
    assert loss.switching_diode == pytest.approx(6 * sw_d, rel=1e-4)
    assert loss.total == pytest.approx(6 * (igbt + diode + sw_t + sw_d), rel=1e-4)


def test_physical_behaviour():
    assert inv.losses(P, 0.0, 200.0, 0.9).total == 0.0  # no current, no loss
    a = inv.losses(P, 10.0, 200.0, 0.9)
    gen = inv.losses(P, 10.0, 200.0, -0.9)  # regenerating: diodes take the conduction
    assert gen.conduction_diode > a.conduction_diode and gen.conduction_igbt < a.conduction_igbt
    assert inv.losses(P, 20.0, 200.0, 0.9).total > a.total  # more current, more loss
    hot = inv.InverterParams(**{**inv.DEMO_A35, "f_sw": 20e3})
    assert inv.losses(hot, 10.0, 200.0, 0.9).switching_igbt == pytest.approx(2 * a.switching_igbt)
    arr = inv.losses(P, np.array([5.0, 10.0]), np.array([100.0, 200.0]), np.array([0.8, 0.9]))
    assert arr.total[1] == pytest.approx(a.total)


def test_dc_link_limit():
    assert inv.max_phase_voltage(P) == pytest.approx(600 / math.sqrt(6))  # 244,9 V: enough for 230 V
    sp = inv.InverterParams(**inv.DEMO_A35, modulation="spwm")
    assert inv.max_phase_voltage(sp) == pytest.approx(600 / (2 * math.sqrt(2)))
    assert inv.modulation_index(P, 230.0) == pytest.approx(2 * math.sqrt(2) * 230 / 600)
    with pytest.raises(ValueError, match="linear range"):
        inv.modulation_index(sp, 230.0)  # 230 V > 212 V: sine PWM cannot reach it on 600 V


@pytest.mark.parametrize("seed", range(5))
def test_svpwm_volt_second_balance(seed):
    rng = np.random.default_rng(seed)
    v_dc, t_s = 600.0, 1e-4
    for _ in range(200):
        r = rng.uniform(0, v_dc / math.sqrt(3))
        a = rng.uniform(0, 2 * math.pi)
        va, vb = r * math.cos(a), r * math.sin(a)
        k, t1, t2, t0 = inv.svpwm(va, vb, v_dc, t_s)
        v1, v2 = inv.active_vector(k, v_dc), inv.active_vector(k % 6 + 1, v_dc)
        assert (t1 * v1[0] + t2 * v2[0]) / t_s == pytest.approx(va, abs=1e-9)
        assert (t1 * v1[1] + t2 * v2[1]) / t_s == pytest.approx(vb, abs=1e-9)
        assert t1 >= -1e-15 and t2 >= -1e-15 and t0 >= 0 and t1 + t2 + t0 == pytest.approx(t_s)


def test_invalid_inputs():
    with pytest.raises(ValueError):
        inv.svpwm(400.0, 0.0, 600.0, 1e-4)  # 400 V > 600/√3 = 346 V
    with pytest.raises(ValueError):
        inv.InverterParams(**{**inv.DEMO_A35, "v_dc": -1.0})
    with pytest.raises(ValueError):
        inv.losses(P, -1.0, 100.0, 0.8)
    with pytest.raises(ValueError):
        inv.losses(P, 1.0, 100.0, 1.5)
    with pytest.raises(ValueError):
        inv.active_vector(7, 600.0)


@pytest.mark.parametrize("modulation", ["svpwm", "spwm"])
def test_required_dc_voltage_is_the_inverse_of_the_linear_range(modulation):
    for v in (50.0, 230.0, 400.0):
        v_dc = inv.required_dc_voltage(v, modulation)
        p = inv.InverterParams(**{**inv.DEMO_A35, "v_dc": v_dc}, modulation=modulation)
        assert inv.max_phase_voltage(p) == pytest.approx(v)
    assert inv.required_dc_voltage(230.0) == pytest.approx(math.sqrt(6) * 230.0)  # 563,4 V
    assert np.allclose(inv.required_dc_voltage(np.array([0.0, 100.0]), "spwm"), [0.0, 200 * math.sqrt(2)])
    with pytest.raises(ValueError):
        inv.required_dc_voltage(-1.0)
    with pytest.raises(ValueError):
        inv.required_dc_voltage(100.0, "sixstep")
