"""Loss map with the average-value inverter model (core.losses + core.inverter): baseline unchanged,
consistency with core.inverter at every point, DC-link limit, power balance."""

import numpy as np
import pytest

from evlab.core import drive, inverter, losses
from evlab.core.session import MotorParams

M = MotorParams(v_phase=230.0, f_rated=50.0, pole_pairs=2, r1=0.5, r2p=2.0, x_leak=4.0, x_m=46.0, r_fe=230.0,
                p_mech=60.0, r1_temperature_k=293.15)
DS = drive.demo_settings()


def _map(st, n=(24, 20)):
    env = drive.envelope(M, DS)
    t, w = losses.default_grid(M, env, st, *n)
    return losses.efficiency_map(M, t, w, DS, st, envelope=env)


def test_default_is_the_linear_baseline():
    a, b = _map(losses.LossSettings()), _map(losses.LossSettings(inverter_model="lineaire"))
    assert np.array_equal(a.valid, b.valid) and np.allclose(a.p_inv, b.p_inv, equal_nan=True)
    assert losses.LossSettings().inverter_model == "lineaire"


def test_average_model_matches_core_inverter_at_every_point():
    st = losses.LossSettings(inverter_model="moyen")
    e = _map(st)
    ip = inverter.demo_inverter()
    ok = e.valid & (e.p_out > 0)
    p_motor = e.p_in - e.p_inv
    cos_phi = p_motor / (3 * e.v * e.i1)  # displacement factor recovered from the map's own powers
    ref = inverter.losses(ip, e.i1[ok], e.v[ok], cos_phi[ok]).total
    assert np.allclose(e.p_inv[ok], ref, rtol=1e-9)
    # power balance of every valid point
    total = e.p_cu1 + e.p_cu2 + e.p_fe + e.p_mech + e.p_inv
    assert np.allclose((e.p_in - e.p_out)[ok], total[ok], rtol=1e-6)
    assert losses.demo_fields(st) == ("beta", "inverter_params")


def test_dc_link_limit_removes_the_points_that_need_more_voltage():
    low = inverter.demo_inverter(v_dc=400.0)  # 400/√6 = 163 V < 230 V
    e = _map(losses.LossSettings(inverter_model="moyen", inverter_params=low))
    v_max = inverter.max_phase_voltage(low)
    assert np.all(e.v[e.valid] <= v_max * (1 + 1e-9))
    full = _map(losses.LossSettings(inverter_model="moyen"))
    assert e.valid.sum() < full.valid.sum()  # the high-speed (field-weakening) part is out of reach


def test_invalid_settings():
    with pytest.raises(ValueError):
        losses.LossSettings(inverter_model="ideal")
    with pytest.raises(ValueError):
        losses.LossSettings(inverter_model="moyen", inverter_params="600 V")
