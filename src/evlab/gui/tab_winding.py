"""Tab "6 · Bobinage": winding factors, slot table, MMF spectrum and rotating air-gap field (core.winding).

Thin view: every number comes from core.winding; this module only lays out the
slot strip, the factor table, the spectrum and animates precomputed frames of the
rotating field (QTimer). Computations take milliseconds, so they run directly.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from evlab.core import winding as wd
from evlab.core.session import Session
from evlab.gui import theme
from evlab.gui.format import fr, fr_fixed
from evlab.gui.widgets import card, french_spin
from evlab.io import femm_model

TITLE = "6 · Bobinage"
LEFT_WIDTH = 300
HARMONICS = (1, 5, 7, 11, 13)
PHASE_COLOURS = {"A": "#f4a6a6", "B": "#f9e08f", "C": "#a9cce3"}
N_FRAMES = 72
N_THETA_PER_SLOT = 32
FPS_MIN, FPS_MAX = 1, 60


class WindingTab(QWidget):
    """Tab 6: Z, 2p, y → slot strip, kw table (y = τ vs y), MMF spectrum, animated field."""

    status_message = Signal(str)
    winding_changed = Signal(object)  # core.winding.Winding (chosen pitch)

    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session
        self.title = TITLE
        self.winding: wd.Winding | None = None
        self.full: wd.Winding | None = None
        self.fields: dict[str, wd.RotatingField] = {}
        self.frame = 0

        root = QHBoxLayout(self)
        left = QWidget()
        left.setFixedWidth(LEFT_WIDTH)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        box = QGroupBox("Bobinage triphasé, double couche")
        form = QFormLayout(box)
        self.spin_z = QSpinBox()
        self.spin_z.setRange(6, 240)
        self.spin_z.setValue(36)
        self.spin_poles = QSpinBox()
        self.spin_poles.setRange(2, 48)
        self.spin_poles.setSingleStep(2)
        self.spin_poles.setValue(4)
        self.lbl_m = QLabel("3")
        self.spin_y = QSpinBox()
        self.spin_y.setRange(1, 9)
        self.spin_y.setValue(7)
        self.spin_y.setToolTip("Pas de bobine en nombre entier d'encoches (1 ≤ y ≤ τ)")
        form.addRow("Encoches Z", self.spin_z)
        form.addRow("Pôles 2p", self.spin_poles)
        form.addRow("Phases m", self.lbl_m)
        form.addRow("Pas y (encoches)", self.spin_y)
        self.lbl_geom = QLabel("")
        self.lbl_geom.setWordWrap(True)
        self.lbl_geom.setProperty("role", "muted")
        form.addRow(self.lbl_geom)
        lv.addWidget(box)

        emf_box = QGroupBox("Force électromotrice")
        ef = QFormLayout(emf_box)
        self.spin_nc = french_spin(1.0, 1e4, 0, "spires", 10.0)
        self.spin_nc.setToolTip("Spires par bobine")
        self.spin_f = french_spin(0.1, 1e4, 1, "Hz", 50.0)
        self.spin_phi = french_spin(1e-5, 10.0, 4, "Wb", 0.01)
        self.spin_phi.setToolTip("Flux par pôle (fondamental)")
        ef.addRow("Spires / bobine", self.spin_nc)
        ef.addRow("Fréquence", self.spin_f)
        ef.addRow("Flux par pôle", self.spin_phi)
        self.lbl_emf = QLabel("")
        self.lbl_emf.setWordWrap(True)
        ef.addRow(self.lbl_emf)
        lv.addWidget(emf_box)

        anim = QGroupBox("Animation du champ tournant")
        av = QVBoxLayout(anim)
        self.btn_play = QPushButton("▶ Lecture")
        self.btn_play.setCheckable(True)
        self.btn_play.toggled.connect(self._play)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(FPS_MIN, FPS_MAX)
        self.slider.setValue(20)
        self.slider.valueChanged.connect(self._set_speed)
        self.lbl_speed = QLabel("")
        self.lbl_speed.setWordWrap(True)
        av.addWidget(self.btn_play)
        av.addWidget(QLabel("Vitesse d'animation"))
        av.addWidget(self.slider)
        av.addWidget(self.lbl_speed)
        lv.addWidget(anim)

        fem = QGroupBox("Animation FEM (FEMM)")
        fv = QVBoxLayout(fem)
        ok, reason = femm_model.femm_available()
        n_cached = len(femm_model.cached_runs())
        cached = f" ; {n_cached} calcul(s) FEM pré-calculé(s) consultable(s)" if n_cached else ""
        self.lbl_fem = QLabel(reason if ok else
                              f"FEMM indisponible : {reason} — le reste de l'onglet fonctionne{cached}")
        self.lbl_fem.setWordWrap(True)
        theme.set_role(self.lbl_fem, "success" if ok else "note")
        self.btn_fem = QPushButton("Ouvrir l'animation FEM…")
        self.btn_fem.clicked.connect(self.open_fem)
        fv.addWidget(self.lbl_fem)
        fv.addWidget(self.btn_fem)
        lv.addWidget(fem)
        self.fem_dialog = None

        self.lbl_error = QLabel("")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.setProperty("role", "error")
        lv.addWidget(self.lbl_error)
        lv.addStretch(1)
        root.addWidget(left)

        right = QVBoxLayout()
        strip_card, sl, _ = card("Tableau des encoches (couche haute / basse)")
        self.strip = QTableWidget(2, 36)
        self.strip.setObjectName("slotTable")  # style.qss: smaller font, 36 columns fit
        self.strip.setVerticalHeaderLabels(["haut", "bas"])
        self.strip.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.strip.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.strip.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.strip.horizontalHeader().setMinimumSectionSize(18)
        self.strip.setFixedHeight(92)
        sl.addWidget(self.strip)
        right.addWidget(strip_card)

        mid = QHBoxLayout()
        kw_card, kl, _ = card("Facteurs de bobinage")
        self.kw_table = QTableWidget(len(HARMONICS), 6)
        self.kw_table.verticalHeader().setDefaultSectionSize(24)
        self.kw_table.setMinimumHeight(26 * (len(HARMONICS) + 1) + 4)
        self.kw_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.kw_table.verticalHeader().setVisible(False)
        self.kw_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        kl.addWidget(self.kw_table)
        mid.addWidget(kw_card, 1)
        spec_card, spl, _ = card("Spectre de la FMM d'une phase (relatif au fondamental)")
        self.plot_spec = pg.PlotWidget()
        self.plot_spec.setLabel("bottom", "rang ν")
        self.plot_spec.setLabel("left", "|F_ν| / |F_1|")
        self.plot_spec.getAxis("left").enableAutoSIPrefix(False)
        self.plot_spec.showGrid(x=False, y=True, alpha=0.25)
        self.plot_spec.addLegend(offset=(-10, 10))
        spl.addWidget(self.plot_spec)
        mid.addWidget(spec_card, 1)
        right.addLayout(mid, 1)

        field_card, fl, _ = card("FMM d'entrefer tournante (courants triphasés équilibrés)")
        plots = QHBoxLayout()
        self.plot_full = pg.PlotWidget()
        self.plot_short = pg.PlotWidget()
        for pw in (self.plot_full, self.plot_short):
            pw.setLabel("bottom", "position θ (degrés mécaniques)")
            pw.setLabel("left", "FMM (A·tr)")
            pw.getAxis("left").enableAutoSIPrefix(False)
            pw.showGrid(x=True, y=True, alpha=0.25)
            pw.addLegend(offset=(-10, 10))
            plots.addWidget(pw)
        self.curves: dict[str, tuple] = {}
        for key, pw in (("full", self.plot_full), ("short", self.plot_short)):
            stepped = pw.plot(pen=pg.mkPen(theme.color("blue"), width=2), name="FMM en escalier")
            fund = pw.plot(pen=pg.mkPen(theme.color("red"), width=1.5, style=Qt.PenStyle.DashLine), name="fondamental")
            self.curves[key] = (stepped, fund)
        fl.addLayout(plots)
        right.addWidget(field_card, 2)
        root.addLayout(right, 1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.next_frame)
        for w in (self.spin_z, self.spin_poles, self.spin_y):
            w.valueChanged.connect(lambda _v: self.recompute())
        for w in (self.spin_nc, self.spin_f, self.spin_phi):
            w.valueChanged.connect(lambda _v: self._show_emf())
        self._set_speed(self.slider.value())
        self.recompute()

    # --- computation -------------------------------------------------------------

    def recompute(self) -> bool:
        """Rebuild everything from the inputs; returns False and shows the core message on invalid input."""
        z, poles = self.spin_z.value(), self.spin_poles.value()
        if poles >= 2 and z % poles == 0:
            self.spin_y.blockSignals(True)
            self.spin_y.setMaximum(z // poles)
            self.spin_y.blockSignals(False)
        try:
            w = wd.Winding(z=z, poles=poles, m=3, y=self.spin_y.value())
        except ValueError as exc:
            self.winding = None
            self.lbl_error.setText(f"Bobinage impossible : {exc}")
            self.status_message.emit(f"Bobinage impossible : {exc}")
            return False
        self.lbl_error.setText("")
        self.winding, self.full = w, wd.Winding(z=z, poles=poles, m=3, y=w.tau)
        self.lbl_geom.setText(f"q = {w.q} encoches/pôle/phase, τ = {w.tau} encoches, "
                              f"α = {fr_fixed(np.degrees(w.alpha), 1)}° él., pas {w.y}/{w.tau}")
        self._fill_strip(w)
        self._fill_kw(w)
        self._draw_spectrum(w)
        n_theta = w.z * N_THETA_PER_SLOT
        self.fields = {"full": wd.rotating_field(self.full, 50.0, 1.0, n_theta, N_FRAMES),
                       "short": wd.rotating_field(w, 50.0, 1.0, n_theta, N_FRAMES)}
        self.plot_full.setTitle(f"pas diamétral y = τ = {w.tau}")
        self.plot_short.setTitle(f"pas raccourci y = {w.y}")
        self.frame = 0
        self._draw_frame()
        self._show_emf()
        self.winding_changed.emit(w)
        return True

    def _fill_strip(self, w: wd.Winding) -> None:
        table = wd.slot_table(w)
        self.strip.setColumnCount(w.z)
        self.strip.setHorizontalHeaderLabels([str(s + 1) for s in range(w.z)])
        for s, slot in enumerate(table):
            for r, ((ph, _sign), label) in enumerate(zip((slot.top, slot.bottom), slot.labels())):
                item = QTableWidgetItem(label)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setBackground(QBrush(QColor(PHASE_COLOURS[ph])))
                item.setForeground(QBrush(QColor(theme.color("cell_text"))))  # dark text on the pastel phase colour
                item.setToolTip(f"encoche {s + 1}, couche {'haute' if r == 0 else 'basse'} : phase {label}")
                self.strip.setItem(r, s, item)

    def _fill_kw(self, w: wd.Winding) -> None:
        full = self.full
        self.kw_table.setHorizontalHeaderLabels(
            ["ν", "kd", f"kp (y = {w.tau})", f"kw (y = {w.tau})", f"kp (y = {w.y})", f"kw (y = {w.y})"])
        for r, nu in enumerate(HARMONICS):
            values = (wd.distribution_factor(w, nu), wd.pitch_factor(full, nu), wd.winding_factor(full, nu),
                      wd.pitch_factor(w, nu), wd.winding_factor(w, nu))
            item = QTableWidgetItem(str(nu))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.kw_table.setItem(r, 0, item)
            for c, v in enumerate(values, start=1):
                it = QTableWidgetItem(fr_fixed(v, 4).replace("-", "−"))
                it.setData(Qt.ItemDataRole.UserRole, v)
                it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.kw_table.setItem(r, c, it)

    def _draw_spectrum(self, w: wd.Winding) -> None:
        """FFT of the phase-A MMF (odd orders ≥ 3; even orders vanish) for y = τ and y, with |kw_ν|/ν."""
        self.plot_spec.clear()
        nu_max = 25
        n_theta = w.z * N_THETA_PER_SLOT * 4
        nus = np.arange(3, nu_max + 1, 2)
        self.spectra = {}
        for key, ww, dx, colour, name in (("full", self.full, -0.35, theme.color("light_blue"), f"y = {w.tau} (FFT)"),
                                          ("short", w, 0.35, theme.color("blue"), f"y = {w.y} (FFT)")):
            _, f_a = wd.phase_mmf(ww, "A", n_theta)
            spec = wd.mmf_spectrum(ww, f_a, nu_max)
            self.spectra[key] = spec
            bars = pg.BarGraphItem(x=nus + dx, height=[spec[n] for n in nus], width=0.6, brush=colour,
                                   pen=None, name=name)
            self.plot_spec.addItem(bars)
        an = wd.analytical_spectrum(w, nu_max)
        self.plot_spec.plot(nus + 0.35, [an[n] for n in nus], pen=None, symbol="x", symbolSize=8,
                            symbolPen=pg.mkPen(theme.color("red"), width=1.5), name=f"|kw_ν|/ν (y = {w.y})")
        self.plot_spec.getAxis("bottom").setTicks([[(int(n), str(int(n))) for n in nus]])

    def _show_emf(self) -> None:
        w = self.winding
        if w is None:
            self.lbl_emf.setText("")
            return
        n = wd.turns_per_phase(w, self.spin_nc.value())
        e = wd.emf(self.spin_f.value(), n, wd.winding_factor(w, 1), self.spin_phi.value())
        self.lbl_emf.setText(f"N = {fr(n, 4)} spires/phase, kw1 = {fr_fixed(wd.winding_factor(w, 1), 4)}\n"
                             f"E = 4,44·f·N·kw1·Φ = {fr(e, 4)} V (efficace, par phase)")

    def open_fem(self):
        """Open the FEM animation window for the current winding (FEMM 4.2, optional)."""
        from evlab.gui.fem_view import FemDialog

        if self.winding is None:
            self.status_message.emit("Bobinage invalide : corriger Z, 2p ou y avant le calcul FEM")
            return None
        self.fem_dialog = FemDialog(self, self.winding, self.session.motor)
        self.fem_dialog.show()
        return self.fem_dialog

    # --- animation ---------------------------------------------------------------

    def _play(self, on: bool) -> None:
        self.btn_play.setText("⏸ Pause" if on else "▶ Lecture")
        if on:
            self.timer.start()
        else:
            self.timer.stop()

    def _set_speed(self, fps: int) -> None:
        self.timer.setInterval(int(1000 / fps))
        self.lbl_speed.setText(f"{fps} images/s, une période électrique = {N_FRAMES} images")

    def next_frame(self) -> None:
        if not self.fields:
            return
        self.frame = (self.frame + 1) % N_FRAMES
        self._draw_frame()

    def _draw_frame(self) -> None:
        k = self.frame
        for key, (stepped, fund) in self.curves.items():
            rf = self.fields[key]
            deg = np.degrees(rf.theta)
            stepped.setData(deg, rf.mmf[k])
            fund.setData(deg, rf.fundamental[k])
        peak = max(float(np.abs(rf.mmf).max()) for rf in self.fields.values())
        for pw in (self.plot_full, self.plot_short):
            pw.setYRange(-1.1 * peak, 1.1 * peak)
            pw.setXRange(0, 360)
