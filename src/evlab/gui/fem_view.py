"""'Animation FEM' window of tab 6: runs io.femm_model (FEMM 4.2) and plays the |B| frames.

Thin view: the FEM solve is io.femm_model.run (worker thread); the analytical
comparison is io.femm_model.analytic_fields (core.winding). Without FEMM the
window says why and the run button stays disabled; the rest of tab 6 is unaffected.
"""

from __future__ import annotations

import math
import tempfile

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from evlab.core import winding as wd
from evlab.gui.format import fr, fr_fixed, fr_pct
from evlab.gui.widgets import french_spin
from evlab.gui.workers import CoreWorker
from evlab.io import femm_model as fm

MATERIALS = (("M-19 Steel", "acier M-19 (non linéaire)"), ("linear", "fer linéaire μr = 4000"))


class FemDialog(QDialog):
    """Run the FEM model over one electrical period and animate it."""

    fem_done = Signal(object)  # io.femm_model.FemResult
    fem_failed = Signal(str)

    def __init__(self, parent: QWidget | None, winding: wd.Winding) -> None:
        super().__init__(parent)
        self.setWindowTitle("Animation FEM — FEMM 4.2")
        self.resize(1100, 640)
        self.winding = winding
        self.result: fm.FemResult | None = None
        self.curves_an: np.ndarray | None = None
        self.frame = 0
        self._cancel = False
        self._worker: CoreWorker | None = None
        self.available, self.reason = fm.femm_available()

        root = QHBoxLayout(self)
        left = QWidget()
        left.setFixedWidth(290)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        box = QGroupBox("Cas magnétostatique")
        form = QFormLayout(box)
        self.combo_mat = QComboBox()
        for key, label in MATERIALS:
            self.combo_mat.addItem(label, key)
        self.spin_i = french_spin(0.1, 200.0, 1, "A", 6.0)
        self.spin_i.setToolTip("Courant de phase crête (courants triphasés équilibrés)")
        self.spin_nc = QSpinBox()
        self.spin_nc.setRange(1, 500)
        self.spin_nc.setValue(10)
        self.spin_frames = QSpinBox()
        self.spin_frames.setRange(1, 72)
        self.spin_frames.setValue(12)
        form.addRow("Fer", self.combo_mat)
        form.addRow("Courant crête", self.spin_i)
        form.addRow("Spires / bobine", self.spin_nc)
        form.addRow("Images / période", self.spin_frames)
        self.lbl_geom = QLabel(f"Z = {winding.z}, 2p = {winding.poles}, y = {winding.y} (onglet 6) ; "
                               "géométrie : hypothèse A32")
        self.lbl_geom.setWordWrap(True)
        self.lbl_geom.setStyleSheet("color: #555;")
        form.addRow(self.lbl_geom)
        lv.addWidget(box)
        self.lbl_status = QLabel(self.reason if self.available else f"FEMM indisponible : {self.reason}")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet("color: #1e7d3a;" if self.available else "color: #b3261e; font-weight: bold;")
        lv.addWidget(self.lbl_status)
        self.btn_run = QPushButton("Calculer avec FEMM")
        self.btn_run.setEnabled(self.available)
        self.btn_run.clicked.connect(self.run)
        self.btn_cancel = QPushButton("Annuler")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel)
        self.progress = QProgressBar()
        self.progress.setFormat("%v / %m images")
        row = QHBoxLayout()
        row.addWidget(self.btn_run, 2)
        row.addWidget(self.btn_cancel, 1)
        lv.addLayout(row)
        lv.addWidget(self.progress)
        self.btn_play = QPushButton("▶ Lecture")
        self.btn_play.setCheckable(True)
        self.btn_play.toggled.connect(self._play)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(1, 20)
        self.slider.setValue(4)
        self.slider.valueChanged.connect(lambda v: self.timer.setInterval(int(1000 / v)))
        lv.addWidget(self.btn_play)
        lv.addWidget(QLabel("Vitesse (images/s)"))
        lv.addWidget(self.slider)
        self.lbl_cmp = QLabel("")
        self.lbl_cmp.setWordWrap(True)
        lv.addWidget(self.lbl_cmp)
        lv.addStretch(1)
        root.addWidget(left)

        right = QVBoxLayout()
        self.image = QLabel("Aucune image : lancer le calcul FEMM.")
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumSize(420, 360)
        pg.setConfigOptions(antialias=True, background="w", foreground="#333")
        self.plot = pg.PlotWidget(title="Induction radiale au milieu de l'entrefer")
        self.plot.setLabel("bottom", "position θ (degrés mécaniques)")
        self.plot.setLabel("left", "B_r (T)")
        self.plot.getAxis("left").enableAutoSIPrefix(False)
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.addLegend(offset=(-10, 10))
        self.curve_fem = self.plot.plot(pen=pg.mkPen("#1b4fa8", width=1.2), name="FEM (FEMM)")
        self.curve_an = self.plot.plot(pen=pg.mkPen("#d62728", width=1.5, style=Qt.PenStyle.DashLine),
                                       name="fondamental analytique μ0·F1/(kc·g)")
        top = QHBoxLayout()
        top.addWidget(self.image, 1)
        right.addLayout(top, 3)
        right.addWidget(self.plot, 2)
        root.addLayout(right, 1)
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.next_frame)

    # --- run ------------------------------------------------------------------------

    def case(self) -> fm.FemCase:
        w = self.winding
        if (w.z, w.poles) != (36, 4):
            raise ValueError("le modèle FEM est dessiné pour 36 encoches et 4 pôles (hypothèse A32)")
        return fm.FemCase(winding=w, turns_per_coil=self.spin_nc.value(), current=self.spin_i.value(),
                          n_frames=self.spin_frames.value(), material=self.combo_mat.currentData(),
                          n_radial=50, n_angular=300)

    def run(self) -> bool:
        try:
            case = self.case()
        except ValueError as exc:
            self.fem_failed.emit(str(exc))
            self.lbl_status.setText(f"Calcul impossible : {exc}")
            return False
        self._cancel = False
        out = tempfile.mkdtemp(prefix="evlab_fem_frames_")

        def job(progress):
            return fm.run(case, out, progress=lambda k, n: progress(f"{k}:{n}"), cancelled=lambda: self._cancel)

        worker = CoreWorker(job)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(self.show_result)
        worker.signals.failed.connect(self._on_failed)
        self._worker = worker
        self.progress.setRange(0, case.n_frames)
        self.progress.setValue(0)
        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.lbl_status.setText("Calcul FEMM en cours (construction du modèle, puis une résolution par image)…")
        QThreadPool.globalInstance().start(worker)
        return True

    def cancel(self) -> None:
        self._cancel = True

    def _on_progress(self, text: str) -> None:
        k, _n = (int(x) for x in text.split(":"))
        self.progress.setValue(k)

    def _on_failed(self, message: str) -> None:
        self.btn_run.setEnabled(self.available)
        self.btn_cancel.setEnabled(False)
        self.lbl_status.setText(f"Échec du calcul FEMM : {message}")
        self.fem_failed.emit(message)

    # --- display ----------------------------------------------------------------------

    def show_result(self, result: fm.FemResult) -> None:
        """Load solved frames (from run, or given directly)."""
        self.result = result
        self.btn_run.setEnabled(self.available)
        self.btn_cancel.setEnabled(False)
        if not result.frames:
            self.lbl_status.setText("Calcul annulé avant la première image.")
            self.fem_done.emit(result)
            return
        cmp, self.curves_an = fm.analytic_fields(result)
        self.comparison = cmp
        speed = ("" if math.isnan(cmp.rotation_speed)
                 else f" Vitesse du champ : {fr(cmp.rotation_speed, 4)} rad/s (2πf/p = {fr(cmp.expected_speed, 4)}).")
        self.lbl_cmp.setText(
            f"<b>Fondamental de B_r</b> : FEM {fr(cmp.b1_fem)} T ; μ0·F1/g = {fr(cmp.b1_smooth)} T ; "
            f"μ0·F1/(kc·g) = {fr(cmp.b1_carter)} T (kc = {fr_fixed(cmp.carter, 3)}) ; "
            f"écart FEM / analytique {fr_pct(100 * (cmp.ratio - 1))}.{speed}<br>"
            "Écart dû aux encoches (Carter, harmoniques de denture), à la chute de FMM dans le fer "
            "et à la saturation (acier M-19 aux forts courants).")
        self.lbl_status.setText(f"{len(result.frames)} image(s) calculée(s) en {fr(result.solve_seconds)} s.")
        self.frame = 0
        self._draw()
        self.fem_done.emit(result)

    def _play(self, on: bool) -> None:
        self.btn_play.setText("⏸ Pause" if on else "▶ Lecture")
        self.timer.start() if on else self.timer.stop()

    def next_frame(self) -> None:
        if self.result is not None and self.result.frames:
            self.frame = (self.frame + 1) % len(self.result.frames)
            self._draw()

    def _draw(self) -> None:
        f = self.result.frames[self.frame]
        if f.png is not None:
            self.image.setPixmap(QPixmap(str(f.png)).scaled(
                self.image.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        deg = np.degrees(f.theta)
        self.curve_fem.setData(deg, f.b_r)
        self.curve_an.setData(deg, self.curves_an[self.frame])
