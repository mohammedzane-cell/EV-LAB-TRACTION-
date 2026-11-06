"""Tab 6 · Bobinage (pytest-qt, offscreen): slot strip, kw table, spectrum, animation, errors."""

import numpy as np
import pytest
from PySide6.QtCore import Qt

from evlab.core import winding as wd
from evlab.gui.main_window import MainWindow


@pytest.fixture
def tab(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    t = w.tabs.widget(5)
    assert t.title == "6 · Bobinage"
    return t


def test_defaults_and_strip(tab):
    w = tab.winding
    assert (w.z, w.poles, w.m, w.y) == (36, 4, 3, 7)
    assert tab.strip.columnCount() == 36 and tab.strip.rowCount() == 2
    table = wd.slot_table(w)
    for s in range(36):
        top, bottom = table[s].labels()
        assert tab.strip.item(0, s).text() == top  # text labels, not colour only
        assert tab.strip.item(1, s).text() == bottom
    assert tab.strip.item(0, 0).background().color().name() == "#f4a6a6"  # phase A
    assert "q = 3" in tab.lbl_geom.text() and "τ = 9" in tab.lbl_geom.text()


def test_kw_table_full_vs_chosen_pitch(tab):
    assert tab.kw_table.horizontalHeaderItem(3).text() == "kw (y = 9)"
    assert tab.kw_table.horizontalHeaderItem(5).text() == "kw (y = 7)"
    expected = {1: (0.9598, 0.9019), 5: (0.2176, -0.0378), 7: (0.1774, -0.1359)}
    for r in range(3):
        nu = int(tab.kw_table.item(r, 0).text())
        full = tab.kw_table.item(r, 3).data(Qt.ItemDataRole.UserRole)
        short = tab.kw_table.item(r, 5).data(Qt.ItemDataRole.UserRole)
        assert (full, short) == pytest.approx(expected[nu], abs=1e-4)
    assert tab.kw_table.item(1, 5).text() == "−0,0378"


def test_spectrum_is_the_core_fft(tab):
    w = tab.winding
    _, f_a = wd.phase_mmf(w, "A", w.z * 32 * 4)
    assert tab.spectra["short"] == wd.mmf_spectrum(w, f_a, 25)
    bars = [i for i in tab.plot_spec.getPlotItem().items if hasattr(i, "opts") and "height" in i.opts]
    assert len(bars) == 2


def test_animation_play_pause_and_frames(qtbot, tab):
    assert not tab.timer.isActive()
    qtbot.mouseClick(tab.btn_play, Qt.MouseButton.LeftButton)
    assert tab.timer.isActive() and "Pause" in tab.btn_play.text()
    tab.slider.setValue(50)
    assert tab.timer.interval() == 20
    qtbot.waitUntil(lambda: tab.frame >= 2, timeout=5000)
    qtbot.mouseClick(tab.btn_play, Qt.MouseButton.LeftButton)
    assert not tab.timer.isActive()
    k = tab.frame
    stepped, fund = tab.curves["short"]
    rf = tab.fields["short"]
    assert np.allclose(stepped.getData()[1], rf.mmf[k])
    assert np.allclose(fund.getData()[1], rf.fundamental[k])
    tab.next_frame()
    assert tab.frame == (k + 1) % 72


def test_side_by_side_full_and_short_pitch(tab):
    assert tab.fields["full"].mmf.shape == tab.fields["short"].mmf.shape
    assert "y = τ = 9" in tab.plot_full.getPlotItem().titleLabel.text
    assert "y = 7" in tab.plot_short.getPlotItem().titleLabel.text


def test_invalid_winding_reported(tab):
    tab.spin_z.setValue(30)  # q = 2,5
    assert tab.winding is None
    assert "q = Z/(2p·m)" in tab.lbl_error.text()
    tab.spin_z.setValue(36)
    assert tab.winding is not None and tab.lbl_error.text() == ""


def test_pitch_range_follows_tau(tab):
    tab.spin_poles.setValue(6)  # 36/6 = 6 slots per pole, q = 2
    assert tab.spin_y.maximum() == 6
    assert tab.winding.tau == 6 and tab.winding.y <= 6


def test_emf(tab):
    w = tab.winding
    n = wd.turns_per_phase(w, 10.0)
    e = wd.emf(50.0, n, wd.winding_factor(w, 1), 0.01)
    assert f"{e:.4g}".replace(".", ",") in tab.lbl_emf.text()
