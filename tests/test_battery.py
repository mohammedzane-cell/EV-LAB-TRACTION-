"""core/battery.py: exact current for a power, energy balance, SOC against an adaptive ODE solution,
every limit (current, power ceiling, SOC window), and the link with a real vehicle simulation."""

import math

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from evlab.core import battery as bt

PACK = bt.demo_pack()


def test_pack_values():
    assert PACK.r == pytest.approx(168 * 0.003)
    assert PACK.capacity_c == pytest.approx(10 * 3600)
    assert bt.ocv(PACK, 0.5) == pytest.approx(168 * 3.75)
    assert bt.ocv(PACK, 0.55) == pytest.approx(168 * (3.75 + 3.83) / 2)
    assert 5.8e3 < PACK.energy_wh() < 6.5e3


def test_current_for_power_is_the_exact_root():
    voc, r = 600.0, 0.5
    for p in (10e3, -8e3, 0.0, voc**2 / (4 * r) * 0.999):
        i = bt.current_for_power(voc, r, p)
        assert voc * i - r * i * i == pytest.approx(p, abs=1e-6)
    assert bt.current_for_power(voc, 1e-9, 6e3) == pytest.approx(10.0, rel=1e-6)  # R → 0: I = P/V
    with pytest.raises(ValueError):
        bt.current_for_power(voc, r, voc**2 / (4 * r) * 1.01)


def test_energy_balance_and_soc_by_coulomb_counting():
    rng = np.random.default_rng(1)
    p = rng.uniform(-6e3, 15e3, 600)
    res = bt.simulate(PACK, p, 1.0, 0.8)
    assert np.allclose(res.v_oc * res.current, res.p_terminal + res.p_loss, rtol=1e-12, atol=1e-9)
    assert res.chemical_energy_wh == pytest.approx(res.energy_wh("p_terminal") + res.energy_wh("p_loss"))
    assert res.soc[-1] == pytest.approx(0.8 - np.sum(res.current) / PACK.capacity_c)
    assert np.allclose(res.v_terminal * res.current, res.p_terminal, rtol=1e-9, atol=1e-9)


def test_constant_power_discharge_against_an_adaptive_ode_solution():
    p, soc0, t_end = 8e3, 0.9, 1800.0  # 4 kWh: stays inside the SOC window
    res = bt.simulate(PACK, np.full(int(t_end), p), 1.0, soc0)
    q, r = PACK.capacity_c, PACK.r

    def dsoc(_t, y):
        voc = bt.ocv(PACK, y[0])
        return [-(voc - math.sqrt(voc * voc - 4 * r * p)) / (2 * r) / q]

    ref = solve_ivp(dsoc, (0, t_end), [soc0], rtol=1e-10, atol=1e-12).y[0, -1]
    assert res.soc[-1] == pytest.approx(ref, abs=2e-4)  # explicit 1 s steps vs adaptive RK45


def test_limits_are_applied_and_recorded():
    # discharge beyond the current limit (50 A): reduced, shortfall recorded
    res = bt.simulate(PACK, [60e3], 1.0, 0.5)
    assert res.current[0] == pytest.approx(PACK.i_discharge_max)
    assert res.shortfall[0] == pytest.approx(60e3 - res.p_terminal[0]) and res.shortfall[0] > 0
    # regeneration beyond the charge limit (20 A): reduced, refused power recorded
    res = bt.simulate(PACK, [-30e3], 1.0, 0.5)
    assert res.current[0] == pytest.approx(-PACK.i_charge_max)
    assert res.regen_refused[0] == pytest.approx(res.p_terminal[0] + 30e3) and res.regen_refused[0] > 0
    # full battery: regeneration refused entirely
    res = bt.simulate(PACK, [-5e3], 1.0, PACK.soc_max)
    assert res.current[0] == 0.0 and res.regen_refused[0] == pytest.approx(5e3)
    # empty window: no discharge
    res = bt.simulate(PACK, [5e3], 1.0, PACK.soc_min)
    assert res.current[0] == 0.0 and res.shortfall[0] == pytest.approx(5e3)
    # small demands within limits: nothing refused
    res = bt.simulate(PACK, [5e3, -3e3], 1.0, 0.5)
    assert res.shortfall.sum() == 0 and res.regen_refused.sum() == 0


def test_invalid_inputs():
    with pytest.raises(ValueError):
        bt.simulate(PACK, [1e3], 1.0, 0.99)  # outside the SOC window
    with pytest.raises(ValueError):
        bt.simulate(PACK, [1e3], 0.0, 0.5)
    with pytest.raises(ValueError):
        bt.simulate(PACK, [math.nan], 1.0, 0.5)
    with pytest.raises(ValueError):
        bt.PackParams(cell=bt.DEMO_CELL_A34, n_series=0)
    with pytest.raises(ValueError):
        bt.CellParams(soc=(0, 0.5, 0.4), ocv=(3, 3.5, 4), r_int=0.003, capacity_ah=10, i_discharge_max=50,
                      i_charge_max=20)
    with pytest.raises(ValueError):
        bt.ocv(PACK, 1.2)


def _chain():
    """Motor (TD5 + R1) → drive → loss map → vehicle on the démo cycle."""
    from dataclasses import replace

    from evlab.core import drive, losses, vehicle
    from evlab.core.session import MotorParams
    from evlab.io.cycles import load_cycle
    from evlab.io.paths import data_dir

    m = MotorParams(v_phase=230.0, f_rated=50.0, pole_pairs=2, r1=0.5, r2p=2.0, x_leak=4.0, x_m=46.0,
                    r_fe=230.0, p_mech=60.0, r1_temperature_k=293.15)
    ds, st = drive.demo_settings(), losses.LossSettings()
    env = drive.envelope(m, ds)
    t, w = losses.default_grid(m, env, st, 40, 30)
    emap = losses.efficiency_map(m, t, w, ds, st, envelope=env)
    veh = vehicle.demo_quadricycle()
    cycle = load_cycle(data_dir() / "cycle_demo.csv")
    veh = replace(veh, gear_ratio=vehicle.size_vehicle(m, env, st, veh, cycle).gear_ratio)
    return m, emap, cycle, vehicle.simulate(cycle, veh, m, env, emap, st)


def test_dc_link_voltage_against_the_motor_on_the_cycle():
    """The pack's terminal voltage against √6·V_ph of each step (SVPWM): enough when charged, not when empty."""
    from evlab.core import inverter, vehicle

    m, emap, cycle, res = _chain()
    v_ph = vehicle.phase_voltage(res, emap)
    assert np.all(v_ph <= m.v_phase * (1 + 1e-9)) and v_ph.max() > 0.9 * m.v_phase  # V/f law, capped at Vn
    assert np.all(v_ph[res.omega == 0] == 0)
    dt = np.diff(cycle.t)
    full = bt.simulate(PACK, res.p_battery, dt, 0.9)
    chk = bt.dc_link_check(full, v_ph)
    assert np.allclose(chk.required, math.sqrt(6) * v_ph)
    assert np.allclose(chk.margin, full.v_terminal - inverter.required_dc_voltage(v_ph))
    assert chk.short_steps == 0 and chk.min_margin > 0  # ≈ 685 V of OCV at 90 % for at most 563 V needed
    low = bt.simulate(PACK, res.p_battery, dt, 0.07)  # OCV ≈ 168 × 3,32 V = 557 V < 563 V
    chk_low = bt.dc_link_check(low, v_ph)
    assert chk_low.short_steps > 0 and chk_low.min_margin < 0
    assert chk_low.short_time == pytest.approx(float(np.sum(dt[(chk_low.margin < 0) & (v_ph > 0)])))
    with pytest.raises(ValueError):
        bt.dc_link_check(full, v_ph[:-1])


def test_driven_by_a_real_vehicle_simulation():
    """Motor (TD5 + R1) → drive → loss map → vehicle → battery: the battery sees the vehicle's terminal power."""
    from evlab.core import drive, losses, vehicle
    from evlab.core.session import MotorParams
    from evlab.io.cycles import load_cycle
    from evlab.io.paths import data_dir

    m = MotorParams(v_phase=230.0, f_rated=50.0, pole_pairs=2, r1=0.5, r2p=2.0, x_leak=4.0, x_m=46.0,
                    r_fe=230.0, p_mech=60.0, r1_temperature_k=293.15)
    ds, st = drive.demo_settings(), losses.LossSettings()
    env = drive.envelope(m, ds)
    t, w = losses.default_grid(m, env, st, 40, 30)
    emap = losses.efficiency_map(m, t, w, ds, st, envelope=env)
    from dataclasses import replace

    veh = vehicle.demo_quadricycle()
    cycle = load_cycle(data_dir() / "cycle_demo.csv")
    sizing = vehicle.size_vehicle(m, env, st, veh, cycle)
    veh = replace(veh, gear_ratio=sizing.gear_ratio)
    res = vehicle.simulate(cycle, veh, m, env, emap, st)
    dt = np.diff(cycle.t)
    batt = bt.simulate(PACK, res.p_battery, dt, 0.9)
    assert batt.shortfall.sum() == 0  # the démo pack follows the démo cycle
    assert batt.energy_wh("p_terminal") == pytest.approx(float(np.sum(res.p_battery * dt)) / 3600, rel=1e-9)
    assert batt.soc[-1] < 0.9 and batt.energy_wh("p_loss") > 0
    regen = res.p_battery < 0
    assert regen.any() and np.all(batt.current[regen] < 0)  # regeneration charges the pack
