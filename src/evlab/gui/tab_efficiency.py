"""Tab "3 · Rendement": efficiency map η(T, Ω) of the Session motor under the drive of tab 2 (core.losses).

Thin view: reads the loss settings, runs core.losses.efficiency_map in a
QThreadPool worker, draws the contour map with % labels, the envelope overlay
and (from stage 5) the cycle points. Every number comes from core/; this module
only converts units for display (rad/s → tr/min, °C ↔ K, η → %).
"""

from __future__ import annotations

import numpy as np
import matplotlib
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import QThreadPool, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from evlab.core import drive, losses
from evlab.core.session import Session
from evlab.gui import theme
from evlab.gui.format import fr, fr_fixed
from evlab.gui.widgets import card, chip, french_spin, set_demo_chip
from evlab.gui.workers import CoreWorker
from evlab.io.notes import demo_labels

TITLE = "3 · Rendement"
LEFT_WIDTH = 300
RPM = 60.0 / (2.0 * 3.141592653589793)  # rad/s → tr/min (display only)
T_ZERO_C = 273.15
LEVELS = (50, 60, 70, 75, 78, 80, 82, 84, 86, 88, 90, 92, 94)  # contour lines, %
DEFAULT_DRIVE = drive.demo_settings()  # until tab 2 sends its envelope (A16)


class EfficiencyTab(QWidget):
    """Tab 3: loss settings → η(T, Ω) map, envelope overlay, cycle points, PNG export."""

    status_message = Signal(str)
    busy = Signal(bool)
    map_done = Signal(object)  # core.losses.EfficiencyMap
    map_failed = Signal(str)

    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session
        self.title = TITLE
        self.envelope: drive.Envelope | None = None
        self.emap: losses.EfficiencyMap | None = None
        self.cycle_points: tuple[np.ndarray, np.ndarray] | None = None
        self._worker: CoreWorker | None = None
        self.stale = True  # inputs changed since the last map; recomputed when the tab is shown

        root = QHBoxLayout(self)
        left = QWidget()
        left.setFixedWidth(LEFT_WIDTH)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)

        box = QGroupBox("Pertes")
        form = QFormLayout(box)
        self.spin_beta = french_spin(0.5, 3.0, 2, "", 1.5)
        self.spin_beta.setToolTip("Exposant de Steinmetz : P_fer ∝ f^β·B² (hypothèse A19)")
        self.spin_tw = french_spin(-40.0, 250.0, 0, "°C", 75.0)
        self.spin_tw.setToolTip("Température du bobinage pour R1 (loi du cuivre)")
        self.chk_mech = QCheckBox("Pertes mécaniques (essai à vide)")
        self.chk_mech.setChecked(True)
        self.spin_friction = french_spin(0.0, 100.0, 0, "%", 50.0)
        self.spin_friction.setToolTip("Part de p_méc ∝ Ω (frottements), le reste ∝ Ω² (ventilation) — A20")
        self.chk_inv = QCheckBox("Pertes onduleur (démo)")
        self.chk_inv.setChecked(True)
        self.spin_inv0 = french_spin(0.0, 1e4, 0, "W", 50.0)
        self.spin_invk = french_spin(0.0, 50.0, 1, "%", 2.0)
        for w in (self.spin_inv0, self.spin_invk):
            w.setToolTip("Valeurs de démonstration (A21)")
        form.addRow("Exposant β fer", self.spin_beta)
        form.addRow("Température bobinage", self.spin_tw)
        form.addRow(self.chk_mech)
        form.addRow("Part frottements", self.spin_friction)
        form.addRow(self.chk_inv)
        form.addRow("Onduleur fixe", self.spin_inv0)
        form.addRow("Onduleur proportionnel", self.spin_invk)
        lv.addWidget(box)

        grid = QGroupBox("Grille et affichage")
        gf = QFormLayout(grid)
        self.spin_nt = QSpinBox()
        self.spin_nt.setRange(10, 400)
        self.spin_nt.setValue(160)
        self.spin_nw = QSpinBox()
        self.spin_nw.setRange(10, 400)
        self.spin_nw.setValue(120)
        self.chk_cycle = QCheckBox("Points du cycle")
        self.chk_cycle.setEnabled(False)
        self.chk_cycle.setToolTip("Disponible avec l'onglet 4 · Véhicule & WLTC (étape 5)")
        self.chk_cycle.toggled.connect(lambda _on: self._draw())
        gf.addRow("Points en couple", self.spin_nt)
        gf.addRow("Points en vitesse", self.spin_nw)
        gf.addRow(self.chk_cycle)
        lv.addWidget(grid)

        self.lbl_drive = QLabel()
        self.lbl_drive.setWordWrap(True)
        self.lbl_drive.setProperty("role", "muted")
        lv.addWidget(self.lbl_drive)

        self.btn_compute = QPushButton("Calculer la carte")
        self.btn_compute.setMinimumHeight(34)
        self.btn_compute.setProperty("role", "primary")
        self.btn_compute.clicked.connect(self.compute)
        self.btn_png = QPushButton("Exporter PNG")
        self.btn_png.setEnabled(False)
        self.btn_png.clicked.connect(self._choose_png)
        lv.addWidget(self.btn_compute)
        lv.addWidget(self.btn_png)
        lv.addStretch(1)
        root.addWidget(left)

        map_card, lay, head = card("Carte de rendement η(C, n)")
        self.chip_demo = chip("démo")
        self.chip_demo.setVisible(False)
        head.addWidget(self.chip_demo)
        self.figure = Figure(figsize=(8, 6), layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.figure)
        lay.addWidget(self.canvas, 1)
        self.lbl_best = QLabel("")
        lay.addWidget(self.lbl_best)
        root.addWidget(map_card, 1)

        self.on_motor_changed(recompute=False)

    # --- inputs -----------------------------------------------------------------

    def settings(self) -> losses.LossSettings:
        """Core LossSettings from the fields (raises ValueError)."""
        use_tw = self.spin_tw.isEnabled()
        return losses.LossSettings(
            beta=self.spin_beta.value(),
            winding_temperature_k=self.spin_tw.value() + T_ZERO_C if use_tw else None,
            mechanical=self.chk_mech.isChecked(),
            friction_share=self.spin_friction.value() / 100.0,
            inverter=self.chk_inv.isChecked(),
            inverter_fixed_w=self.spin_inv0.value(),
            inverter_fraction=self.spin_invk.value() / 100.0,
        )

    def drive_settings(self) -> drive.DriveSettings:
        return self.envelope.settings if self.envelope is not None else DEFAULT_DRIVE

    def on_motor_changed(self, recompute: bool = True) -> None:
        """Tab 1 published a motor: R1 reference temperature and p_mec come with it."""
        m = self.session.motor
        known = m.r1 > 0 and m.r1_temperature_k is not None
        self.spin_tw.setEnabled(known)
        if known:
            self.spin_tw.setValue(m.r1_temperature_k - T_ZERO_C)
        self.spin_tw.setToolTip("Température du bobinage pour R1 (loi du cuivre)" if known
                                else "R1 sans température de référence : pas de correction")
        self.chk_mech.setText(f"Pertes mécaniques (p_méc = {fr(m.p_mech)} W)")
        self._update_demo_chip()
        if recompute:
            self._invalidate()

    def on_envelope(self, env: drive.Envelope) -> None:
        """Tab 2 computed an envelope: use its drive settings and boundary, then recompute."""
        self.envelope = env
        st = env.settings
        self.lbl_drive.setText(f"Variateur (onglet 2) : {fr(st.i_max)} A, boost {fr(st.boost)} V, "
                               f"marge {fr_fixed(100 * st.margin, 0)} %, f max {fr(st.f_max)} Hz")
        self._invalidate()

    def _update_demo_chip(self, emap: losses.EfficiencyMap | None = None) -> None:
        """Démo chip from what the map depends on: motor, drive settings (A16), inverter losses (A21)."""
        if emap is not None:
            dst, st = emap.envelope.settings, emap.settings
        else:
            dst = self.drive_settings()
            try:
                st = self.settings()
            except ValueError:
                st = None
        set_demo_chip(self.chip_demo, demo_labels(motor=self.session.motor, drive_settings=dst, loss_settings=st))

    def _invalidate(self) -> None:
        """Inputs changed: recompute now if the tab is visible, otherwise when it is shown."""
        self.stale = True
        if self.isVisible():
            self.compute()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)
        if self.stale:
            self.compute()

    def set_cycle_points(self, torque: np.ndarray, omega: np.ndarray) -> None:
        """Operating points of a driving cycle (shaft torque N·m, speed rad/s), from stage 5."""
        self.cycle_points = (np.asarray(torque, dtype=float), np.asarray(omega, dtype=float))
        self.chk_cycle.setEnabled(True)
        self.chk_cycle.setToolTip("Points de fonctionnement du cycle")
        self._draw()

    # --- computation --------------------------------------------------------------

    def compute(self) -> bool:
        """Start core.losses.efficiency_map in a pool thread. Returns False if the inputs are refused."""
        try:
            st = self.settings()
        except ValueError as exc:
            msg = f"Paramètres de pertes invalides : {exc}"
            self.status_message.emit(msg)
            self.map_failed.emit(msg)
            return False
        motor, dst, env = self.session.motor, self.drive_settings(), self.envelope
        if env is not None and env.settings != dst:
            env = None
        n_t, n_w = self.spin_nt.value(), self.spin_nw.value()

        def job(progress):
            e = env if env is not None else drive.envelope(motor, dst)
            t, w = losses.default_grid(motor, e, st, n_t, n_w)
            return losses.efficiency_map(motor, t, w, dst, st, envelope=e)

        worker = CoreWorker(job)
        worker.signals.finished.connect(self._on_done)
        worker.signals.failed.connect(self._on_failed)
        self._worker = worker
        self.btn_compute.setEnabled(False)
        self.busy.emit(True)
        self.status_message.emit(f"Calcul de la carte {n_t} × {n_w}…")
        QThreadPool.globalInstance().start(worker)
        return True

    def _on_done(self, emap: losses.EfficiencyMap) -> None:
        self.emap = emap
        self.stale = False
        self.btn_compute.setEnabled(True)
        self.btn_png.setEnabled(True)
        self.busy.emit(False)
        self._draw()
        self._update_demo_chip(emap)
        eta, t, w = losses.best_point(emap)
        self.lbl_best.setText(f"Rendement max {fr_fixed(100 * eta, 1)} % à {fr(t)} N·m, "
                              f"{fr_fixed(w * RPM, 0)} tr/min (rendement chaîne onduleur + moteur, arbre)")
        self.status_message.emit("Carte de rendement calculée")
        self.map_done.emit(emap)

    def _on_failed(self, message: str) -> None:
        self.btn_compute.setEnabled(True)
        self.busy.emit(False)
        msg = f"Échec du calcul de la carte : {message}"
        self.status_message.emit(msg)
        self.map_failed.emit(msg)

    # --- drawing and export ---------------------------------------------------------

    def _draw(self) -> None:
        """Draw the map with the matplotlib colours of the current theme."""
        with matplotlib.rc_context(theme.mpl_rc()):
            self.figure.set_facecolor(theme.color("plot_bg"))
            self._draw_map()

    def on_theme_changed(self) -> None:
        self._draw()

    def _draw_map(self) -> None:
        self.figure.clear()
        ax = self.figure.add_subplot()
        self.ax = ax
        emap = self.emap
        if emap is None:
            ax.set_axis_off()
            self.canvas.draw_idle()
            return
        n = emap.speed * RPM
        eta = 100.0 * emap.eta
        filled = ax.contourf(n, emap.torque, eta, levels=np.arange(0, 101, 2.5), cmap="viridis", extend="neither")
        levels = [lv for lv in LEVELS if np.nanmin(eta) < lv < np.nanmax(eta)]
        if levels:
            lines = ax.contour(n, emap.torque, eta, levels=levels, colors="white", linewidths=0.8)
            ax.clabel(lines, fmt=lambda v: f"{fr_fixed(v, 0)} %", fontsize=8)
        self.figure.colorbar(filled, ax=ax, label="Rendement (%)")
        env = emap.envelope
        ax.plot(env.omega * RPM, losses.shaft_torque_limit(self.session.motor, env, emap.settings),
                color=theme.color("red"), linewidth=2, label="enveloppe (couple à l'arbre)")
        if self.chk_cycle.isChecked() and self.cycle_points is not None:
            t, w = self.cycle_points
            ax.scatter(w * RPM, t, s=6, color=theme.color("orange"), alpha=0.6, label="points du cycle")
        demo = " (démo)" if self.session.motor.is_demo else ""
        ax.set_title(f"{self.session.motor.source}{demo}", fontsize=10)
        ax.set_xlabel("Vitesse (tr/min)")
        ax.set_ylabel("Couple à l'arbre (N·m)")
        ax.legend(loc="upper right", fontsize=8)
        ax.set_ylim(0, float(emap.torque[-1]))
        ax.set_xlim(0, float(n[-1]))
        self.canvas.draw_idle()

    def _choose_png(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Exporter la carte", "carte_rendement.png", "PNG (*.png)")
        if path:
            self.export_png(path)

    def export_png(self, path) -> None:
        """Save the current map as a PNG (150 dpi)."""
        self.figure.savefig(str(path), dpi=150)
        self.status_message.emit(f"Carte exportée : {path}")
