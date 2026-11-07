"""Tab "2 · Enveloppe": V/f + field-weakening torque–speed envelope of the Session motor (core.drive).

Thin view: reads the drive settings, runs core.drive.envelope in a QThreadPool
worker, draws the result and its zones. Every number shown comes from core/;
this module only converts units for display (rad/s → tr/min, W → kW).
"""

from __future__ import annotations

import pyqtgraph as pg
from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtWidgets import QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from evlab.core import drive
from evlab.core.session import Session
from evlab.gui import theme
from evlab.gui.format import fr, fr_fixed
from evlab.gui.widgets import KpiTile, card, chip, french_spin, set_demo_chip
from evlab.gui.workers import CoreWorker
from evlab.io.notes import demo_labels

TITLE = "2 · Enveloppe"
LEFT_WIDTH = 300
RPM = 60.0 / (2.0 * 3.141592653589793)  # rad/s → tr/min (display only)
ZONE_BRUSHES = {1: (47, 111, 214, 28), 2: (46, 158, 91, 28), 3: (224, 138, 30, 32)}
ZONE_NAMES = {1: "couple constant", 2: "puissance constante", 3: "limité par le décrochage"}


class EnvelopeTab(QWidget):
    """Tab 2: drive settings → envelope T(Ω), P(Ω), zones and KPIs."""

    status_message = Signal(str)
    busy = Signal(bool)
    envelope_done = Signal(object)  # core.drive.Envelope
    envelope_failed = Signal(str)

    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session
        self.title = TITLE
        self.envelope: drive.Envelope | None = None
        self._worker: CoreWorker | None = None

        root = QHBoxLayout(self)
        left = QWidget()
        left.setFixedWidth(LEFT_WIDTH)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)

        box = QGroupBox("Variateur")
        form = QFormLayout(box)
        self.spin_imax = french_spin(0.1, 1e4, 1, "A", drive.DEMO_SETTINGS["i_max"])
        self.spin_imax.setToolTip("Courant statorique maximal (efficace, par phase) — valeur démo")
        self.spin_boost = french_spin(0.0, 1e4, 1, "V", drive.DEMO_SETTINGS["boost"])
        self.spin_boost.setToolTip("Tension à f → 0 (compense la chute dans R1) ; la loi atteint Vn à fn")
        self.spin_margin = french_spin(1.0, 100.0, 0, "%", 100 * drive.DEMO_SETTINGS["margin"])
        self.spin_margin.setToolTip("Fraction utilisable du couple de décrochage")
        self.spin_fmax = french_spin(1.0, 1e3, 1, "Hz", drive.DEMO_SETTINGS["f_max"])
        form.addRow("Courant max", self.spin_imax)
        form.addRow("Boost basse vitesse", self.spin_boost)
        form.addRow("Marge / décrochage", self.spin_margin)
        form.addRow("Fréquence max", self.spin_fmax)
        lv.addWidget(box)

        motor_box = QGroupBox("Moteur (onglet 1)")
        mv = QVBoxLayout(motor_box)
        self.lbl_motor = QLabel()
        self.lbl_motor.setWordWrap(True)
        mv.addWidget(self.lbl_motor)
        lv.addWidget(motor_box)

        self.btn_compute = QPushButton("Calculer l'enveloppe")
        self.btn_compute.setMinimumHeight(34)
        self.btn_compute.setProperty("role", "primary")
        self.btn_compute.clicked.connect(self.compute)
        lv.addWidget(self.btn_compute)
        lv.addStretch(1)
        root.addWidget(left)

        right = QVBoxLayout()
        tiles = QHBoxLayout()
        self.tiles = {
            "base": KpiTile("Vitesse de base", "tr/min"),
            "end_cp": KpiTile("Fin de puissance constante", "tr/min"),
            "p_max": KpiTile("P max", "kW"),
            "t_vmax": KpiTile("Couple à vitesse max", "N·m"),
        }
        for t in self.tiles.values():
            tiles.addWidget(t)
        right.addLayout(tiles)

        plot_card, lay, head = card("Enveloppe couple–vitesse (loi V/f + défluxage)")
        self.chip_demo = chip("démo")
        self.chip_demo.setVisible(False)
        head.addWidget(self.chip_demo)
        self.plot_torque = pg.PlotWidget(title="Couple disponible")
        self.plot_power = pg.PlotWidget(title="Puissance disponible")
        for pw, ylab in ((self.plot_torque, "Couple électromagnétique (N·m)"), (self.plot_power, "Puissance (kW)")):
            pw.setLabel("bottom", "Vitesse (tr/min)")
            pw.setLabel("left", ylab)
            pw.showGrid(x=True, y=True, alpha=0.25)
            pw.addLegend(offset=(-10, 10))
        plots = QHBoxLayout()
        plots.addWidget(self.plot_torque)
        plots.addWidget(self.plot_power)
        lay.addLayout(plots)
        self.lbl_zones = QLabel("")
        self.lbl_zones.setProperty("role", "muted")
        lay.addWidget(self.lbl_zones)
        self.lbl_flux = QLabel("")
        self.lbl_flux.setWordWrap(True)
        self.lbl_flux.setProperty("role", "error")
        self.lbl_flux.setVisible(False)
        lay.addWidget(self.lbl_flux)
        right.addWidget(plot_card, 1)
        root.addLayout(right, 1)

        self.on_motor_changed()

    # --- inputs -------------------------------------------------------------------

    def settings(self) -> drive.DriveSettings:
        """Core DriveSettings from the fields (raises ValueError)."""
        return drive.DriveSettings(
            i_max=self.spin_imax.value(),
            boost=self.spin_boost.value(),
            margin=self.spin_margin.value() / 100.0,
            f_max=self.spin_fmax.value(),
        )

    def on_motor_changed(self) -> None:
        """Called when tab 1 publishes a motor: show it and recompute."""
        m = self.session.motor
        demo = " (démo)" if m.is_demo else ""
        self.lbl_motor.setText(f"{m.source}{demo}\nV = {fr(m.v_phase)} V, f = {fr(m.f_rated)} Hz, p = {m.pole_pairs}")
        self._update_demo_chip()
        self.compute()

    def _update_flux_note(self, env: drive.Envelope | None) -> None:
        """Warn when the air-gap flux E/f exceeds En/fn somewhere on the envelope (linear circuit: no saturation)."""
        over = env is not None and env.max_flux_ratio > 1.0 + 1e-9
        self.lbl_flux.setVisible(over)
        self.lbl_flux.setText(
            f"⚠ Boost : E/f atteint {fr(env.max_flux_ratio)} × En/fn à {fr_fixed(env.speed_of_max_flux * RPM, 0)} "
            "tr/min — surexcitation, saturation non modélisée (circuit magnétique linéaire, A33) : "
            "le couple à basse vitesse est surestimé." if over else "")

    def _update_demo_chip(self, settings: drive.DriveSettings | None = None) -> None:
        if settings is None:
            try:
                settings = self.settings()
            except ValueError:
                settings = None
        set_demo_chip(self.chip_demo, demo_labels(motor=self.session.motor, drive_settings=settings))

    # --- computation ----------------------------------------------------------------

    def compute(self) -> bool:
        """Start core.drive.envelope in a pool thread. Returns False if the inputs are refused."""
        try:
            st = self.settings()
        except ValueError as exc:
            msg = f"Paramètres du variateur invalides : {exc}"
            self.status_message.emit(msg)
            self.envelope_failed.emit(msg)
            return False
        motor = self.session.motor
        worker = CoreWorker(lambda progress: drive.envelope(motor, st))
        worker.signals.finished.connect(self._on_done)
        worker.signals.failed.connect(self._on_failed)
        self._worker = worker
        self.btn_compute.setEnabled(False)
        self.busy.emit(True)
        self.status_message.emit("Calcul de l'enveloppe…")
        QThreadPool.globalInstance().start(worker)
        return True

    def _on_done(self, env: drive.Envelope) -> None:
        self.envelope = env
        self.btn_compute.setEnabled(True)
        self.busy.emit(False)
        self.tiles["base"].set_value(fr_fixed(env.base_speed * RPM, 0))
        self.tiles["end_cp"].set_value(fr_fixed(env.end_constant_power * RPM, 0))
        self.tiles["p_max"].set_value(fr(env.p_max / 1000.0))
        self.tiles["t_vmax"].set_value(fr(env.torque_at_max_speed))
        self._draw(env)
        self._update_demo_chip(env.settings)
        self._update_flux_note(env)
        self.status_message.emit(f"Enveloppe calculée : vitesse max {fr_fixed(env.omega_max * RPM, 0)} tr/min")
        self.envelope_done.emit(env)

    def _on_failed(self, message: str) -> None:
        self._update_flux_note(None)
        self.btn_compute.setEnabled(True)
        self.busy.emit(False)
        msg = f"Échec du calcul de l'enveloppe : {message}"
        self.status_message.emit(msg)
        self.envelope_failed.emit(msg)

    def _draw(self, env: drive.Envelope) -> None:
        n = env.omega * RPM
        bounds = {1: (0.0, env.base_speed * RPM), 2: (env.base_speed * RPM, env.end_constant_power * RPM),
                  3: (env.end_constant_power * RPM, env.omega_max * RPM)}
        for pw in (self.plot_torque, self.plot_power):
            pw.clear()
            for z, (a, b) in bounds.items():
                if b > a:
                    pw.addItem(pg.LinearRegionItem((a, b), movable=False, brush=pg.mkBrush(*ZONE_BRUSHES[z]),
                                                   pen=pg.mkPen(None)))
        self.plot_torque.plot(n, env.torque, pen=pg.mkPen(theme.color("blue"), width=2.5), name="couple disponible")
        self.plot_torque.plot(n, env.torque_current, pen=pg.mkPen(theme.color("green"), width=1, style=Qt.PenStyle.DashLine),
                              name="limite courant", connect="finite")
        self.plot_torque.plot(n, env.settings.margin * env.torque_breakdown,
                              pen=pg.mkPen(theme.color("orange"), width=1, style=Qt.PenStyle.DashLine),
                              name=f"{fr_fixed(100 * env.settings.margin, 0)} % du décrochage")
        self.plot_power.plot(n, env.power / 1000.0, pen=pg.mkPen(theme.color("blue"), width=2.5), name="puissance")
        self.plot_torque.setYRange(0, 1.15 * float(env.torque.max()))
        self.lbl_zones.setText(" · ".join(
            f"zone {z} : {ZONE_NAMES[z]} {fr_fixed(a, 0)}–{fr_fixed(b, 0)} tr/min"
            for z, (a, b) in bounds.items() if b > a))
