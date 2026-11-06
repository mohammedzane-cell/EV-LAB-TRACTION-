"""Tab 6 'Animation FEM' (pytest-qt): works without FEMM; real FEMM run skipped when absent."""

import math
from dataclasses import replace

import numpy as np
import pytest

from evlab.core import winding as wd
from evlab.gui.main_window import MainWindow
from evlab.io import femm_model as fm

FEMM_OK, REASON = fm.femm_available()


@pytest.fixture
def tab(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    return w.tabs.widget(5)


def _fake_result(tmp_path, n=3):
    """FemResult with an analytical-like B_r (no FEMM): tests the viewer only."""
    case = fm.FemCase(n_frames=n, n_gap=360, n_radial=4, n_angular=16)
    cmp_case = replace(case)
    theta, r, th, _ = fm.sample_points(case)
    frames = []
    for k in range(n):
        t = k / (n * case.frequency)
        wt = 2 * math.pi * case.frequency * t
        cur = tuple(case.current * math.cos(wt + wd.PHASE_SHIFT[ph]) for ph in wd.PHASES)
        b_r = -0.6 * np.cos(2 * theta - wt)
        frame = fm.FemFrame(t, cur, theta, b_r, r, th, np.full((4, 16), 0.8))
        frames.append(fm._with_png(frame, case, tmp_path / f"f{k}.png"))
    return fm.FemResult(cmp_case, tuple(frames), 1.0)


def test_tab6_shows_femm_status(tab):
    assert tab.btn_fem.isEnabled()
    assert ("FEMM 4.2 disponible" in tab.lbl_fem.text()) == FEMM_OK


def test_works_without_femm(qtbot, tab, monkeypatch):
    monkeypatch.setattr(fm, "femm_available", lambda: (False, "pyfemm n'est pas installé"))
    dlg = tab.open_fem()
    qtbot.addWidget(dlg)
    assert not dlg.btn_run.isEnabled()
    assert "FEMM indisponible" in dlg.lbl_status.text()
    tab.next_frame()  # the analytical animation of tab 6 is unaffected
    assert tab.frame == 1


def test_viewer_plays_frames(qtbot, tab, tmp_path):
    dlg = tab.open_fem()
    qtbot.addWidget(dlg)
    res = _fake_result(tmp_path)
    with qtbot.waitSignal(dlg.fem_done, timeout=5000):
        dlg.show_result(res)
    assert not dlg.image.pixmap().isNull()
    x, y = dlg.curve_fem.getData()
    assert np.allclose(y, res.frames[0].b_r)
    cmp, curves = fm.analytic_fields(res)
    assert np.allclose(dlg.curve_an.getData()[1], curves[0])
    assert "μ0·F1/(kc·g)" in dlg.lbl_cmp.text() and "Carter" in dlg.lbl_cmp.text()
    dlg.btn_play.setChecked(True)
    qtbot.waitUntil(lambda: dlg.frame >= 1, timeout=5000)
    dlg.btn_play.setChecked(False)


def test_other_winding_is_refused(qtbot, tab):
    tab.spin_poles.setValue(6)
    dlg = tab.open_fem()
    qtbot.addWidget(dlg)
    with qtbot.waitSignal(dlg.fem_failed, timeout=5000) as b:
        assert not dlg.run()
    assert "36 encoches et 4 pôles" in b.args[0]


@pytest.mark.skipif(not FEMM_OK, reason=f"FEMM indisponible : {REASON}")
def test_real_femm_run_from_the_dialog(qtbot, tab):
    dlg = tab.open_fem()
    qtbot.addWidget(dlg)
    dlg.combo_mat.setCurrentIndex(1)  # linear: faster
    dlg.spin_frames.setValue(2)
    with qtbot.waitSignal(dlg.fem_done, timeout=600_000) as b:
        assert dlg.run()
    res = b.args[0]
    assert len(res.frames) == 2 and all(f.png.exists() for f in res.frames)
    assert 0.9 < dlg.comparison.ratio < 1.1
