"""Tab 4 · Véhicule & WLTC (pytest-qt, offscreen): sizing, simulation, warning, link to tab 3."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from evlab.core import drive, losses, vehicle
from evlab.gui.format import fr
from evlab.gui.main_window import MainWindow
from evlab.io.cycles import load_cycle

TIMEOUT = 30_000
DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture
def win(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitUntil(lambda: w.tabs.widget(1).envelope is not None, timeout=TIMEOUT)
    return w


@pytest.fixture
def tab(win, qtbot):
    t = win.tabs.widget(3)
    assert t.title == "4 · Véhicule & WLTC"
    with qtbot.waitSignal(t.simulation_done, timeout=TIMEOUT):
        win.tabs.setCurrentIndex(3)  # simulated when shown
    return t


def _core(win, tab, gear=None):
    m, env = win.session.motor, win.tabs.widget(1).envelope
    st = win.tabs.widget(2).settings()
    t, w = losses.default_grid(m, env, st, 120, 90)
    emap = losses.efficiency_map(m, t, w, env.settings, st, envelope=env)
    veh = tab.vehicle()
    cyc = load_cycle(DATA / "cycle_demo.csv")
    sizing = vehicle.size_vehicle(m, env, st, veh, cyc)
    v = replace(veh, gear_ratio=sizing.gear_ratio if gear is None else gear)
    return sizing, vehicle.simulate(cyc, v, m, env, emap, st)


def test_class_ratio_and_kpis_come_from_core(tab, win):
    sizing, res, cycle = tab.result
    exp_sizing, exp = _core(win, tab)
    assert sizing == exp_sizing
    assert res.summary == exp.summary
    assert tab.spin_g.value() == pytest.approx(exp_sizing.gear_ratio, abs=5e-4)
    assert tab.lbl_class.text().startswith(f"Classe WLTC {exp_sizing.wltc_class} ({fr(exp_sizing.pmr)} W/kg")
    assert tab.tiles["whkm"].value.text() == f"{fr(exp.summary.wh_per_km)} Wh/km"
    assert tab.tiles["distance"].value.text() == f"{fr(exp.summary.distance_m / 1000)} km"
    assert "cycle démo utilisé" in tab.lbl_cycle.text()  # no official WLTC file yet
    assert tab.chip_demo.isVisibleTo(tab)
    assert not tab.lbl_warning.isVisibleTo(tab)


def test_long_gear_shows_red_warning(qtbot, tab, win):
    tab.spin_g.setValue(8.0)
    with qtbot.waitSignal(tab.simulation_done, timeout=TIMEOUT) as b:
        tab.simulate()
    _, res, _ = b.args[0]
    assert res.summary.n_outside > 0
    assert tab.lbl_warning.isVisibleTo(tab)
    assert f"{res.summary.n_outside} point(s)" in tab.lbl_warning.text()
    names = [i.name() for i in tab.plot_speed.getPlotItem().listDataItems()]
    assert "hors enveloppe" in names
    with qtbot.waitSignal(tab.simulation_done, timeout=TIMEOUT):
        tab.propose_gear()
    assert not tab.lbl_warning.isVisibleTo(tab)


def test_regen_checkbox(qtbot, tab):
    tab.chk_regen.setChecked(False)
    with qtbot.waitSignal(tab.simulation_done, timeout=TIMEOUT) as b:
        tab.simulate()
    _, res, _ = b.args[0]
    assert res.summary.regen_percent == 0.0 and np.all(res.p_battery >= 0)
    assert tab.tiles["regen"].value.text() == "0,0 %"


def test_cycle_points_sent_to_tab3(tab, win):
    eff = win.tabs.widget(2)
    assert eff.cycle_points is not None and eff.chk_cycle.isEnabled()
    _, res, _ = tab.result
    assert np.allclose(eff.cycle_points[1], res.omega[res.torque > 0])


def test_user_cycle_file(qtbot, tab, tmp_path):
    p = tmp_path / "plat.csv"
    p.write_text("t [s],v [km/h]\n0,0\n20,40\n200,40\n220,0\n", encoding="utf-8")
    with qtbot.waitSignal(tab.simulation_done, timeout=TIMEOUT) as b:
        tab.load_user_cycle(p)
    _, res, cycle = b.args[0]
    assert cycle.name == "plat" and "plat" in tab.lbl_cycle.text()


def test_invalid_cycle_reported(qtbot, tab, win, tmp_path):
    p = tmp_path / "faux.csv"
    p.write_text("t [s],v [km/h]\n0,0\n0,5\n", encoding="utf-8")
    with qtbot.waitSignal(tab.simulation_failed, timeout=TIMEOUT) as b:
        tab.load_user_cycle(p)
    assert "strictement croissant" in b.args[0]
    assert "Échec de la simulation" in win.statusBar().currentMessage()
