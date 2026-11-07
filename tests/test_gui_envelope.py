"""Tab 2 · Enveloppe (pytest-qt, offscreen): envelope from the Session motor, KPIs, motor changes."""

import math
from dataclasses import replace

import pytest

from evlab.core import drive
from evlab.core.session import td5_ex1
from evlab.gui.format import fr, fr_fixed
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
    t = win.tabs.widget(1)
    assert t.title == "2 · Enveloppe"
    if t.envelope is None:  # first computation started at construction
        qtbot.waitSignal(t.envelope_done, timeout=TIMEOUT).wait()
    return t


def test_initial_envelope_uses_session_motor(tab, win):
    expected = drive.envelope(win.session.motor, drive.DriveSettings(i_max=20.0, boost=0.0, margin=0.8, f_max=100.0))
    assert tab.envelope.base_speed == expected.base_speed
    assert tab.envelope.p_max == expected.p_max
    assert tab.tiles["base"].value.text() == f"{fr_fixed(expected.base_speed * RPM, 0)} tr/min"
    assert tab.tiles["end_cp"].value.text() == f"{fr_fixed(expected.end_constant_power * RPM, 0)} tr/min"
    assert tab.tiles["p_max"].value.text() == f"{fr(expected.p_max / 1000)} kW"
    assert tab.tiles["t_vmax"].value.text() == f"{fr(expected.torque_at_max_speed)} N·m"
    assert "TD5 Ex 1" in tab.lbl_motor.text()
    assert "zone 1" in tab.lbl_zones.text() and "zone 3" in tab.lbl_zones.text()


def test_settings_change_recomputes(qtbot, tab, win):
    tab.spin_imax.setValue(30.0)
    tab.spin_margin.setValue(90.0)
    with qtbot.waitSignal(tab.envelope_done, timeout=TIMEOUT) as b:
        qtbot.mouseClick(tab.btn_compute, __import__("PySide6.QtCore").QtCore.Qt.MouseButton.LeftButton)
    env = b.args[0]
    assert env.settings == drive.DriveSettings(i_max=30.0, boost=0.0, margin=0.9, f_max=100.0)
    exp = drive.envelope(win.session.motor, env.settings)
    assert env.torque_at_max_speed == exp.torque_at_max_speed


def test_plots(tab):
    items = tab.plot_torque.getPlotItem().listDataItems()
    names = [i.name() for i in items]
    assert names == ["couple disponible", "limite courant", "80 % du décrochage"]
    x, y = items[0].getData()
    assert y[10] == pytest.approx(tab.envelope.torque[10])
    assert x[10] == pytest.approx(tab.envelope.omega[10] * RPM)


def test_new_motor_from_tab1_is_used(qtbot, win, tab):
    new = replace(td5_ex1(), r1=0.5, source="TP3 · optimisation", is_demo=True)
    win.session.set_motor(new)
    with qtbot.waitSignal(tab.envelope_done, timeout=TIMEOUT) as b:
        win._on_motor_published(new)
    assert b.args[0].p_max == drive.envelope(new, tab.settings()).p_max
    assert "TP3 · optimisation (démo)" in tab.lbl_motor.text()
    assert tab.chip_demo.isVisibleTo(tab)


def test_invalid_current_limit_reported(qtbot, win, tab):
    win.tabs.setCurrentIndex(1)
    tab.spin_imax.setValue(3.0)  # below the no-load current
    with qtbot.waitSignal(tab.envelope_failed, timeout=TIMEOUT) as b:
        tab.compute()
    assert "no-load current" in b.args[0]
    assert "Échec du calcul de l'enveloppe" in win.statusBar().currentMessage()
    assert tab.btn_compute.isEnabled()


def test_demo_chip_follows_the_drive_settings(qtbot, win, tab):
    assert not win.session.motor.is_demo  # TD5 Ex 1: course data
    assert tab.chip_demo.isVisibleTo(tab)  # but i_max, boost, margin, f_max are A16 démo values
    assert "réglages variateur" in tab.chip_demo.toolTip()
    tab.spin_imax.setValue(25.0)
    with qtbot.waitSignal(tab.envelope_done, timeout=TIMEOUT):
        tab.compute()
    assert tab.chip_demo.isVisibleTo(tab) and "I max" not in tab.chip_demo.toolTip()
    tab.spin_boost.setValue(2.0)
    tab.spin_margin.setValue(85.0)
    tab.spin_fmax.setValue(110.0)
    with qtbot.waitSignal(tab.envelope_done, timeout=TIMEOUT):
        tab.compute()
    assert not tab.chip_demo.isVisibleTo(tab)


def test_boost_overflux_warning(qtbot, win, tab):
    assert not tab.lbl_flux.isVisibleTo(tab)  # boost 0: V/f = Vn/fn below fn
    tab.spin_boost.setValue(2.0)
    with qtbot.waitSignal(tab.envelope_done, timeout=TIMEOUT):
        tab.compute()
    assert tab.lbl_flux.isVisibleTo(tab)
    ratio = drive.max_flux_ratio(win.session.motor, 2.0)
    assert fr(ratio) in tab.lbl_flux.text() and "saturation" in tab.lbl_flux.text()


def test_tab1_says_layout_does_not_change_classical_formulas(win):
    t1 = win.tabs.widget(0)
    assert "ne change pas les formules classiques" in t1.lbl_layout_note.text()
