"""Layout at laptop and desktop sizes: no overlap, nothing outside its parent, no cut text, legends off the plots."""

import pyqtgraph as pg
import pytest
from PySide6.QtWidgets import QGridLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from evlab.gui import main_window as mw
from evlab.gui.layout_check import layout_problems
from evlab.gui.main_window import MainWindow

TIMEOUT = 120_000
SIZES = [(1100, 650), (1280, 720), (1366, 768), (1920, 1080)]


# --- the checker itself ---------------------------------------------------------------------

def test_checker_finds_overlap_cut_text_and_accepts_a_clean_layout(qtbot):
    clean = QWidget()
    lay = QVBoxLayout(clean)
    lay.addWidget(QLabel("Tension simple"))
    lay.addWidget(QPushButton("Identifier"))
    qtbot.addWidget(clean)
    clean.resize(300, 120)
    clean.show()
    qtbot.wait(50)
    assert layout_problems(clean) == []

    bad = QWidget()
    grid = QGridLayout(bad)
    grid.addWidget(QLabel("premier"), 0, 0)
    grid.addWidget(QLabel("second"), 0, 0)  # same cell: the two labels intersect
    btn = QPushButton("Charger ce design dans tous les onglets")
    btn.setMaximumWidth(60)  # narrower than its text
    grid.addWidget(btn, 1, 0)
    qtbot.addWidget(bad)
    bad.resize(300, 120)
    bad.show()
    qtbot.wait(50)
    probs = layout_problems(bad)
    assert any("chevauche" in p for p in probs)
    assert any("coupé" in p and "Charger ce design" in p for p in probs)


def test_window_sizes_and_maximised_start():
    assert mw.MIN_SIZE == (1100, 650)
    assert mw.opens_maximised(1280, 680)  # 1920×1080 at 150 % minus the task bar
    assert mw.opens_maximised(1366, 728)
    assert not mw.opens_maximised(1920, 1040)


# --- the application, after the demo click path ----------------------------------------------

@pytest.fixture(scope="module")
def win(qapp, request):
    from PySide6.QtCore import QSettings
    import tempfile

    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tempfile.mkdtemp())
    from pytestqt.qtbot import QtBot

    w = MainWindow(theme_name="light")
    w.show()
    bot = QtBot(request)
    bot.waitUntil(lambda: w.tabs.widget(1).envelope is not None, timeout=TIMEOUT)
    t1 = w.tabs.widget(0)
    t1.load_demo()
    t1.radios["both"].setChecked(True)
    with bot.waitSignal(t1.identification_done, timeout=TIMEOUT):
        t1.identify()
    veh, th = w.tabs.widget(3), w.tabs.widget(4)
    with bot.waitSignal(veh.simulation_done, timeout=TIMEOUT):
        w.tabs.setCurrentIndex(3)
    with bot.waitSignal(th.thermal_done, timeout=TIMEOUT):
        w.tabs.setCurrentIndex(4)
    t7 = w.tabs.widget(6)
    w.tabs.setCurrentIndex(6)
    t7.spin_points.setValue(2)
    t7.spin_pop.setValue(3)
    t7.spin_budget.setValue(36)
    t7.spin_workers.setValue(1)
    with bot.waitSignal(t7.pareto_done, timeout=TIMEOUT) as b:
        t7.run()
    t7.select(min(b.args[0].front, key=lambda e: e.wh_per_km))
    yield w, bot
    w.close()


def test_minimum_window_fits_every_tab(win):
    w, _ = win
    assert (w.minimumWidth(), w.minimumHeight()) == mw.MIN_SIZE
    hint = w.minimumSizeHint()
    assert hint.width() <= mw.MIN_SIZE[0] and hint.height() <= mw.MIN_SIZE[1]


@pytest.mark.parametrize("size", SIZES, ids=[f"{a}x{b}" for a, b in SIZES])
def test_no_overlap_nor_cut_text_on_any_tab(win, size):
    w, bot = win
    w.resize(*size)
    bot.wait(200)
    problems = []
    for k in range(w.tabs.count()):
        w.tabs.setCurrentIndex(k)
        bot.wait(150)
        problems += [f"{w.tabs.widget(k).title}: {p}" for p in layout_problems(w.tabs.widget(k))]
    assert problems == []


def test_left_panels_scroll_and_plots_expand(win):
    w, _ = win
    for k in range(w.tabs.count()):
        tab = w.tabs.widget(k)
        panels = [a for a in tab.findChildren(QScrollArea) if a.objectName() == "leftPanel"]
        assert len(panels) == 1, tab.title
        for pw in tab.findChildren(pg.PlotWidget):
            assert pw.minimumHeight() >= 120
            assert pw.sizePolicy().verticalPolicy().name == "Expanding"


def test_legends_are_outside_the_plots_and_list_every_curve(win):
    w, _ = win
    plots = [pw for k in range(w.tabs.count()) for pw in w.tabs.widget(k).findChildren(pg.PlotWidget)]
    with_legend = [pw for pw in plots if pw.getPlotItem().legend is not None]
    assert len(with_legend) >= 8
    for pw in with_legend:
        legend = pw.getPlotItem().legend
        assert not legend.isVisible()  # nothing drawn over the data
        label = pw.legend_label
        names = [lbl.text for _, lbl in legend.items]
        for name in names:
            assert name in label.text()
        # the legend row sits above its plot, in the same box
        assert label.parentWidget() is pw.parentWidget()
        assert label.geometry().bottom() <= pw.geometry().top()
    torque = w.tabs.widget(1).plot_torque.legend_label.text()
    for name in ("couple disponible", "limite courant", "du décrochage"):
        assert name in torque


def test_fem_window_has_no_overlap_at_laptop_size(win):
    w, bot = win
    dlg = w.tabs.widget(5).open_fem()
    dlg.resize(1100, 650)
    dlg.show()
    bot.wait(300)
    assert layout_problems(dlg) == []
    dlg.close()
