"""Tab "5 · Thermique": two-node thermal model fed by the cycle losses of tab 4 (core.thermal).

Thin view: reads the network parameters, runs core.thermal.simulate in a
QThreadPool worker on the losses of the last tab 4 cycle and draws T(t).
Every number comes from core/; this module only converts units for display
(K ↔ °C, s → min, h → order of magnitude).
"""

from __future__ import annotations

from dataclasses import replace

import pyqtgraph as pg
from PySide6.QtCore import QThreadPool, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from evlab.core import thermal
from evlab.core.session import Session
from evlab.gui import theme
from evlab.gui.format import fr, fr_fixed, power_of_ten
from evlab.gui.widgets import KpiTile, card, chip, french_spin, set_demo_chip
from evlab.gui.workers import CoreWorker
from evlab.io.notes import R1_ZERO_NOTE, demo_labels

TITLE = "5 · Thermique"
LEFT_WIDTH = 300
T_ZERO_C = 273.15  # K ↔ °C (display only)
METHODS = (("implicit", "Euler implicite (1 s)"), ("rk45", "solve_ivp RK45 (contrôle)"))


class ThermalTab(QWidget):
    """Tab 5: network parameters → winding and frame temperatures over N cycles, insulation life."""

    status_message = Signal(str)
    busy = Signal(bool)
    thermal_done = Signal(object)  # core.thermal.ThermalResult
    thermal_failed = Signal(str)

    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session
        self.title = TITLE
        self.cycle = None  # (DriveResult, EfficiencyMap, Cycle, Vehicle) from tab 4
        self.result: thermal.ThermalResult | None = None
        self.stale = True
        self._worker: CoreWorker | None = None

        root = QHBoxLayout(self)
        left = QWidget()
        left.setFixedWidth(LEFT_WIDTH)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        d = thermal.demo_thermal()
        box = QGroupBox("Réseau thermique (démo)")
        form = QFormLayout(box)
        self.spin_cw = french_spin(1.0, 1e7, 0, "J/K", d.c_w)
        self.spin_cs = french_spin(1.0, 1e8, 0, "J/K", d.c_s)
        self.spin_rws = french_spin(1e-4, 10.0, 4, "K/W", d.r_ws)
        self.spin_rsa = french_spin(1e-4, 10.0, 4, "K/W", d.r_sa)
        self.spin_ta = french_spin(-40.0, 80.0, 1, "°C", d.t_ambient_k - T_ZERO_C)
        for w in (self.spin_cw, self.spin_cs, self.spin_rws, self.spin_rsa):
            w.setToolTip("Valeur de démonstration : pas de relevé R(t) à chaud dans le TP3 (A26)")
        form.addRow("C bobinage", self.spin_cw)
        form.addRow("C fer / carcasse", self.spin_cs)
        form.addRow("R bobinage → fer", self.spin_rws)
        form.addRow("R carcasse → air", self.spin_rsa)
        form.addRow("Température ambiante", self.spin_ta)
        self.lbl_tau = QLabel("")
        self.lbl_tau.setProperty("role", "muted")
        form.addRow(self.lbl_tau)
        lv.addWidget(box)

        run = QGroupBox("Essai")
        rf = QFormLayout(run)
        self.combo_class = QComboBox()
        for k, t in thermal.INSULATION_CLASSES.items():
            self.combo_class.addItem(f"Classe {k} ({fr_fixed(t, 0)} °C)", k)
        self.combo_class.setCurrentIndex(list(thermal.INSULATION_CLASSES).index("F"))
        self.spin_cycles = QSpinBox()
        self.spin_cycles.setRange(1, 500)
        self.spin_cycles.setValue(10)
        self.combo_method = QComboBox()
        for key, label in METHODS:
            self.combo_method.addItem(label, key)
        rf.addRow("Isolation", self.combo_class)
        rf.addRow("Cycles enchaînés", self.spin_cycles)
        rf.addRow("Intégrateur", self.combo_method)
        self.lbl_cycle = QLabel("Cycle : — (simuler l'onglet 4)")
        self.lbl_cycle.setWordWrap(True)
        rf.addRow(self.lbl_cycle)
        lv.addWidget(run)

        self.btn_run = QPushButton("Calculer les températures")
        self.btn_run.setMinimumHeight(34)
        self.btn_run.setProperty("role", "primary")
        self.btn_run.clicked.connect(self.compute)
        lv.addWidget(self.btn_run)
        lv.addStretch(1)
        root.addWidget(left)

        right = QVBoxLayout()
        tiles = QHBoxLayout()
        self.tiles = {
            "t_max": KpiTile("T max bobinage", "°C"),
            "t_mean": KpiTile("T moyenne (dernier cycle)", "°C"),
            "margin": KpiTile("Marge à la classe", "K"),
            "life": KpiTile("Durée de vie isolation (ordre de grandeur)", "h"),
        }
        for t in self.tiles.values():
            tiles.addWidget(t)
        right.addLayout(tiles)
        plot_card, lay, head = card("Températures du bobinage et de la carcasse")
        self.chip_demo = chip("paramètres démo")
        head.addWidget(self.chip_demo)
        self.chip_r1 = chip(R1_ZERO_NOTE, "alert")
        head.addWidget(self.chip_r1)
        self.on_motor_changed()
        self.plot = pg.PlotWidget()
        self.plot.setLabel("bottom", "Temps (min)")
        self.plot.setLabel("left", "Température (°C)")
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.addLegend(offset=(10, 10))
        lay.addWidget(self.plot)
        self.lbl_note = QLabel("La durée de vie suit la règle des 10 K : c'est un ordre de grandeur, "
                               "le point chaud est plus chaud que la moyenne du bobinage calculée ici.")
        self.lbl_note.setWordWrap(True)
        self.lbl_note.setProperty("role", "muted")
        lay.addWidget(self.lbl_note)
        right.addWidget(plot_card, 1)
        root.addLayout(right, 1)
        self._show_tau()
        for w in (self.spin_cw, self.spin_cs, self.spin_rws, self.spin_rsa):
            w.valueChanged.connect(lambda _v: self._show_tau())

    # --- inputs --------------------------------------------------------------------

    def params(self) -> thermal.ThermalParams:
        vals = (self.spin_cw.value(), self.spin_cs.value(), self.spin_rws.value(), self.spin_rsa.value())
        p = thermal.ThermalParams(*vals, t_ambient_k=self.spin_ta.value() + T_ZERO_C)
        return replace(p, is_demo=bool(thermal.demo_fields(p)))  # démo while any of C_w, C_s, R_ws, R_sa is A26

    def on_motor_changed(self) -> None:
        """Tab 1 published a motor: warn when it has no stator copper losses (R1 = 0)."""
        self.chip_r1.setVisible(thermal.stator_copper_missing(self.session.motor))

    def _show_tau(self) -> None:
        try:
            fast, slow = thermal.time_constants(self.params())
        except ValueError:
            self.lbl_tau.setText("")
            return
        self.lbl_tau.setText(f"Constantes de temps : {fr(fast / 60)} min et {fr(slow / 60)} min")

    def on_cycle(self, result) -> None:
        """Tab 4 simulated a cycle: keep its losses and recompute when shown."""
        _sizing, res, cycle, emap, veh = result
        self.cycle = (res, emap, cycle, veh)
        self.lbl_cycle.setText(f"Cycle : {cycle.name} ({fr(cycle.t[-1] / 60)} min)")
        self.stale = True
        if self.isVisible():
            self.compute()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)
        if self.stale and self.cycle is not None:
            self.compute()

    # --- computation -------------------------------------------------------------

    def compute(self) -> bool:
        if self.cycle is None:
            msg = "Simulez d'abord un cycle dans l'onglet 4 · Véhicule & WLTC"
            self.status_message.emit(msg)
            self.thermal_failed.emit(msg)
            return False
        try:
            p = self.params()
        except ValueError as exc:
            msg = f"Paramètres thermiques invalides : {exc}"
            self.status_message.emit(msg)
            self.thermal_failed.emit(msg)
            return False
        res, emap, _, _ = self.cycle
        ref = thermal.map_copper_temperature(emap, self.session.motor.r1_temperature_k)
        n, cls, method = self.spin_cycles.value(), self.combo_class.currentData(), self.combo_method.currentData()

        def job(progress):
            pc, pf = thermal.cycle_losses(res, emap)
            return thermal.simulate(p, pc, pf, n_cycles=n, copper_ref_k=ref, method=method, insulation_class=cls)

        worker = CoreWorker(job)
        worker.signals.finished.connect(self._on_done)
        worker.signals.failed.connect(self._on_failed)
        self._worker = worker
        self.btn_run.setEnabled(False)
        self.busy.emit(True)
        self.status_message.emit(f"Calcul thermique sur {n} cycles…")
        QThreadPool.globalInstance().start(worker)
        return True

    def _on_done(self, r: thermal.ThermalResult) -> None:
        self.result = r
        self.stale = False
        self.btn_run.setEnabled(True)
        self.busy.emit(False)
        s = r.summary
        self.tiles["t_max"].set_value(fr_fixed(s.t_max - T_ZERO_C, 1))
        self.tiles["t_mean"].set_value(fr_fixed(s.t_mean - T_ZERO_C, 1))
        self.tiles["margin"].set_value(fr_fixed(s.margin, 1))
        self.tiles["life"].set_value("≈ " + power_of_ten(thermal.order_of_magnitude(s.life_hours)))
        theme.set_role(self.tiles["margin"].value, "error" if s.margin < 0 else None)
        _res, emap, cycle, veh = self.cycle
        set_demo_chip(self.chip_demo, demo_labels(motor=self.session.motor, drive_settings=emap.envelope.settings,
                                                  thermal_params=self.params(), vehicle=veh, cycle=cycle))
        self.plot.clear()
        minutes = r.t / 60.0
        self.plot.plot(minutes, r.t_w - T_ZERO_C, pen=pg.mkPen(theme.color("red"), width=2), name="bobinage")
        self.plot.plot(minutes, r.t_s - T_ZERO_C, pen=pg.mkPen(theme.color("blue"), width=2), name="fer / carcasse")
        t_class = thermal.INSULATION_CLASSES[s.insulation_class]
        self.plot.plot([minutes[0], minutes[-1]], [t_class, t_class],
                       pen=pg.mkPen(theme.color("orange"), width=1.5, style=Qt.PenStyle.DashLine),
                       name=f"classe {s.insulation_class} ({fr_fixed(t_class, 0)} °C)")
        self.status_message.emit(f"Température max du bobinage : {fr_fixed(s.t_max - T_ZERO_C, 1)} °C")
        self.thermal_done.emit(r)

    def _on_failed(self, message: str) -> None:
        self.btn_run.setEnabled(True)
        self.busy.emit(False)
        msg = f"Échec du calcul thermique : {message}"
        self.status_message.emit(msg)
        self.thermal_failed.emit(msg)
