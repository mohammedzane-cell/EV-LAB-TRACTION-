"""'Animation FEM' window of tab 6: runs io.femm_model (FEMM 4.2) and plays the |B| frames.

Thin view: the FEM solve is io.femm_model.run (worker thread); the analytical
comparison is io.femm_model.analytic_fields (core.winding); I_µ = V/Xm is
core.circuit.magnetising_current. Without FEMM the window says why, the run button
stays disabled and the pre-computed runs of data/fem_cache are shown instead.
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

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
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from evlab.core import circuit
from evlab.core import winding as wd
from evlab.core.session import MotorParams
from evlab.gui import theme
from evlab.gui.format import fr, fr_fixed, fr_pct
from evlab.gui.widgets import external_legends, flexible_plots, french_spin, scroll_panel
from evlab.gui.workers import CoreWorker
from evlab.io import femm_model as fm

MATERIALS = (("M-19 Steel", "acier M-19 (non linéaire)"), ("linear", "fer linéaire μr = 4000"))
IRON_NAMES = {"M-19 Steel": "acier M-19", "linear": "fer linéaire"}
PRESETS = ((6.0, "6 A crête"), (18.0, "18 A crête (surexcitation)"))
NOTE = ("Rotor lisse sans barres = état magnétisant (à vide). Un courant élevé ici est une "
        "surexcitation, pas un point en charge. Géométrie démo.")


def current_text(peak: float) -> str:
    """'6,00 A crête (4,24 A eff)'."""
    return f"{fr(peak)} A crête ({fr(fm.rms_from_peak(peak))} A eff)"


class FemDialog(QDialog):
    """Run the FEM model over one electrical period (or replay a saved run) and animate it."""

    fem_done = Signal(object)  # io.femm_model.FemResult
    fem_failed = Signal(str)

    def __init__(self, parent: QWidget | None, winding: wd.Winding, motor: MotorParams | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Animation FEM — FEMM 4.2")
        self.resize(1100, 680)
        self.winding = winding
        self.motor = motor
        self.result: fm.FemResult | None = None
        self.curves_an: np.ndarray | None = None
        self.frame = 0
        self._cancel = False
        self._worker: CoreWorker | None = None
        self.available, self.reason = fm.femm_available()

        root = QHBoxLayout(self)
        left = QWidget()
        left.setFixedWidth(330)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        box = QGroupBox("Cas magnétostatique")
        form = QFormLayout(box)
        self.combo_mat = QComboBox()
        for key, label in MATERIALS:
            self.combo_mat.addItem(label, key)
        # current: peak value; default = magnetising current of the identified motor (tab 1)
        self.i_mu_peak = None if motor is None else fm.peak_from_rms(circuit.magnetising_current(motor))
        self.combo_preset = QComboBox()
        if self.i_mu_peak is not None:
            self.combo_preset.addItem("I_µ = V/Xm (moteur de l'onglet 1)", self.i_mu_peak)
        for value, label in PRESETS:
            self.combo_preset.addItem(label, value)
        self.spin_i = french_spin(0.1, 200.0, 2, "A crête", self.combo_preset.itemData(0))
        self.spin_i.setToolTip("Courant de phase CRÊTE (courants triphasés équilibrés) : Î = √2·I_eff")
        self.lbl_i = QLabel(current_text(self.spin_i.value()))
        self.spin_i.valueChanged.connect(lambda v: self.lbl_i.setText(current_text(v)))
        self.combo_preset.currentIndexChanged.connect(
            lambda k: self.spin_i.setValue(self.combo_preset.itemData(k)))
        self.spin_nc = QSpinBox()
        self.spin_nc.setRange(1, 500)
        self.spin_nc.setValue(10)
        self.spin_frames = QSpinBox()
        self.spin_frames.setRange(1, 72)
        self.spin_frames.setSingleStep(6)
        self.spin_frames.setValue(12)
        self.spin_frames.setToolTip("Multiple de 6 : seules les images de [0, T/6) sont résolues par FEMM, "
                                    "les autres s'en déduisent par symétrie (3 encoches, A+ → C− → B+)")
        form.addRow("Fer", self.combo_mat)
        form.addRow("Préréglage", self.combo_preset)
        form.addRow("Courant", self.spin_i)
        form.addRow("", self.lbl_i)
        if motor is not None:
            demo = " (démo)" if motor.is_demo else ""
            self.lbl_imu = QLabel(f"I_µ = V/Xm = {fr(circuit.magnetising_current(motor))} A eff → "
                                  f"{fr(self.i_mu_peak)} A crête ; moteur : {motor.source}{demo}")
            self.lbl_imu.setWordWrap(True)
            self.lbl_imu.setProperty("role", "muted")
        form.addRow("Spires / bobine", self.spin_nc)
        form.addRow("Images / période", self.spin_frames)
        self.lbl_geom = QLabel(f"Z = {winding.z}, 2p = {winding.poles}, y = {winding.y} (onglet 6) ; "
                               "géométrie : hypothèse A32 (démo)")
        self.lbl_geom.setWordWrap(True)
        self.lbl_geom.setProperty("role", "muted")
        lv.addWidget(box)
        if motor is not None:
            lv.addWidget(self.lbl_imu)
        lv.addWidget(self.lbl_geom)
        self.lbl_note = QLabel(NOTE)
        self.lbl_note.setWordWrap(True)
        self.lbl_note.setProperty("role", "note")
        lv.addWidget(self.lbl_note)
        self.lbl_status = QLabel(self.reason if self.available else f"FEMM indisponible : {self.reason}")
        self.lbl_status.setWordWrap(True)
        theme.set_role(self.lbl_status, "success" if self.available else "error")
        lv.addWidget(self.lbl_status)
        self.btn_run = QPushButton("Calculer avec FEMM")
        self.btn_run.setEnabled(self.available)
        self.btn_run.clicked.connect(self.run)
        self.btn_cancel = QPushButton("Annuler")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel)
        self.progress = QProgressBar()
        self.progress.setFormat("%v / %m images résolues")
        row = QHBoxLayout()
        row.addWidget(self.btn_run, 2)
        row.addWidget(self.btn_cancel, 1)
        lv.addLayout(row)
        lv.addWidget(self.progress)
        self.combo_cache = QComboBox()
        self.btn_cache = QPushButton("Charger les résultats pré-calculés")
        self.btn_cache.clicked.connect(lambda: self.load_cached(self.combo_cache.currentData()))
        lv.addWidget(self.combo_cache)
        lv.addWidget(self.btn_cache)
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
        root.addWidget(scroll_panel(left))

        right = QVBoxLayout()
        self.image = QLabel("Aucune image : lancer le calcul FEMM.")
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumSize(320, 260)
        # the frame is scaled to the label, never the other way round: no overlap on a short screen
        self.image.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.plot = pg.PlotWidget(title="Induction radiale au milieu de l'entrefer")
        self.plot.setLabel("bottom", "position θ (degrés mécaniques)")
        self.plot.setLabel("left", "B_r (T)")
        self.plot.getAxis("left").enableAutoSIPrefix(False)
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.addLegend(offset=(-10, 10))
        self.curve_fem = self.plot.plot(pen=pg.mkPen(theme.color("blue"), width=1.2), name="FEM (FEMM)")
        self.curve_an = self.plot.plot(pen=pg.mkPen(theme.color("red"), width=1.5, style=Qt.PenStyle.DashLine),
                                       name="fondamental analytique μ0·F1/(kc·g)")
        top = QHBoxLayout()
        top.addWidget(self.image, 1)
        right.addLayout(top, 3)
        right.addWidget(self.plot, 2)
        root.addLayout(right, 1)
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.next_frame)

        external_legends(self)  # legend above the B_r plot, never over the curves
        flexible_plots(self)
        self.refresh_cache_list()
        if not self.available and self.combo_cache.count():
            self.load_cached(self._preferred_cache())

    # --- cache --------------------------------------------------------------------------

    def refresh_cache_list(self) -> None:
        self.combo_cache.clear()
        for folder in fm.cached_runs():
            try:
                case = fm.load_cache(folder).case
            except ValueError:
                continue
            if (case.winding.z, case.winding.poles) == (self.winding.z, self.winding.poles):
                self.combo_cache.addItem(self._case_label(case), folder)
        self.combo_cache.setEnabled(self.combo_cache.count() > 0)
        self.btn_cache.setEnabled(self.combo_cache.count() > 0)

    def _preferred_cache(self) -> Path:
        """The saved run of the current settings if there is one, else the first one."""
        try:
            match = fm.find_cache(self.case())
        except ValueError:
            match = None
        for k in range(self.combo_cache.count()):  # findData cannot compare Path objects
            if self.combo_cache.itemData(k) == match:
                self.combo_cache.setCurrentIndex(k)
        return self.combo_cache.currentData()

    @staticmethod
    def _case_label(case: fm.FemCase) -> str:
        return (f"{IRON_NAMES[case.material]}, {current_text(case.current)}, {case.turns_per_coil} spires/bobine, "
                f"y = {case.winding.y}, {case.n_frames} images")

    def load_cached(self, folder: Path | None) -> bool:
        if folder is None:
            return False
        try:
            result = fm.load_cache(folder)
        except ValueError as exc:
            self.lbl_status.setText(str(exc))
            return False
        self.show_result(result)
        return True

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
            res = fm.run(case, out, progress=lambda k, n: progress(f"{k}:{n}"), cancelled=lambda: self._cancel)
            saved = None
            if len(res.frames) == case.n_frames:  # complete run: kept in data/fem_cache
                try:
                    saved = fm.save_cache(res)
                except OSError:
                    saved = None
            return res, saved

        worker = CoreWorker(job)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(self._on_finished)
        worker.signals.failed.connect(self._on_failed)
        self._worker = worker
        self.progress.setRange(0, len(fm.solved_indices(case)))
        self.progress.setValue(0)
        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.lbl_status.setText("Calcul FEMM en cours (construction du modèle, puis une résolution par image "
                                "de [0, T/6))…")
        QThreadPool.globalInstance().start(worker)
        return True

    def cancel(self) -> None:
        self._cancel = True

    def _on_progress(self, text: str) -> None:
        k, n = (int(x) for x in text.split(":"))
        self.progress.setRange(0, n)
        self.progress.setValue(k)

    def _on_finished(self, payload) -> None:
        result, saved = payload
        self.show_result(result)
        if saved is not None:
            self.refresh_cache_list()
            self.lbl_status.setText(self.lbl_status.text() + f" Enregistré dans data/fem_cache/{saved.name}.")

    def _on_failed(self, message: str) -> None:
        self.btn_run.setEnabled(self.available)
        self.btn_cancel.setEnabled(False)
        self.lbl_status.setText(f"Échec du calcul FEMM : {message}")
        self.fem_failed.emit(message)

    # --- display ----------------------------------------------------------------------

    def show_result(self, result: fm.FemResult) -> None:
        """Load solved frames (from run, from the cache, or given directly)."""
        self.result = result
        self.btn_run.setEnabled(self.available)
        self.btn_cancel.setEnabled(False)
        if not result.frames:
            self.lbl_status.setText("Calcul annulé avant la première image.")
            self.fem_done.emit(result)
            return
        case = result.case
        cmp, self.curves_an = fm.analytic_fields(result)
        self.comparison = cmp
        speed = ("" if math.isnan(cmp.rotation_speed)
                 else f" Vitesse du champ : {fr(cmp.rotation_speed, 4)} rad/s (2πf/p = {fr(cmp.expected_speed, 4)}).")
        self.lbl_cmp.setText(
            f"<b>Fondamental de B_r</b> à {current_text(case.current)}, {IRON_NAMES[case.material]} : "
            f"FEM {fr(cmp.b1_fem)} T ; μ0·F1/g = {fr(cmp.b1_smooth)} T ; "
            f"μ0·F1/(kc·g) = {fr(cmp.b1_carter)} T (kc = {fr_fixed(cmp.carter, 3)}) ; "
            f"écart FEM / analytique {fr_pct(100 * (cmp.ratio - 1))}.{speed}<br>"
            "Écart dû aux encoches (Carter, harmoniques de denture), à la chute de FMM dans le fer "
            "et à la saturation (acier M-19 aux forts courants).")
        n, n_solved = len(result.frames), len(result.solved)
        how = (f"{n_solved} résolue(s) par FEMM, {n - n_solved} déduite(s) par symétrie (rotation de 3 encoches, "
               "A+ → C− → B+)" if n_solved and n_solved < n else "toutes résolues par FEMM")
        if result.cached:
            self.lbl_status.setText(f"Résultats FEM pré-calculés ({self._case_label(case)} ; {how} ; "
                                    f"géométrie démo).")
            theme.set_role(self.lbl_status, "info")
        else:
            self.lbl_status.setText(f"{n} image(s) en {fr(result.solve_seconds)} s : {how}.")
            theme.set_role(self.lbl_status, "success")
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
