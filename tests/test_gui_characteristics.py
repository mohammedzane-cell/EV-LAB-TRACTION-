"""Tab 2 shows the characteristic points and sensitivities of the session motor exactly as core computes them."""

from evlab.core import characteristics as charac
from evlab.core.session import Session
from evlab.gui.format import fr, fr_fixed
from evlab.gui.tab_envelope import SENS_COLS, SENS_ROWS, EnvelopeTab


def test_characteristics_and_sensitivities_come_from_core(qtbot):
    session = Session()
    tab = EnvelopeTab(session)
    qtbot.addWidget(tab)
    c = charac.characteristics(session.motor)
    s = charac.sensitivity(session.motor)
    assert tab.char_labels["t_max"].text() == f"{fr(c.breakdown_torque)} N·m"
    assert tab.char_labels["t_start"].text() == f"{fr(c.start_torque)} N·m"
    assert tab.char_labels["g_c"].text() == fr(c.breakdown_slip)
    for r, (out, _) in enumerate(SENS_ROWS):
        for col, (par, _) in enumerate(SENS_COLS):
            v = s[out][par]
            v = 0.0 if abs(v) < 0.005 else v
            assert tab.sens_table.item(r, col).text() == fr_fixed(v, 2).replace("-", "−")
    # TD5 Ex 1 (R1 = 0): g_c ∝ R'2/X, so the displayed sensitivities are +1,00 and −1,00
    assert tab.sens_table.item(1, 1).text() == "1,00" and tab.sens_table.item(1, 2).text() == "−1,00"


def test_tab3_average_inverter_model_uses_the_chosen_dc_link(qtbot):
    import numpy as np

    from evlab.core import inverter
    from evlab.gui.tab_efficiency import EfficiencyTab

    tab = EfficiencyTab(Session())
    qtbot.addWidget(tab)
    assert tab.settings().inverter_model == "lineaire" and not tab.spin_vdc.isEnabled()  # baseline by default
    tab.combo_inv_model.setCurrentIndex(1)
    tab.spin_vdc.setValue(400.0)
    st = tab.settings()
    assert st.inverter_model == "moyen" and st.inverter_params.v_dc == 400.0 and st.inverter_params.is_demo
    assert tab.spin_vdc.isEnabled() and not tab.spin_inv0.isEnabled()
    assert "onduleur IGBT moyen" in tab.chip_demo.toolTip()
    with qtbot.waitSignal(tab.map_done, timeout=60_000) as b:
        tab.compute()
    emap = b.args[0]
    assert np.all(emap.v[emap.valid] <= inverter.max_phase_voltage(st.inverter_params) * (1 + 1e-9))


def test_tab4_battery_follows_the_simulated_cycle(qtbot):
    import numpy as np

    from evlab.core import battery
    from evlab.gui.tab_vehicle import VehicleTab

    tab = VehicleTab(Session())
    qtbot.addWidget(tab)
    assert "kWh" in tab.lbl_pack.text() and tab.battery_result is None
    with qtbot.waitSignal(tab.simulation_done, timeout=120_000):
        tab.simulate()
    _s, res, cycle, _mp, _veh = tab.result
    ref = battery.simulate(battery.demo_pack(), res.p_battery, np.diff(cycle.t), 0.9)
    b = tab.battery_result
    assert np.array_equal(b.soc, ref.soc) and np.array_equal(b.current, ref.current)
    assert "SOC 90,0 %" in tab.lbl_battery.text()
    tab.spin_soc0.setValue(60.0)  # inputs of the battery: recomputed without a new cycle simulation
    assert tab.battery_result.soc[0] == 0.6
    assert [tab.cycle_tabs.tabText(k) for k in range(3)] == ["Puissances", "Couple moteur", "Batterie"]


def test_tab4_checks_the_dc_link_voltage(qtbot):
    import numpy as np

    from evlab.core import battery, vehicle
    from evlab.gui.tab_vehicle import VehicleTab

    tab = VehicleTab(Session())
    qtbot.addWidget(tab)
    with qtbot.waitSignal(tab.simulation_done, timeout=120_000):
        tab.simulate()
    _s, res, cycle, emap, _veh = tab.result
    ref = battery.dc_link_check(tab.battery_result, vehicle.phase_voltage(res, emap))
    assert tab.dc_check.short_steps == ref.short_steps == 0
    assert f"marge min {fr(ref.min_margin)} V" in tab.lbl_battery.text()
    assert f"besoin max {fr(float(np.max(ref.required)))} V" in tab.lbl_battery.text()
    with qtbot.waitSignal(tab.battery_done, timeout=10_000):
        tab.spin_soc0.setValue(7.0)  # nearly empty: the pack is below √6·V_ph above base speed
    assert tab.dc_check.short_steps > 0 and "tension du pack insuffisante" in tab.lbl_battery.text()
