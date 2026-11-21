"""Tab 9 · Labo 3D (pytest-qt): the QML scene loads, the scene follows the winding and the simulated cycle,
every number the scene and the panel show comes from core (angles, SOC, powers, temperatures), the view
controls reach the scene. Offscreen there is no 3D API: the tab says so and keeps working (rendering itself
is checked under Xvfb in test_gui_lab3d_render.py)."""

import math

import numpy as np
import pytest
from PySide6.QtGui import QGuiApplication

from evlab.core import scene3d
from evlab.core import winding as wd
from evlab.gui import main_window as mw
from evlab.gui.format import fr_fixed
from evlab.gui.scene3d_bridge import heat_colour
from evlab.gui.tab_lab3d import FLOW_LINKS, N_MARKERS

TIMEOUT = 60_000


@pytest.fixture
def win(qtbot):
    w = mw.MainWindow()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitUntil(lambda: w.tabs.widget(1).envelope is not None, timeout=TIMEOUT)
    return w


@pytest.fixture
def lab_with_cycle(win, qtbot):
    """Tab 4 simulated, tab 5 computed, tab 9 shown."""
    veh = win.tabs.widget(3)
    with qtbot.waitSignal(veh.simulation_done, timeout=TIMEOUT):
        win.tabs.setCurrentIndex(3)
    th = win.tabs.widget(4)
    with qtbot.waitSignal(th.thermal_done, timeout=TIMEOUT):
        win.tabs.setCurrentIndex(4)
    lab = win.tabs.widget(mw.LAB3D_INDEX)
    win.tabs.setCurrentIndex(mw.LAB3D_INDEX)
    qtbot.waitUntil(lambda: lab.view is not None, timeout=TIMEOUT)
    return win, lab


def test_tab_9_loads_its_qml_scene(win, qtbot):
    lab = win.tabs.widget(mw.LAB3D_INDEX)
    assert lab.title == "9 · Labo 3D" and win.tabs.count() == 9
    assert lab.view is None  # built when first shown
    win.tabs.setCurrentIndex(mw.LAB3D_INDEX)
    qtbot.waitUntil(lambda: lab.view is not None, timeout=TIMEOUT)
    assert lab.view.status().name == "Ready" and lab.view.errors() == []
    root = lab.view.rootObject()
    assert root.objectName() == "lab3dRoot" and root.findChild(type(root), "view3d") is not None
    if QGuiApplication.platformName() == "offscreen":
        assert lab.render_ok is False and lab.lbl_render.isVisibleTo(lab)
        assert "Rendu 3D indisponible" in lab.lbl_render.text()
    # the motor scene: one part per component, the meshes of core.scene3d
    keys = set(lab.bridge.part_keys())
    assert {"stator_core", "winding_A", "winding_B", "winding_C", "rotor_bars", "shaft", "air_gap"} <= keys
    assert "Z = 36 encoches, 2p = 4, pas y = 7" in lab.lbl_scene.text() and "N_r = 28" in lab.lbl_scene.text()
    assert lab.chip_illustrative.isVisibleTo(lab)
    # no cycle yet: the playback waits for tab 4
    assert not lab.btn_play.isEnabled() and "onglet 4" in lab.lbl_frame.text()


def test_the_motor_follows_the_winding_of_tab_6(win, qtbot):
    lab = win.tabs.widget(mw.LAB3D_INDEX)
    t6 = win.tabs.widget(5)
    t6.spin_z.setValue(24)
    qtbot.waitUntil(lambda: lab.winding.z == 24, timeout=TIMEOUT)
    w = lab.winding
    assert lab.parts["stator_core"].facts["n_slots"] == 24
    assert lab.parts["winding_A"].facts["coil_sides"] == 2 * 24 // 3
    assert lab.parts["winding_A"].facts["kw1"] == pytest.approx(float(wd.winding_factor(w, 1)))
    assert f"Z = 24 encoches, 2p = {w.poles}, pas y = {w.y}" in lab.lbl_scene.text()


def test_view_controls_reach_the_scene(win, qtbot):
    lab = win.tabs.widget(mw.LAB3D_INDEX)
    win.tabs.setCurrentIndex(mw.LAB3D_INDEX)
    full_cut = lab.parts["stator_core"].mesh.volume()
    lab.chk_cut.setChecked(False)
    assert lab.parts["stator_core"].mesh.volume() > full_cut  # the quarter is back
    lab.slider_explode.setValue(100)
    assert lab.bridge.explode == 1.0
    lab.group_checks["housing"].setChecked(False)
    assert lab.bridge.visibleGroups["housing"] is False
    lab.chk_labels.setChecked(False)
    assert lab.bridge.labelsVisible is False
    lab.select("rotor_bars")
    assert lab.bridge.selected == "rotor_bars"
    assert "N_r = 28 barres" in lab.lbl_selected.text()
    lab.select("winding_B")
    assert "12 bobines, 24 côtés de bobine" in lab.lbl_selected.text() and "0,9019" in lab.lbl_selected.text()
    lab.select("terminal_box")
    assert "tension simple V = 230 V" in lab.lbl_selected.text()  # the identified motor (tab 1)
    lab.combo_scene.setCurrentIndex(1)
    assert lab.scene_key() == "powertrain" and "battery" in lab.bridge.part_keys()
    assert not lab.chk_cut.isEnabled() and lab.bridge.explode == 0.0
    assert lab.group_pages["powertrain"].isVisibleTo(lab) and not lab.group_pages["motor"].isVisibleTo(lab)


def test_playback_shows_the_simulated_cycle(lab_with_cycle, qtbot):
    win, lab = lab_with_cycle
    sizing, res, cycle, emap, veh = win.tabs.widget(3).result
    batt, th = win.tabs.widget(3).battery_result, win.tabs.widget(4).result
    assert lab.pb is not None and lab.btn_play.isEnabled()
    expected = scene3d.playback(res, cycle, veh, battery=batt, thermal=th, emap=emap)
    assert np.array_equal(lab.pb.angle_motor, expected.angle_motor)
    assert np.array_equal(lab.pb.soc, batt.soc) and np.array_equal(lab.pb.t_winding, expected.t_winding)
    # a traction instant: angles, SOC and readouts are those of core.frame_at
    k = int(np.argmax(res.p_shaft))
    t = float(cycle.t[k])
    lab.seek(t)
    f = scene3d.frame_at(expected, t)
    slow = scene3d.display_slowdown(expected, lab.rate())
    assert lab.slowdown == slow
    assert lab.bridge.angleMotor == pytest.approx(math.degrees(f.angle_motor / slow))
    assert lab.bridge.angleWheel == pytest.approx(math.degrees(f.angle_wheel / slow))
    assert lab.bridge.soc == pytest.approx(f.soc)
    text = lab.lbl_frame.text()
    assert f"v = {fr_fixed(f.v * 3.6, 1)} km/h" in text and f"C arbre = {fr_fixed(f.torque, 1)} N·m" in text
    assert f"SOC = {fr_fixed(100 * f.soc, 1)} %" in text and "traction" in text
    assert f"θ bobinage = {fr_fixed(f.t_winding - 273.15, 1)} °C" in text
    assert "ralenties ÷" in lab.lbl_playback_note.text()
    # powertrain: markers on the links that carry power, in the traction colour
    lab.combo_scene.setCurrentIndex(1)
    lab.seek(t)
    f = scene3d.frame_at(expected, t)
    carrying = [name for _link, name in FLOW_LINKS if scene3d.flow_direction(getattr(f, name)) != 0]
    assert len(carrying) == 4 and len(lab.bridge.particles) == 4 * N_MARKERS
    # temperature colours: the winding takes the colour of its node's temperature
    lab.combo_colours.setCurrentIndex(2)
    lo, hi = lab._scale_limits()
    frac = scene3d.temperature_fraction(f.t_winding, lo, hi)
    assert lab.bridge.material_colour("phase_A") == heat_colour(frac)
    assert "pas un champ" in lab.lbl_scale.text()
    # playing advances the cycle time; leaving the tab pauses
    lab.play()
    qtbot.waitUntil(lambda: lab.t != t, timeout=5000)
    win.tabs.setCurrentIndex(0)
    assert not lab.timer.isActive()


def test_invalid_time_is_refused(lab_with_cycle):
    _win, lab = lab_with_cycle
    with pytest.raises(ValueError):
        lab.seek(lab.pb.t[-1] + 10.0)
