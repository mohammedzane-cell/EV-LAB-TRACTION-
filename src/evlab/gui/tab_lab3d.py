"""Tab 9 · 3D laboratory: the motor and the powertrain in 3D, driven by the simulated cycle.

Thin view: the meshes, the kinematics, the powers and the temperatures come from core.scene3d (and through it
from the vehicle, battery and thermal results of tabs 4 and 5); this module only lays out the controls,
formats the numbers in French and passes the display state to the QML scene (Qt Quick 3D, part of PySide6).

What the scene is, and is not (shown in the panel):
- the geometry is illustrative (A37): Z, 2p, y and the phase of each coil side come from tab 6, the wheel
  radius and the gear ratio from tab 4; the other lengths are typical proportions, not the identified motor;
- the temperatures are the two averages of the lumped two-node model (tab 5), never a spatial field;
- no electromagnetic field is drawn in 3D (the rotating field is the 2-D animation of tab 6).
"""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, Qt, QTimer, QUrl, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from evlab.core import battery as battery_mod
from evlab.core import scene3d
from evlab.core import thermal as thermal_mod
from evlab.core import vehicle as vehicle_mod
from evlab.core import winding as wd
from evlab.core.session import Session
from evlab.gui import theme
from evlab.gui.format import fr, fr_fixed
from evlab.gui.scene3d_bridge import HEAT_STOPS, SceneBridge
from evlab.gui.widgets import chip, scroll_panel

TITLE = "9 · Labo 3D"
PANEL_WIDTH = 300
TICK_MS = 40  # playback refresh, ms (25 images/s)
T_ZERO_C = 273.15  # K ↔ °C (display only)
RPM = 60.0 / (2.0 * math.pi)  # rad/s → tr/min (display only)
QML_FILE = Path(__file__).with_name("qml") / "lab3d.qml"
SPEEDS = ((1.0, "× 1 (temps réel)"), (5.0, "× 5"), (20.0, "× 20"), (60.0, "× 60"))
N_MARKERS = 5  # power-flow markers per link

SCENES = (("motor", "Moteur asynchrone"), ("powertrain", "Chaîne de traction du véhicule"))
GROUPS = {
    "motor": (("housing", "Carter, flasques, boîte à bornes"), ("stator", "Tôles statoriques"),
              ("winding", "Bobinage (phases A, B, C)"), ("air_gap", "Entrefer"), ("rotor", "Tôles rotoriques"),
              ("cage", "Cage d'écureuil (barres, anneaux)"), ("shaft", "Arbre"), ("bearings", "Roulements")),
    "powertrain": (("battery", "Batterie et jauge de SOC"), ("inverter", "Onduleur"), ("cables", "Câbles DC et AC"),
                   ("motor", "Moteur"), ("gearbox", "Réducteur, différentiel, arbres"), ("wheels", "Roues"),
                   ("chassis", "Châssis")),
}
COLOUR_MODES = (("phases", "Phases A, B, C"), ("materials", "Matériaux"),
                ("thermal", "Températures (2 nœuds)"))
# names of the parts (labels in the scene and title of the selection panel)
NAMES = {
    "housing": "Carter à ailettes", "terminal_box": "Boîte à bornes", "shield_front": "Flasque côté entraînement",
    "shield_back": "Flasque côté opposé", "stator_core": "Tôles statoriques", "winding_A": "Bobinage phase A",
    "winding_B": "Bobinage phase B", "winding_C": "Bobinage phase C", "air_gap": "Entrefer",
    "rotor_core": "Tôles rotoriques", "rotor_bars": "Barres de la cage", "end_rings": "Anneaux de court-circuit",
    "shaft": "Arbre", "bearing_front": "Roulement avant", "bearing_back": "Roulement arrière",
    "chassis": "Châssis", "battery": "Batterie", "battery_soc": "Jauge de SOC", "battery_soc_case": "Jauge de SOC", "inverter": "Onduleur",
    "motor": "Moteur asynchrone", "motor_shaft": "Arbre moteur", "pinion_1": "Pignon d'entrée",
    "gear_1": "Roue intermédiaire", "pinion_2": "Pignon intermédiaire", "gear_2": "Réducteur et différentiel",
    "intermediate_shaft": "Arbre intermédiaire", "differential": "Différentiel", "half_shafts": "Arbres de roue",
    "wheel_fl": "Roue avant gauche (motrice)", "wheel_fr": "Roue avant droite (motrice)",
    "wheel_rl": "Roue arrière gauche", "wheel_rr": "Roue arrière droite", "dc_+": "Câble DC +", "dc_-": "Câble DC −",
    "ac_U": "Câble de phase U", "ac_V": "Câble de phase V", "ac_W": "Câble de phase W",
}
for _k in ("wheel_fl", "wheel_fr", "wheel_rl", "wheel_rr"):
    NAMES[_k + "_rim"] = "Jante — " + NAMES[_k].lower()
LABELLED = {
    "motor": ("housing", "terminal_box", "stator_core", "winding_A", "winding_B", "winding_C", "air_gap",
              "rotor_bars", "end_rings", "shaft", "bearing_front"),
    "powertrain": ("battery", "battery_soc", "inverter", "motor", "gear_2", "half_shafts", "wheel_fl",
                   "dc_+", "ac_V"),
}
FLOW_LINKS = (("dc", "p_dc"), ("ac", "p_ac"), ("shaft", "p_shaft"), ("wheel", "p_wheel"))


class Lab3DTab(QWidget):
    """Tab 9: interactive 3D scenes of the motor and of the powertrain, played along the simulated cycle."""

    status_message = Signal(str)

    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session
        self.title = TITLE
        self.bridge = SceneBridge()
        self.winding = wd.Winding(36, 4, 3, 7)  # until tab 6 publishes its winding
        self.cycle_ctx = None  # (sizing, DriveResult, Cycle, EfficiencyMap, Vehicle) of tab 4
        self.battery: battery_mod.BatteryResult | None = None
        self.thermal: thermal_mod.ThermalResult | None = None
        self.thermal_request = None  # callable: asks tab 5 to compute for the current cycle (set by the window)
        self.pb: scene3d.Playback | None = None
        self.t = 0.0
        self.slowdown = 1.0
        self.flow_phase = {k: 0.0 for k, _ in FLOW_LINKS}
        self.parts: dict[str, scene3d.Part] = {}
        self.paths: dict = {}
        self.frame: scene3d.Frame | None = None
        self.view = None  # QQuickWidget, built when the tab is first shown
        self.render_ok: bool | None = None
        self.timer = QTimer(self)
        self.timer.setInterval(TICK_MS)
        self.timer.timeout.connect(self._tick)
        self.clock = QElapsedTimer()

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.stage = QVBoxLayout()
        self.stage.setContentsMargins(0, 0, 0, 0)
        self.lbl_render = QLabel("")
        self.lbl_render.setWordWrap(True)
        self.lbl_render.setProperty("role", "note")
        self.lbl_render.setVisible(False)
        self.stage.addWidget(self.lbl_render)
        self.placeholder = QLabel("Scène 3D : elle s'affiche à l'ouverture de l'onglet.")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stage.addWidget(self.placeholder, 1)
        stage_w = QWidget()
        stage_w.setLayout(self.stage)
        root.addWidget(stage_w, 1)
        root.addWidget(scroll_panel(self._build_panel()))
        self._build_scene()
        self._update_playback_ui()

    # --- panel ---------------------------------------------------------------------------------

    def _build_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(PANEL_WIDTH)
        lv = QVBoxLayout(panel)
        lv.setContentsMargins(0, 0, 0, 0)

        box = QGroupBox("Scène")
        bl = QVBoxLayout(box)
        self.combo_scene = QComboBox()
        for key, name in SCENES:
            self.combo_scene.addItem(name, key)
        self.combo_scene.currentIndexChanged.connect(self._build_scene)
        bl.addWidget(self.combo_scene)
        self.chip_illustrative = chip("géométrie illustrative", "demo")
        self.chip_illustrative.setToolTip("Cotes typiques, pas celles du moteur identifié (docs/assumptions.md A37)")
        bl.addWidget(self.chip_illustrative)
        self.lbl_scene = QLabel("")
        self.lbl_scene.setWordWrap(True)
        self.lbl_scene.setProperty("role", "muted")
        bl.addWidget(self.lbl_scene)
        lv.addWidget(box)

        box = QGroupBox("Vue")
        form = QFormLayout(box)
        self.slider_explode = QSlider(Qt.Orientation.Horizontal)
        self.slider_explode.setRange(0, 100)
        self.slider_explode.valueChanged.connect(lambda v: self.bridge.set_explode(v / 100.0))
        form.addRow("Vue éclatée", self.slider_explode)
        self.chk_cut = QCheckBox("Coupe (un quart du stator retiré)")
        self.chk_cut.setChecked(True)
        self.chk_cut.toggled.connect(self._build_scene)
        form.addRow(self.chk_cut)
        self.chk_labels = QCheckBox("Étiquettes")
        self.chk_labels.setChecked(True)
        self.chk_labels.toggled.connect(self.bridge.set_labels_visible)
        form.addRow(self.chk_labels)
        self.combo_colours = QComboBox()
        for key, name in COLOUR_MODES:
            self.combo_colours.addItem(name, key)
        self.combo_colours.currentIndexChanged.connect(self._colour_mode_changed)
        form.addRow("Couleurs", self.combo_colours)
        self.lbl_scale = QLabel("")
        self.lbl_scale.setWordWrap(True)
        self.lbl_scale.setProperty("role", "muted")
        form.addRow(self.lbl_scale)
        row = QHBoxLayout()
        for preset, name in (("iso", "3/4"), ("front", "Face"), ("side", "Côté"), ("top", "Dessus")):
            b = QPushButton(name)
            b.setToolTip("Point de vue prédéfini (souris : glisser = tourner, molette = zoom, clic droit = déplacer)")
            b.clicked.connect(lambda _c=False, p=preset: self.bridge.request_camera(p))
            row.addWidget(b)
        form.addRow(row)
        lv.addWidget(box)

        self.box_groups = QGroupBox("Composants")
        gl = QVBoxLayout(self.box_groups)
        self.group_checks: dict[str, QCheckBox] = {}
        self.group_pages: dict[str, QWidget] = {}
        for scene, groups in GROUPS.items():
            page = QWidget()
            pl_ = QVBoxLayout(page)
            pl_.setContentsMargins(0, 0, 0, 0)
            for key, name in groups:
                chk = QCheckBox(name)
                chk.setChecked(True)
                chk.toggled.connect(lambda on, k=key: self.bridge.set_group_visible(k, on))
                pl_.addWidget(chk)
                self.group_checks[key] = chk
            gl.addWidget(page)
            self.group_pages[scene] = page
        lv.addWidget(self.box_groups)

        box = QGroupBox("Sélection (clic sur une pièce)")
        sl = QVBoxLayout(box)
        self.lbl_selected = QLabel("Aucune pièce sélectionnée.")
        self.lbl_selected.setWordWrap(True)
        self.lbl_selected.setTextFormat(Qt.TextFormat.RichText)
        sl.addWidget(self.lbl_selected)
        lv.addWidget(box)
        self.bridge.picked.connect(self._show_selection)

        box = QGroupBox("Lecture du cycle (onglet 4)")
        pl = QVBoxLayout(box)
        row = QHBoxLayout()
        self.btn_play = QPushButton("Lecture")
        self.btn_play.setProperty("role", "primary")
        self.btn_play.clicked.connect(self.toggle_play)
        row.addWidget(self.btn_play)
        self.combo_speed = QComboBox()
        for rate, name in SPEEDS:
            self.combo_speed.addItem(name, rate)
        self.combo_speed.setCurrentIndex(2)
        self.combo_speed.currentIndexChanged.connect(self._speed_changed)
        row.addWidget(self.combo_speed)
        pl.addLayout(row)
        self.slider_t = QSlider(Qt.Orientation.Horizontal)
        self.slider_t.valueChanged.connect(self._seek)
        pl.addWidget(self.slider_t)
        self.lbl_frame = QLabel("")
        self.lbl_frame.setWordWrap(True)
        self.lbl_frame.setTextFormat(Qt.TextFormat.RichText)
        pl.addWidget(self.lbl_frame)
        self.lbl_playback_note = QLabel("")
        self.lbl_playback_note.setWordWrap(True)
        self.lbl_playback_note.setProperty("role", "muted")
        pl.addWidget(self.lbl_playback_note)
        lv.addWidget(box)
        lv.addStretch(1)
        return panel

    # --- QML view (built when first shown) -------------------------------------------------------

    def ensure_view(self) -> bool:
        """Create the Qt Quick 3D view; returns True when the platform renders 3D (RHI graphics API)."""
        if self.view is not None:
            return bool(self.render_ok)
        from PySide6.QtQuick import QSGRendererInterface
        from PySide6.QtQuickWidgets import QQuickWidget

        self.view = QQuickWidget()
        self.view.setObjectName("lab3dView")
        self.view.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self.view.setMinimumSize(320, 240)
        self.view.rootContext().setContextProperty("bridge", self.bridge)
        self.bridge.setParent(self.view)  # deleted after the QML scene that reads it
        self.on_theme_changed()
        self.view.setSource(QUrl.fromLocalFile(str(QML_FILE)))
        errors = [e.toString() for e in self.view.errors()]
        if errors:
            raise RuntimeError("lab3d.qml: " + "; ".join(errors))
        self.stage.replaceWidget(self.placeholder, self.view)
        self.placeholder.hide()
        api = self.view.quickWindow().rendererInterface().graphicsApi()
        self.render_ok = bool(QSGRendererInterface.isApiRhiBased(api))
        if not self.render_ok:
            self.lbl_render.setText("Rendu 3D indisponible sur cette plateforme graphique (rendu logiciel, sans "
                                    "API 3D) : les commandes, la sélection et les valeurs restent actives.")
            self.lbl_render.setVisible(True)
        return self.render_ok

    def showEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().showEvent(event)
        self.ensure_view()
        self._want_thermal()

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().hideEvent(event)
        self.pause()

    def on_theme_changed(self) -> None:
        pal = theme.palette()
        self.bridge.set_theme({"background": pal["plot_bg"], "accent": pal["primary"], "text": pal["text"],
                               "card": pal["card"], "border": pal["border"], "ground": pal["card"]})

    # --- scene content -------------------------------------------------------------------------

    def scene_key(self) -> str:
        return self.combo_scene.currentData()

    def _vehicle(self) -> vehicle_mod.Vehicle:
        return self.cycle_ctx[4] if self.cycle_ctx is not None else vehicle_mod.demo_quadricycle()

    def _pack(self) -> battery_mod.PackParams:
        return self.battery.pack if self.battery is not None else battery_mod.demo_pack()

    def _build_scene(self) -> None:
        scene = self.scene_key()
        g = scene3d.illustrative_geometry(self.winding)
        if scene == "motor":
            parts = scene3d.motor_parts(g, self.winding, cutaway=self.chk_cut.isChecked())
            centre, radius = (0.0, 0.0, 0.0), 0.32
        else:
            lay = scene3d.demo_layout(self._vehicle())
            parts = scene3d.powertrain_parts(lay, g, self._pack())
            self.paths = scene3d.flow_paths(lay, g)
            centre, radius = (0.0, 0.35, 0.0), 1.45
        self.parts = {p.key: p for p in parts}
        labels = {k: NAMES[k] for k in self.parts}
        self.bridge.set_parts(scene, parts, labels, centre, radius, main=set(LABELLED[scene]))
        self.chk_cut.setEnabled(scene == "motor")
        self.slider_explode.setEnabled(scene == "motor")
        if scene != "motor":
            self.slider_explode.setValue(0)
        for key, page in self.group_pages.items():
            page.setVisible(key == scene)
        self._scene_note()
        self._show_selection("")
        if self.pb is not None:
            self._show_frame(advance=0.0)

    def _scene_note(self) -> None:
        w = self.winding
        if self.scene_key() == "motor":
            g = scene3d.illustrative_geometry(w)
            text = (f"Z = {w.z} encoches, 2p = {w.poles}, pas y = {w.y} et phase de chaque côté de bobine : "
                    f"onglet 6. N_r = {g.n_bars} barres (combinaison usuelle). Cotes typiques d'un moteur "
                    f"≈ 5 kW, pas celles du moteur identifié ; entrefer dessiné {fr(g.gap * 1000)} mm (agrandi).")
            if w.pole_pairs != self.session.motor.pole_pairs:
                text += (f" Attention : le bobinage a {w.poles} pôles, le moteur identifié "
                         f"{2 * self.session.motor.pole_pairs}.")
        else:
            veh = self._vehicle()
            lay = scene3d.demo_layout(veh)
            src = "onglet 4" if self.cycle_ctx is not None else "véhicule de démonstration, onglet 4 non simulé"
            text = (f"Rayon de roue {fr(veh.wheel_radius)} m et rapport G = {fr(veh.gear_ratio)} ({src}) ; "
                    f"réducteur dessiné en deux étages de √G = {fr(lay.stage_ratio)}. Empattement, voie et "
                    f"emplacements : disposition illustrative.")
        self.lbl_scene.setText(text)

    def _colour_mode_changed(self) -> None:
        self.bridge.set_colour_mode(self.combo_colours.currentData())
        self._want_thermal()
        self._temperature_scale()

    # --- links with the other tabs -------------------------------------------------------------

    def on_winding(self, w: wd.Winding) -> None:
        """Tab 6 changed the winding: rebuild the motor (Z, 2p, y, slot table)."""
        self.winding = w
        self._build_scene()

    def on_cycle(self, result) -> None:
        """Tab 4 simulated a cycle: (sizing, DriveResult, Cycle, EfficiencyMap, Vehicle)."""
        self.cycle_ctx = result
        self.thermal = None  # a thermal result belongs to one drive result
        self._rebuild_playback()
        if self.scene_key() == "powertrain":
            self._build_scene()
        else:
            self._scene_note()
        self._want_thermal()

    def on_battery(self, b) -> None:
        """Tab 4 recomputed the battery (pack or initial SOC changed)."""
        self.battery = b
        self._rebuild_playback()

    def on_thermal(self, result, drive_result) -> None:
        """Tab 5 finished; accepted when it was computed for the drive result shown here."""
        if self.cycle_ctx is None or drive_result is not self.cycle_ctx[1]:
            return
        self.thermal = result
        self._rebuild_playback()

    def _want_thermal(self) -> None:
        if (self.isVisible() and self.cycle_ctx is not None and self.thermal is None
                and self.combo_colours.currentData() == "thermal" and self.thermal_request is not None):
            self.thermal_request()

    def _rebuild_playback(self) -> None:
        if self.cycle_ctx is None:
            self.pb = None
            self._update_playback_ui()
            return
        _sizing, res, cycle, emap, veh = self.cycle_ctx
        batt = self.battery if self.battery is not None and len(self.battery.soc) == len(cycle.t) else None
        try:
            self.pb = scene3d.playback(res, cycle, veh, battery=batt, thermal=self.thermal, emap=emap)
        except ValueError as exc:  # series of another cycle: shown without them
            self.status_message.emit(f"Labo 3D : {exc}")
            self.pb = scene3d.playback(res, cycle, veh, emap=emap)
        self.t = min(max(self.t, float(self.pb.t[0])), float(self.pb.t[-1]))
        self._update_playback_ui()

    # --- playback -------------------------------------------------------------------------------

    def _update_playback_ui(self) -> None:
        has = self.pb is not None
        for w in (self.btn_play, self.combo_speed, self.slider_t):
            w.setEnabled(has)
        if not has:
            self.lbl_frame.setText("Simulez un cycle dans l'onglet 4 · Véhicule & WLTC : la scène suivra la "
                                   "vitesse, le couple, les puissances, le SOC et les températures du cycle.")
            self.lbl_playback_note.setText("")
            self._temperature_scale()
            return
        self.slider_t.blockSignals(True)
        self.slider_t.setRange(int(self.pb.t[0]), int(math.ceil(self.pb.t[-1])))
        self.slider_t.setValue(int(self.t))
        self.slider_t.blockSignals(False)
        self._speed_changed()
        self._temperature_scale()
        self._show_frame(advance=0.0)

    def rate(self) -> float:
        return float(self.combo_speed.currentData())

    def _speed_changed(self) -> None:
        if self.pb is None:
            return
        self.slowdown = scene3d.display_slowdown(self.pb, self.rate())
        parts = [f"Rotations dessinées ralenties ÷ {fr(self.slowdown)} (rapports de vitesse exacts)."]
        if self.pb.thermal_cycle is not None:
            k, n = self.pb.thermal_cycle
            parts.append(f"Températures : cycle {k} sur {n} du modèle à 2 nœuds (onglet 5).")
        if self.pb.is_demo:
            parts.append("Cycle ou véhicule démo.")
        self.lbl_playback_note.setText(" ".join(parts))

    def toggle_play(self) -> None:
        if self.timer.isActive():
            self.pause()
        else:
            self.play()

    def play(self) -> None:
        if self.pb is None:
            return
        self.clock.start()
        self.timer.start()
        self.btn_play.setText("Pause")

    def pause(self) -> None:
        self.timer.stop()
        self.btn_play.setText("Lecture")

    def _tick(self) -> None:
        dt_screen = self.clock.restart() / 1000.0
        t = self.t + self.rate() * dt_screen
        if t > self.pb.t[-1]:
            t = float(self.pb.t[0])  # loop
        self.t = t
        self.slider_t.blockSignals(True)
        self.slider_t.setValue(int(t))
        self.slider_t.blockSignals(False)
        self._show_frame(advance=dt_screen)

    def _seek(self, value: int) -> None:
        if self.pb is None:
            return
        self.t = min(float(value), float(self.pb.t[-1]))
        self._show_frame(advance=0.0)

    def seek(self, t: float) -> None:
        """Show the scene at time t (s) of the cycle."""
        self.slider_t.setValue(int(t))
        self.t = float(t)
        self._show_frame(advance=0.0)

    def _show_frame(self, advance: float) -> None:
        if self.pb is None:
            return
        f = scene3d.frame_at(self.pb, self.t)
        self.frame = f
        k = self.slowdown
        self.bridge.set_angles(f.angle_motor / k, f.angle_intermediate / k, f.angle_wheel / k)
        if f.soc is not None:
            self.bridge.set_soc(f.soc)
        temps = {}
        if f.t_winding is not None:
            lo, hi = self._scale_limits()
            temps = {"winding": scene3d.temperature_fraction(f.t_winding, lo, hi),
                     "frame": scene3d.temperature_fraction(f.t_frame, lo, hi)}
        self.bridge.set_temperatures(temps)
        self._flow(f, advance)
        self._readouts(f)

    def _flow(self, f: scene3d.Frame, advance: float) -> None:
        if self.scene_key() != "powertrain":
            self.bridge.set_particles([])
            return
        pal = theme.palette()
        items = []
        for link, name in FLOW_LINKS:
            power = getattr(f, name)
            if power is None or scene3d.flow_direction(power) == 0:
                continue
            self.flow_phase[link] = scene3d.advance_flow_phase(self.flow_phase[link], power, self.pb.p_max, advance)
            colour = pal["primary"] if power > 0 else pal["success"]
            fractions = [self.flow_phase[link] + j / N_MARKERS for j in range(N_MARKERS)]
            items += [(p, colour) for p in scene3d.points_along(self.paths[link], fractions)]
        self.bridge.set_particles(items)

    def _readouts(self, f: scene3d.Frame) -> None:
        def kw(p: float | None) -> str:
            return "—" if p is None else f"{fr_fixed(round(p / 1000, 2) + 0.0, 2)} kW"  # no « −0,00 »

        state = "traction" if f.p_shaft > 1 else ("récupération" if f.p_shaft < -1 else "à l'arrêt / roue libre")
        lines = [
            f"<b>t = {fr_fixed(f.t, 0)} s</b> / {fr_fixed(self.pb.t[-1], 0)} s · {state}",
            f"v = {fr_fixed(f.v * 3.6, 1)} km/h · n moteur = {fr_fixed(f.omega_motor * RPM, 0)} tr/min · "
            f"n roues = {fr_fixed(f.omega_wheel * RPM, 0)} tr/min",
            f"C arbre = {fr_fixed(f.torque, 1)} N·m",
            f"P batterie = {kw(f.p_battery)} · P DC onduleur = {kw(f.p_dc)}",
            f"P AC moteur = {kw(f.p_ac)} · P arbre = {kw(f.p_shaft)}",
            f"P roues (moteur) = {kw(f.p_wheel)} · freins à friction = {kw(f.p_friction)}",
        ]
        if f.soc is not None:
            lines.append(f"SOC = {fr_fixed(100 * f.soc, 1)} %")
        if f.t_winding is not None:
            lines.append(f"θ bobinage = {fr_fixed(f.t_winding - T_ZERO_C, 1)} °C · θ fer/carcasse = "
                         f"{fr_fixed(f.t_frame - T_ZERO_C, 1)} °C <i>(moyennes, modèle à 2 nœuds)</i>")
        self.lbl_frame.setText("<br>".join(lines))

    def _scale_limits(self) -> tuple[float, float]:
        """Colour scale of the temperatures: ambient (start of the thermal run) → insulation class limit, K."""
        th = self.thermal
        return float(th.t_s[0]), thermal_mod.INSULATION_CLASSES[th.summary.insulation_class] + T_ZERO_C

    def _temperature_scale(self) -> None:
        if self.combo_colours.currentData() != "thermal":
            self.lbl_scale.setText("")
            return
        if self.pb is None or self.pb.t_winding is None:
            self.lbl_scale.setText("Températures : lancez le calcul de l'onglet 5 (demandé automatiquement "
                                   "quand un cycle est simulé). Sans résultat, couleurs des matériaux.")
            return
        lo, hi = self._scale_limits()
        stops = ", ".join(c for _f, c in HEAT_STOPS)
        self.lbl_scale.setText(
            f"<span style='background: qlineargradient(x1:0, x2:1, stop:0 {HEAT_STOPS[0][1]}, "
            f"stop:1 {HEAT_STOPS[-1][1]});'>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</span> "
            f"{fr_fixed(lo - T_ZERO_C, 0)} °C → {fr_fixed(hi - T_ZERO_C, 0)} °C (limite classe "
            f"{self.thermal.summary.insulation_class}). Bobinage = nœud « bobinage », tôles et carter = nœud "
            f"« fer/carcasse » ; rotor sans nœud (couleur matériau). Une seule valeur par nœud : pas un champ.")
        self.lbl_scale.setToolTip(f"Échelle : {stops}")

    # --- selection ---------------------------------------------------------------------------

    def select(self, key: str) -> None:
        """Select a part as a click would."""
        self.bridge.pick(key)

    def _show_selection(self, key: str) -> None:
        if not key or key not in self.parts:
            self.lbl_selected.setText("Aucune pièce sélectionnée. Cliquez une pièce dans la scène.")
            return
        self.lbl_selected.setText(f"<b>{NAMES.get(key, key)}</b><br>" + "<br>".join(self._describe(key)))
        self.status_message.emit(f"Labo 3D : {NAMES.get(key, key)}")

    def _describe(self, key: str) -> list[str]:
        p, w, m = self.parts[key], self.winding, self.session.motor
        facts = p.facts
        f = self.frame if self.pb is not None else None
        out: list[str] = []
        if key.startswith("winding_"):
            out.append(f"{facts['coils']} bobines, {facts['coil_sides']} côtés de bobine (deux couches), "
                       f"q = {facts['q']}, pas y = {facts['y']} encoches ; kw1 = {fr_fixed(facts['kw1'], 4)} "
                       f"(onglet 6).")
            if f is not None and f.t_winding is not None:
                out.append(f"θ bobinage = {fr_fixed(f.t_winding - T_ZERO_C, 1)} °C (moyenne, modèle à 2 nœuds).")
        elif key == "stator_core":
            out.append(f"Z = {facts['n_slots']} encoches (onglet 6). Alésage Ø {fr(2000 * facts['r_bore'])} mm et "
                       f"longueur de fer {fr(1000 * facts['stack'])} mm : cotes illustratives.")
        elif key == "air_gap":
            out.append(f"Dessiné {fr(1000 * facts['gap_drawn'])} mm, agrandi pour être visible (une machine réelle "
                       f"de cette taille : quelques dixièmes de mm). Le champ d'entrefer n'est pas dessiné en 3D : "
                       f"voir l'animation 2-D de l'onglet 6.")
        elif key == "rotor_bars":
            out.append(f"N_r = {facts['n_bars']} barres d'aluminium coulé : combinaison usuelle pour Z = {w.z}, "
                       f"2p = {w.poles} (choix illustratif, A37).")
        elif key in ("rotor_core", "end_rings", "shaft", "motor_shaft"):
            out.append("Tourne avec θm = ∫ωm dt du cycle (onglet 4), dessiné ralenti.")
        elif key == "terminal_box":
            out.append(f"Couplage étoile, tension simple V = {fr(m.v_phase)} V, f = {fr(m.f_rated)} Hz "
                       f"(moteur identifié, onglet 1).")
        elif key == "battery":
            out.append(f"{facts['n_series']} cellules en série × {facts['n_parallel']}, "
                       f"{fr(facts['energy_wh'] / 1000)} kWh, {fr(facts['v_nominal'])} V à 50 % de SOC (onglet 4, "
                       f"cellule démo A34). 12 modules dessinés.")
        elif key == "battery_soc":
            out.append("Hauteur = SOC du comptage coulombien (onglet 4).")
        elif key == "inverter":
            out.append("Onduleur deux niveaux, modèle moyen (onglet 3). Câbles DC depuis la batterie, trois phases "
                       "vers la boîte à bornes.")
        elif key == "motor":
            out.append(f"Le moteur identifié (onglet 1) : {fr(m.v_phase)} V par phase, p = {m.pole_pairs}. "
                       f"Carter illustratif.")
        elif key in ("pinion_1", "gear_1", "pinion_2", "gear_2"):
            veh = self._vehicle()
            out.append(f"Rayon {fr(1000 * facts['radius'])} mm. Rapport global G = {fr(veh.gear_ratio)} (onglet 4), "
                       f"dessiné en deux étages de √G = {fr(math.sqrt(veh.gear_ratio))} (répartition illustrative).")
        elif key.startswith("wheel_"):
            out.append(f"Rayon {fr(self._vehicle().wheel_radius)} m (onglet 4) ; tourne avec θ = ∫v/r dt.")
        elif key in ("differential", "half_shafts", "intermediate_shaft"):
            out.append("Tourne à la vitesse des roues (θm/G) ; l'arbre intermédiaire à −θm/√G.")
        if f is not None and key in ("shaft", "motor_shaft", "rotor_core", "motor"):
            out.append(f"Maintenant : n = {fr_fixed(f.omega_motor * RPM, 0)} tr/min, C = {fr_fixed(f.torque, 1)} N·m.")
        if not out:
            out.append("Pièce de la géométrie illustrative (A37).")
        return out
