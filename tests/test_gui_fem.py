"""Tab 6 'Animation FEM' (pytest-qt): works without FEMM; real FEMM run skipped when absent."""

import math
from dataclasses import replace

import numpy as np
import pytest

from evlab.core import circuit
from evlab.core import winding as wd
from evlab.gui import fem_view
from evlab.gui.main_window import MainWindow
from evlab.io import femm_model as fm

FEMM_OK, REASON = fm.femm_available()


@pytest.fixture(autouse=True)
def empty_cache(tmp_path, monkeypatch):
    """The tests never read or write the committed data/fem_cache."""
    root = tmp_path / "fem_cache"
    monkeypatch.setattr(fm, "CACHE_DIR", root)
    return root


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


def test_current_is_peak_and_defaults_to_the_magnetising_current(qtbot, tab):
    dlg = tab.open_fem()
    qtbot.addWidget(dlg)
    m = tab.session.motor  # TD5 Ex 1: I_µ = 230/46 = 5 A RMS → 7,07 A peak
    assert dlg.spin_i.value() == pytest.approx(round(fm.peak_from_rms(circuit.magnetising_current(m)), 2))
    assert dlg.spin_i.suffix() == " A crête"
    assert dlg.lbl_i.text() == "7,07 A crête (5,00 A eff)"
    assert "I_µ = V/Xm = 5,00 A eff" in dlg.lbl_imu.text()
    dlg.combo_preset.setCurrentIndex(1)
    assert dlg.spin_i.value() == 6.0 and dlg.lbl_i.text() == "6,00 A crête (4,24 A eff)"
    dlg.combo_preset.setCurrentIndex(2)
    assert dlg.spin_i.value() == 18.0
    assert dlg.lbl_note.text() == fem_view.NOTE and "état magnétisant (à vide)" in fem_view.NOTE
    assert "surexcitation, pas un point en charge" in fem_view.NOTE and "Géométrie démo" in fem_view.NOTE


def test_cache_is_shown_without_femm(qtbot, tab, tmp_path, empty_cache, monkeypatch):
    fm.save_cache(_fake_result(tmp_path, n=6), empty_cache)
    monkeypatch.setattr(fm, "femm_available", lambda: (False, "pyfemm n'est pas installé"))
    dlg = tab.open_fem()
    qtbot.addWidget(dlg)
    assert dlg.result is not None and dlg.result.cached and len(dlg.result.frames) == 6
    assert "Résultats FEM pré-calculés" in dlg.lbl_status.text() and "géométrie démo" in dlg.lbl_status.text()
    assert not dlg.btn_run.isEnabled() and dlg.btn_cache.isEnabled() and dlg.combo_cache.count() == 1
    assert not dlg.image.pixmap().isNull()
    assert np.allclose(dlg.curve_fem.getData()[1], dlg.result.frames[0].b_r)


def test_cache_of_the_current_settings_is_preferred(qtbot, tab, tmp_path, empty_cache, monkeypatch):
    other = _fake_result(tmp_path, n=6)  # 6 A, sorted first
    fm.save_cache(other, empty_cache)
    mine = fm.FemCase(winding=tab.winding, current=7.07, n_frames=12, n_radial=50, n_angular=300)
    theta, r, th, _ = fm.sample_points(mine)
    frames = tuple(fm.FemFrame(mine.frame_time(k), mine.currents(mine.frame_time(k)), theta,
                               -0.7 * np.cos(2 * theta - 2 * math.pi * k / 12), r, th, None) for k in range(12))
    fm.save_cache(fm.FemResult(mine, frames, 1.0, (0, 1)), empty_cache)
    monkeypatch.setattr(fm, "femm_available", lambda: (False, "pyfemm n'est pas installé"))
    dlg = tab.open_fem()
    qtbot.addWidget(dlg)
    assert dlg.combo_cache.count() == 2 and dlg.result.case == mine
    assert "2 résolue(s) par FEMM, 10 déduite(s) par symétrie" in dlg.lbl_status.text()


def test_no_cache_no_femm(qtbot, tab, monkeypatch):
    monkeypatch.setattr(fm, "femm_available", lambda: (False, "pyfemm n'est pas installé"))
    dlg = tab.open_fem()
    qtbot.addWidget(dlg)
    assert dlg.result is None and not dlg.btn_cache.isEnabled()


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
    dlg.spin_frames.setValue(6)  # one frame solved, five from the symmetry
    with qtbot.waitSignal(dlg.fem_done, timeout=600_000) as b:
        assert dlg.run()
    res = b.args[0]
    assert len(res.frames) == 6 and res.solved == (0,) and all(f.png.exists() for f in res.frames)
    assert 0.9 < dlg.comparison.ratio < 1.1
    assert "1 résolue(s) par FEMM, 5 déduite(s) par symétrie" in dlg.lbl_status.text()
    qtbot.waitUntil(lambda: dlg.combo_cache.count() == 1, timeout=5000)  # saved in the (test) cache
    assert fm.load_cache(dlg.combo_cache.currentData()).case == res.case
