"""Tab "4 · Véhicule & WLTC": the vehicle fitted to the Session motor, driven on its WLTC class (core.vehicle).

Thin view: reads the vehicle parameters, runs core.vehicle (sizing + cycle
simulation) in a QThreadPool worker and draws the results. Every number comes
from core/; this module only converts units for display (m/s → km/h, J → Wh,
W → kW, rad → %) and picks which cycle file to load.
"""

from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path

import pyqtgraph as pg
from PySide6.QtCore import QThreadPool, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from evlab.core import drive, losses, vehicle
from evlab.core.session import Session
from evlab.gui.format import fr, fr_fixed
from evlab.gui.widgets import KpiTile, card, chip, french_spin
from evlab.gui.workers import CoreWorker
from evlab.io.cycles import load_cycle, wltc_file
from evlab.io.demo_data import CYCLE_FILE

TITLE = "4 · Véhicule & WLTC"
LEFT_WIDTH = 300
DATA = Path(__file__).resolve().parents[3] / "data"
KMH = 3.6  # m/s → km/h (display only)
DEFAULT_DRIVE = drive.DriveSettings(i_max=20.0)


class VehicleTab(QWidget):
    """Tab 4: vehicle parameters → WLTC class, gear ratio, cycle energy."""

    status_message = Signal(str)
    busy = Signal(bool)
    simulation_done = Signal(object)  # (Sizing, DriveResult, Cycle)
    simulation_failed = Signal(str)
    cycle_points = Signal(object, object)  # motor shaft torque (N·m), speed (rad/s) for tab 3

    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session
        self.title = TITLE
        self.envelope: drive.Envelope | None = None
        self.emap: losses.EfficiencyMap | None = None
        self.loss_settings_provider = losses.LossSettings  # replaced by tab 3's settings()
        self.user_cycle: Path | None = None
        self.result = None
        self.stale = True
        self._worker: CoreWorker | None = None

        root = QHBoxLayout(self)
        left = QWidget()
        left.setFixedWidth(LEFT_WIDTH)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)

        demo = vehicle.demo_quadricycle()
        box = QGroupBox("Véhicule (quadricycle léger, démo)")
        form = QFormLayout(box)
        self.spin_mass = french_spin(50.0, 5e4, 0, "kg", demo.mass)
        self.spin_cxs = french_spin(0.05, 20.0, 3, "m²", demo.cx_s)
        self.spin_crr = french_spin(0.0, 0.1, 4, "", demo.crr)
        self.spin_r = french_spin(0.05, 2.0, 3, "m", demo.wheel_radius)
        self.spin_eta_g = french_spin(50.0, 100.0, 1, "%", 100 * demo.gear_efficiency)
        self.spin_aux = french_spin(0.0, 1e5, 0, "W", demo.aux_power)
        self.spin_grade = french_spin(-30.0, 30.0, 1, "%", 0.0)
        self.spin_g = french_spin(0.1, 50.0, 3, "", demo.gear_ratio)
        self.spin_g.valueChanged.connect(self._g_edited)
        self.btn_propose = QPushButton("Proposer")
        self.btn_propose.setToolTip("Rapport proposé par le dimensionnement (tout le cycle dans l'enveloppe)")
        self.btn_propose.clicked.connect(self.propose_gear)
        self.chk_regen = QCheckBox("Freinage récupératif")
        self.chk_regen.setChecked(True)
        g_row = QHBoxLayout()
        g_row.addWidget(self.spin_g, 1)
        g_row.addWidget(self.btn_propose)
        form.addRow("Masse", self.spin_mass)
        form.addRow("Cx·S", self.spin_cxs)
        form.addRow("Crr", self.spin_crr)
        form.addRow("Rayon de roue", self.spin_r)
        form.addRow("Rendement transmission", self.spin_eta_g)
        form.addRow("Auxiliaires", self.spin_aux)
        form.addRow("Pente", self.spin_grade)
        form.addRow("Rapport G", g_row)
        form.addRow(self.chk_regen)
        lv.addWidget(box)

        cyc = QGroupBox("Classe WLTC et cycle")
        cv = QVBoxLayout(cyc)
        self.lbl_class = QLabel("Classe WLTC : —")
        f = self.lbl_class.font()
        f.setBold(True)
        self.lbl_class.setFont(f)
        self.lbl_cycle = QLabel("Cycle : —")
        self.lbl_cycle.setWordWrap(True)
        self.lbl_gear = QLabel("")
        self.lbl_gear.setWordWrap(True)
        self.lbl_gear.setStyleSheet("color: #555;")
        self.btn_cycle = QPushButton("Charger un cycle CSV…")
        self.btn_cycle.clicked.connect(self._choose_cycle)
        self.btn_class_cycle = QPushButton("Cycle de la classe")
        self.btn_class_cycle.clicked.connect(self.use_class_cycle)
        for w in (self.lbl_class, self.lbl_cycle, self.lbl_gear):
            cv.addWidget(w)
        row = QHBoxLayout()
        row.addWidget(self.btn_cycle)
        row.addWidget(self.btn_class_cycle)
        cv.addLayout(row)
        lv.addWidget(cyc)

        self.btn_simulate = QPushButton("Simuler le cycle")
        self.btn_simulate.setMinimumHeight(34)
        self.btn_simulate.setStyleSheet(
            "QPushButton { background: #2f6fd6; color: white; font-weight: bold; border-radius: 4px; }"
            "QPushButton:disabled { background: #9db7e6; }"
        )
        self.btn_simulate.clicked.connect(self.simulate)
        lv.addWidget(self.btn_simulate)
        lv.addStretch(1)
        root.addWidget(left)

        right = QVBoxLayout()
        self.lbl_warning = QLabel("")
        self.lbl_warning.setWordWrap(True)
        self.lbl_warning.setStyleSheet(
            "QLabel { background: #fde8e7; color: #b3261e; border: 1px solid #b3261e;"
            " border-radius: 4px; padding: 6px; font-weight: bold; }")
        self.lbl_warning.setVisible(False)
        right.addWidget(self.lbl_warning)
        tiles = QHBoxLayout()
        self.tiles = {
            "distance": KpiTile("Distance", "km"),
            "energy": KpiTile("Énergie batterie", "Wh"),
            "whkm": KpiTile("Consommation", "Wh/km"),
            "regen": KpiTile("Récupéré", "%"),
        }
        for t in self.tiles.values():
            tiles.addWidget(t)
        right.addLayout(tiles)
        plot_card, lay, head = card("Cycle : vitesse et puissance batterie")
        self.chip_demo = chip("démo")
        self.chip_demo.setVisible(False)
        head.addWidget(self.chip_demo)
        pg.setConfigOptions(antialias=True, background="w", foreground="#333")
        self.plot_speed = pg.PlotWidget(title="Vitesse du véhicule")
        self.plot_power = pg.PlotWidget(title="Puissance batterie")
        self.plot_power.setXLink(self.plot_speed)
        for pw, ylab in ((self.plot_speed, "Vitesse (km/h)"), (self.plot_power, "Puissance (kW)")):
            pw.setLabel("bottom", "Temps (s)")
            pw.setLabel("left", ylab)
            pw.showGrid(x=True, y=True, alpha=0.25)
            pw.addLegend(offset=(-10, 10))
            lay.addWidget(pw)
        right.addWidget(plot_card, 1)
        root.addLayout(right, 1)
        self._g_from_user = False

    # --- inputs -------------------------------------------------------------------

    def vehicle(self) -> vehicle.Vehicle:
        """Core Vehicle from the fields (raises ValueError)."""
        demo = vehicle.demo_quadricycle()
        values = (self.spin_mass.value(), self.spin_cxs.value(), self.spin_crr.value(), self.spin_r.value(),
                  self.spin_eta_g.value() / 100, self.spin_aux.value())
        is_demo = values == (demo.mass, demo.cx_s, demo.crr, demo.wheel_radius, demo.gear_efficiency, demo.aux_power)
        return vehicle.Vehicle(
            mass=values[0], cx_s=values[1], crr=values[2], wheel_radius=values[3],
            gear_ratio=self.spin_g.value(), gear_efficiency=values[4], aux_power=values[5],
            regen=self.chk_regen.isChecked(), grade=math.atan(self.spin_grade.value() / 100.0),
            name=demo.name if is_demo else "véhicule", is_demo=is_demo,
        )

    def _g_edited(self, _v: float) -> None:
        self._g_from_user = True

    def on_motor_changed(self) -> None:
        self._invalidate()

    def on_envelope(self, env: drive.Envelope) -> None:
        self.envelope = env
        self.emap = None if self.emap is None or self.emap.envelope is not env else self.emap
        self._invalidate()

    def on_map(self, emap: losses.EfficiencyMap) -> None:
        self.emap = emap
        self._invalidate()

    def _invalidate(self) -> None:
        self.stale = True
        if self.isVisible():
            self.simulate()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)
        if self.stale:
            self.simulate()

    def _choose_cycle(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Charger un cycle", str(DATA), "CSV (*.csv)")
        if path:
            self.load_user_cycle(path)

    def load_user_cycle(self, path) -> None:
        """Use this cycle file instead of the one of the WLTC class."""
        self.user_cycle = Path(path)
        self.simulate()

    def use_class_cycle(self) -> None:
        self.user_cycle = None
        self.simulate()

    def propose_gear(self) -> None:
        """Simulate with the gear ratio proposed by core.vehicle.size_vehicle."""
        self._g_from_user = False
        self.simulate()

    # --- computation ----------------------------------------------------------------

    def simulate(self) -> bool:
        """Start sizing + simulation in a pool thread. Returns False if the inputs are refused."""
        try:
            veh = self.vehicle()
            st = self.loss_settings_provider()
        except ValueError as exc:
            msg = f"Paramètres du véhicule invalides : {exc}"
            self.status_message.emit(msg)
            self.simulation_failed.emit(msg)
            return False
        motor = self.session.motor
        env, emap = self.envelope, self.emap
        user_cycle, use_proposed = self.user_cycle, not self._g_from_user
        dst = env.settings if env is not None else DEFAULT_DRIVE

        def job(progress):
            e = env if env is not None else drive.envelope(motor, dst)
            mp = emap if emap is not None and emap.envelope is e else None
            if mp is None:
                t, w = losses.default_grid(motor, e, st, 120, 90)
                mp = losses.efficiency_map(motor, t, w, dst, st, envelope=e)
            cls = vehicle.wltc_class(vehicle.rated_power(motor, e, st) / veh.mass)
            path = user_cycle or wltc_file(DATA, cls) or DATA / CYCLE_FILE
            cycle = load_cycle(path)
            sizing = vehicle.size_vehicle(motor, e, st, veh, cycle)
            v = replace(veh, gear_ratio=sizing.gear_ratio) if use_proposed else veh
            return sizing, vehicle.simulate(cycle, v, motor, e, mp, mp.settings), cycle, v, path

        worker = CoreWorker(job)
        worker.signals.finished.connect(self._on_done)
        worker.signals.failed.connect(self._on_failed)
        self._worker = worker
        self.btn_simulate.setEnabled(False)
        self.busy.emit(True)
        self.status_message.emit("Simulation du cycle…")
        QThreadPool.globalInstance().start(worker)
        return True

    def _on_done(self, out) -> None:
        sizing, res, cycle, veh, path = out
        self.result = (sizing, res, cycle)
        self.stale = False
        self.btn_simulate.setEnabled(True)
        self.busy.emit(False)
        if veh.gear_ratio != self.spin_g.value():
            self.spin_g.blockSignals(True)
            self.spin_g.setValue(veh.gear_ratio)
            self.spin_g.blockSignals(False)
        self.lbl_class.setText(f"Classe WLTC {sizing.wltc_class} ({fr(sizing.pmr)} W/kg, "
                               f"P = {fr(sizing.rated_power / 1000)} kW)")
        official = wltc_file(DATA, sizing.wltc_class)
        note = "" if self.user_cycle or official else \
            f" — fichier WLTC classe {sizing.wltc_class} absent de data/, cycle démo utilisé"
        self.lbl_cycle.setText(f"Cycle : {cycle.name}{note}")
        feas = "toute la courbe dans l'enveloppe" if sizing.feasible else \
            f"aucun rapport ne tient tout le cycle (marge {fr(sizing.min_margin)})"
        self.lbl_gear.setText(f"G proposé {fr(sizing.gear_ratio)} (G max vitesse {fr(sizing.gear_ratio_max)}) : {feas}")
        s = res.summary
        self.tiles["distance"].set_value(fr(s.distance_m / 1000))
        self.tiles["energy"].set_value(fr(s.energy_j / 3600))
        self.tiles["whkm"].set_value(fr(s.wh_per_km))
        self.tiles["regen"].set_value(fr_fixed(s.regen_percent, 1))
        self.lbl_warning.setText(
            f"⚠ {s.n_outside} point(s) du cycle hors de l'enveloppe du moteur (couple ou vitesse insuffisants)"
            if s.n_outside else "")
        self.lbl_warning.setVisible(s.n_outside > 0)
        self.chip_demo.setVisible(cycle.is_demo or veh.is_demo or self.session.motor.is_demo)
        self._draw(res, cycle)
        self.cycle_points.emit(res.torque[res.torque > 0], res.omega[res.torque > 0])
        self.status_message.emit(f"Cycle simulé : {fr(s.wh_per_km)} Wh/km")
        self.simulation_done.emit(self.result)

    def _on_failed(self, message: str) -> None:
        self.btn_simulate.setEnabled(True)
        self.busy.emit(False)
        msg = f"Échec de la simulation : {message}"
        self.status_message.emit(msg)
        self.simulation_failed.emit(msg)

    def _draw(self, res: vehicle.DriveResult, cycle: vehicle.Cycle) -> None:
        self.plot_speed.clear()
        self.plot_power.clear()
        self.plot_speed.plot(cycle.t, cycle.v * KMH, pen=pg.mkPen("#1b4fa8", width=2), name=cycle.name)
        if res.outside.any():
            self.plot_speed.plot(res.t[res.outside], res.v[res.outside] * KMH, pen=None, symbol="o", symbolSize=7,
                                 symbolBrush="#d62728", symbolPen=None, name="hors enveloppe")
        self.plot_power.plot(res.t, res.p_battery / 1000, pen=pg.mkPen("#2e9e5b", width=1.5), name="batterie")
        self.plot_power.addLine(y=0, pen=pg.mkPen("#999"))
