"""Tab 5 · Thermique (pytest-qt, offscreen): fed by tab 4, values from core.thermal."""

import numpy as np
import pytest

from evlab.core import thermal
from evlab.gui.format import fr_fixed
from evlab.gui.main_window import MainWindow
from evlab.io.format import power_of_ten

TIMEOUT = 30_000


@pytest.fixture
def win(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitUntil(lambda: w.tabs.widget(1).envelope is not None, timeout=TIMEOUT)
    veh = w.tabs.widget(3)
    with qtbot.waitSignal(veh.simulation_done, timeout=TIMEOUT):
        w.tabs.setCurrentIndex(3)
    return w


@pytest.fixture
def tab(win, qtbot):
    t = win.tabs.widget(4)
    assert t.title == "5 · Thermique"
    with qtbot.waitSignal(t.thermal_done, timeout=TIMEOUT):
        win.tabs.setCurrentIndex(4)
    return t


def test_temperatures_come_from_core(tab, win):
    _, res, _, emap, _ = win.tabs.widget(3).result
    pc, pf = thermal.cycle_losses(res, emap)
    ref = thermal.map_copper_temperature(emap, win.session.motor.r1_temperature_k)
    exp = thermal.simulate(thermal.demo_thermal(), pc, pf, n_cycles=10, copper_ref_k=ref)
    assert np.allclose(tab.result.t_w, exp.t_w)
    s = exp.summary
    assert tab.tiles["t_max"].value.text() == f"{fr_fixed(s.t_max - 273.15, 1)} °C"
    assert tab.tiles["t_mean"].value.text() == f"{fr_fixed(s.t_mean - 273.15, 1)} °C"
    assert tab.tiles["margin"].value.text() == f"{fr_fixed(s.margin, 1)} K"
    assert tab.tiles["life"].value.text() == f"≈ {power_of_ten(thermal.order_of_magnitude(s.life_hours))} h"
    assert tab.chip_demo.isVisibleTo(tab)


def test_plot_has_class_line(tab):
    names = [i.name() for i in tab.plot.getPlotItem().listDataItems()]
    assert names == ["bobinage", "fer / carcasse", "classe F (155 °C)"]
    _, y = tab.plot.getPlotItem().listDataItems()[2].getData()
    assert np.all(y == 155.0)


def test_class_cycles_and_method(qtbot, tab):
    tab.combo_class.setCurrentIndex(list(thermal.INSULATION_CLASSES).index("B"))
    tab.spin_cycles.setValue(3)
    tab.combo_method.setCurrentIndex(1)  # RK45
    with qtbot.waitSignal(tab.thermal_done, timeout=TIMEOUT) as b:
        tab.compute()
    r = b.args[0]
    assert r.method == "rk45" and r.summary.insulation_class == "B"
    assert r.t.size == 3 * (tab.cycle[0].t.size) + 1
    assert "classe B (130 °C)" in [i.name() for i in tab.plot.getPlotItem().listDataItems()]


def test_time_constants_shown(tab):
    fast, slow = thermal.time_constants(thermal.demo_thermal())
    assert tab.lbl_tau.text().startswith("Constantes de temps")
    assert f"{fast / 60:.2f}".replace(".", ",")[:3] in tab.lbl_tau.text()


def test_power_of_ten():
    assert power_of_ten(1e7) == "10⁷" and power_of_ten(1e-2) == "10⁻²"


def test_needs_a_cycle(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    t = w.tabs.widget(4)
    with qtbot.waitSignal(t.thermal_failed, timeout=TIMEOUT) as b:
        t.compute()
    assert "onglet 4" in b.args[0]


def test_r1_zero_chip_follows_the_motor(tab, win):
    from dataclasses import replace

    from evlab.io.notes import R1_ZERO_NOTE

    assert win.session.motor.r1 == 0  # default TD5 Ex 1
    assert tab.chip_r1.isVisibleTo(tab)
    assert tab.chip_r1.text() == R1_ZERO_NOTE
    assert R1_ZERO_NOTE == "R1 ≈ 0 : pas de pertes cuivre stator — lancez l'identification (onglet 1)"
    win.session.set_motor(replace(win.session.motor, r1=0.5, r1_temperature_k=348.15))
    win._on_motor_published(win.session.motor)
    assert not tab.chip_r1.isVisibleTo(tab)


def test_demo_chip_one_flag_per_thermal_field(qtbot, tab):
    assert "réseau thermique C_w, C_s, R_ws, R_sa (A26)" in tab.chip_demo.toolTip()
    assert "quadricycle léger (démo)" in tab.chip_demo.toolTip()  # the cycle's vehicle
    tab.spin_cw.setValue(4000.0)
    with qtbot.waitSignal(tab.thermal_done, timeout=TIMEOUT):
        tab.compute()
    assert tab.chip_demo.isVisibleTo(tab)  # C_s, R_ws, R_sa are still démo
    assert "réseau thermique C_s, R_ws, R_sa (A26)" in tab.chip_demo.toolTip()
