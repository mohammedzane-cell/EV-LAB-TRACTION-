"""Tab 3 · Rendement (pytest-qt, offscreen): map from the Session motor and tab 2's drive, export, cycle."""

import math

import numpy as np
import pytest

from evlab.core import drive, losses
from evlab.gui.main_window import MainWindow

TIMEOUT = 30_000
RPM = 60 / (2 * math.pi)


@pytest.fixture
def win(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    return w


@pytest.fixture
def tab(win, qtbot):
    t = win.tabs.widget(2)
    assert t.title == "3 · Rendement"
    qtbot.waitUntil(lambda: win.tabs.widget(1).envelope is not None, timeout=TIMEOUT)
    win.tabs.setCurrentIndex(2)  # the map is computed when the tab is shown
    qtbot.waitUntil(lambda: t.emap is not None and t.btn_compute.isEnabled(), timeout=TIMEOUT)
    return t


def test_map_is_the_core_map(tab, win):
    assert tab.envelope is not None  # came from tab 2
    st = tab.settings()
    env = drive.envelope(win.session.motor, tab.drive_settings())
    t, w = losses.default_grid(win.session.motor, env, st, 160, 120)
    exp = losses.efficiency_map(win.session.motor, t, w, tab.drive_settings(), st, envelope=env)
    assert tab.emap.eta.shape == (160, 120)
    assert np.array_equal(np.isnan(tab.emap.eta), np.isnan(exp.eta))
    assert np.allclose(tab.emap.eta, exp.eta, equal_nan=True, rtol=1e-12)
    eta, tb, wb = losses.best_point(exp)
    assert f"{100 * eta:.1f} %".replace(".", ",") in tab.lbl_best.text()


def test_contour_labels_and_overlay(tab):
    texts = [t.get_text() for t in tab.ax.texts]
    assert texts and all(t.endswith(" %") for t in texts)
    labels = [ln.get_label() for ln in tab.ax.get_lines()]
    assert "enveloppe (couple à l'arbre)" in labels
    line = tab.ax.get_lines()[labels.index("enveloppe (couple à l'arbre)")]
    x, y = line.get_data()
    env = tab.emap.envelope
    assert np.allclose(x, env.omega * RPM)
    assert np.allclose(y, losses.shaft_torque_limit(tab.session.motor, env, tab.emap.settings))


def test_settings_change_recomputes(qtbot, tab):
    tab.chk_inv.setChecked(False)
    tab.spin_nt.setValue(40)
    tab.spin_nw.setValue(30)
    with qtbot.waitSignal(tab.map_done, timeout=TIMEOUT) as b:
        tab.compute()
    emap = b.args[0]
    assert emap.eta.shape == (40, 30)
    assert not emap.settings.inverter
    assert np.nanmax(emap.p_inv) == 0.0


def test_export_png(tab, tmp_path):
    path = tmp_path / "carte.png"
    tab.export_png(path)
    assert path.stat().st_size > 10_000
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_cycle_points_toggle(tab):
    assert not tab.chk_cycle.isEnabled()
    tab.set_cycle_points(np.array([20.0, 40.0]), np.array([100.0, 150.0]))
    assert tab.chk_cycle.isEnabled()
    tab.chk_cycle.setChecked(True)
    offsets = [c.get_offsets() for c in tab.ax.collections if c.get_label() == "points du cycle"]
    assert len(offsets) == 1 and np.allclose(offsets[0][:, 0], np.array([100.0, 150.0]) * RPM)
    tab.chk_cycle.setChecked(False)
    assert not [c for c in tab.ax.collections if c.get_label() == "points du cycle"]


def test_new_envelope_from_tab2_is_used(qtbot, win, tab):
    env_tab = win.tabs.widget(1)
    env_tab.spin_imax.setValue(30.0)
    with qtbot.waitSignal(tab.map_done, timeout=TIMEOUT) as b:
        env_tab.compute()
    assert b.args[0].envelope.settings.i_max == 30.0
    assert "30,0 A" in tab.lbl_drive.text()


def test_r1_temperature_needs_a_reference(tab):
    assert tab.session.motor.r1 == 0  # TD5 Ex 1: no correction possible or needed
    assert not tab.spin_tw.isEnabled()
    assert tab.settings().winding_temperature_k is None


def test_hidden_tab_does_not_compute(qtbot, win):
    tab = win.tabs.widget(2)
    qtbot.waitUntil(lambda: win.tabs.widget(1).envelope is not None, timeout=TIMEOUT)
    assert tab.emap is None and tab.stale
    with qtbot.waitSignal(tab.map_done, timeout=TIMEOUT):
        win.tabs.setCurrentIndex(2)
    assert not tab.stale


def test_demo_chip_lists_drive_and_inverter(qtbot, tab, win):
    assert not win.session.motor.is_demo
    assert tab.chip_demo.isVisibleTo(tab)
    tip = tab.chip_demo.toolTip()
    assert "réglages variateur" in tip and "pertes onduleur (A21)" in tip
    with qtbot.waitSignal(tab.map_done, timeout=TIMEOUT):
        tab.chk_inv.setChecked(False)
        tab.compute()
    assert "pertes onduleur" not in tab.chip_demo.toolTip()
