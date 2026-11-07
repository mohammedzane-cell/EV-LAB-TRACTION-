"""Tab "1 · Identification": Γ circuit from the bench tests (classical formulas) and the load points (fit).

Thin view: reads the inputs, runs core.identification.compare_methods in a
QThreadPool worker, draws core results and publishes the identified motor to the
Session. Every number shown comes from core/ (or from the files, for the
measured points); this module only formats them.
Layout reference: docs/mockup_tab1.png.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from evlab.core import circuit
from evlab.core import identification as ident
from evlab.core.session import Session
from evlab.gui.format import fr, fr_fixed, fr_pct
from evlab.gui.widgets import card, chip, french_spin
from evlab.gui.workers import CoreWorker
from evlab.io import demo_data
from evlab.io.loaders import (
    BenchTests,
    LoaderError,
    LoadPointsFile,
    load_bench_tests,
    load_load_points,
    nameplate,
    reference_motor,
)

TITLE = "1 · Identification"
LEFT_WIDTH = 300
T_ZERO_C = 273.15  # °C ↔ K at the GUI edge
RAD_S_TO_RPM = 60.0 / (2.0 * np.pi)  # unit conversion at the GUI edge

METHODS = (("classical", "Formules classiques"), ("fit", "Optimisation (scipy)"), ("both", "Comparer les deux"))
LAYOUTS = (("tp3", "TP3 (R1 en tête)"), ("terminals", "Bornes"))
ROWS = ("reference", "classical", "fit")
ROW_LABELS = {"classical": "Formules classiques", "fit": "Optimisation"}
COLUMNS = (("r_fe", "Rf (Ω)"), ("x_m", "Xm (Ω)"), ("x_leak", "X fuites (Ω)"), ("r2p", "R'2 (Ω)"))
PARAM_LABELS = {"x_m": "Xm", "x_leak": "X", "r2p": "R'2", "r_fe": "Rf"}
STAGES = {"classical": "Formules classiques…", "fit": "Optimisation (moindres carrés, 10 départs)…"}
COLORS = {"classical": "#e08a1e", "fit": "#2e9e5b", "points": "#2f6fd6"}
VALUE_ROLE = Qt.ItemDataRole.UserRole


_spin = french_spin
_card = card


class _PreviewDialog(QDialog):
    """Read-only table of what a CSV file contained (values as loaded, SI)."""

    def __init__(self, parent: QWidget, title: str, headers: list[str], rows: list[list[str]]) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(560, 360)
        table = QTableWidget(len(rows), len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for r, row in enumerate(rows):
            for c, text in enumerate(row):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(r, c, item)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        QVBoxLayout(self).addWidget(table)
        self.table = table


class IdentificationTab(QWidget):
    """Tab 1: load the bench files, pick a method, identify, publish the motor."""

    status_message = Signal(str)  # for the main window status bar
    busy = Signal(bool)  # True while the worker runs
    motor_published = Signal(object)  # MotorParams now in the Session
    identification_done = Signal(object)  # core MethodComparison
    identification_failed = Signal(str)

    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session
        self.title = TITLE
        self.bench: BenchTests | None = None
        self.points_file: LoadPointsFile | None = None
        self.result: ident.MethodComparison | None = None
        self._worker: CoreWorker | None = None

        root = QHBoxLayout(self)
        left = QWidget()
        left.setFixedWidth(LEFT_WIDTH)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(self._machine_group())
        lv.addWidget(self._data_group())
        lv.addWidget(self._method_group())
        buttons = QHBoxLayout()
        self.btn_identify = QPushButton("Identifier")
        self.btn_identify.setMinimumHeight(34)
        self.btn_identify.setStyleSheet(
            "QPushButton { background: #2f6fd6; color: white; font-weight: bold; border-radius: 4px; }"
            "QPushButton:disabled { background: #9db7e6; }"
        )
        self.btn_identify.clicked.connect(self.identify)
        self.btn_pdf = QPushButton("Exporter PDF")
        self.btn_pdf.setMinimumHeight(34)
        self.btn_pdf.setEnabled(False)
        self.btn_pdf.setToolTip("Rapport PDF : étape 9 de la feuille de route")
        buttons.addWidget(self.btn_identify, 3)
        buttons.addWidget(self.btn_pdf, 2)
        lv.addLayout(buttons)
        lv.addStretch(1)
        root.addWidget(left)

        right = QVBoxLayout()
        right.addWidget(self._plot_card(), 3)
        right.addWidget(self._table_card(), 1)
        root.addLayout(right, 1)
        self._refresh_table()
        self._refresh_plots()

    # --- building blocks ---------------------------------------------------------

    def _machine_group(self) -> QGroupBox:
        m = self.session.motor
        box = QGroupBox("Machine")
        form = QFormLayout(box)
        self.spin_v = _spin(1.0, 1e5, 1, "V", m.v_phase)
        self.spin_f = _spin(0.1, 1e3, 1, "Hz", m.f_rated)
        self.spin_p = QSpinBox()
        self.spin_p.setRange(1, 24)
        self.spin_p.setValue(m.pole_pairs)
        self.spin_p.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.spin_r1 = _spin(0.0, 1e3, 4, "Ω", m.r1)
        self.spin_r1.setToolTip("Résistance d'une phase statorique (essai DC) ; 0 = R1 négligée (TD5)")
        self.spin_t_r1 = _spin(-50.0, 250.0, 1, "°C", 20.0)
        self.spin_t_r1.setToolTip("Température du bobinage lors de la mesure de R1")
        self.combo_layout = QComboBox()
        for key, label in LAYOUTS:
            self.combo_layout.addItem(label, key)
        self.lbl_speed = QLabel("—")
        self.lbl_speed.setToolTip("Lue dans la plaque signalétique du fichier d'essais")
        form.addRow("Tension simple", self.spin_v)
        form.addRow("Fréquence", self.spin_f)
        form.addRow("Paires de pôles", self.spin_p)
        form.addRow("R1 (DC)", self.spin_r1)
        form.addRow("Température R1", self.spin_t_r1)
        form.addRow("Schéma", self.combo_layout)
        self.lbl_layout_note = QLabel("Le schéma (TP3 / bornes) ne change pas les formules classiques ; "
                                      "il fixe le circuit de l'optimisation sur les points en charge "
                                      "et celui des onglets 2 à 7.")
        self.lbl_layout_note.setWordWrap(True)
        self.lbl_layout_note.setStyleSheet("color: #666; font-size: 11px;")
        form.addRow(self.lbl_layout_note)
        form.addRow("Vitesse nominale", self.lbl_speed)
        return box

    def _data_group(self) -> QGroupBox:
        box = QGroupBox("Essais (CSV)")
        grid = QGridLayout(box)
        self.lbl_bench = QLabel("Essais DC, à vide, rotor bloqué : —")
        self.lbl_points = QLabel("Points en charge : —")
        self.btn_bench = QPushButton("Charger…")
        self.btn_points = QPushButton("Charger…")
        self.btn_bench_preview = QPushButton("Aperçu")
        self.btn_points_preview = QPushButton("Aperçu")
        for lbl in (self.lbl_bench, self.lbl_points):
            lbl.setWordWrap(True)
        self.btn_bench.clicked.connect(lambda: self._choose(self.load_bench_file))
        self.btn_points.clicked.connect(lambda: self._choose(self.load_points_file))
        self.btn_bench_preview.clicked.connect(self.preview_bench)
        self.btn_points_preview.clicked.connect(self.preview_points)
        self.btn_bench_preview.setEnabled(False)
        self.btn_points_preview.setEnabled(False)
        grid.addWidget(self.lbl_bench, 0, 0, 1, 2)
        grid.addWidget(self.btn_bench, 1, 0)
        grid.addWidget(self.btn_bench_preview, 1, 1)
        grid.addWidget(self.lbl_points, 2, 0, 1, 2)
        grid.addWidget(self.btn_points, 3, 0)
        grid.addWidget(self.btn_points_preview, 3, 1)
        self.btn_demo = QPushButton("Charger la démo (TD5 Ex 1, bruit 2,5 %)")
        self.btn_demo.clicked.connect(self.load_demo)
        grid.addWidget(self.btn_demo, 4, 0, 1, 2)
        return box

    def _method_group(self) -> QGroupBox:
        box = QGroupBox("Méthode")
        lay = QVBoxLayout(box)
        self.method_group = QButtonGroup(self)
        self.radios: dict[str, QRadioButton] = {}
        for k, (key, label) in enumerate(METHODS):
            rb = QRadioButton(label)
            self.radios[key] = rb
            self.method_group.addButton(rb, k)
            lay.addWidget(rb)
        self.radios["fit"].setChecked(True)
        return box

    PLOTS = (  # key, title, x label, y label, grid row, grid column
        ("torque_speed", "Couple–vitesse", "vitesse (tr/min)", "Couple (N·m)", 0, 0),
        ("torque_slip", "Couple–glissement", "glissement g", "Couple (N·m)", 0, 1),
        ("current_speed", "Courant–vitesse", "vitesse (tr/min)", "Courant absorbé (A)", 1, 0),
        ("current_slip", "Courant–glissement", "glissement g", "Courant absorbé (A)", 1, 1),
    )

    def _plot_card(self) -> QFrame:
        card, lay, head = _card("Caractéristiques : modèle et points d'essai")
        self.lbl_legend = QLabel("")  # one legend shared by the four plots
        self.lbl_legend.setTextFormat(Qt.TextFormat.RichText)
        head.insertWidget(1, self.lbl_legend)
        self.chip_demo = chip("points synthétiques (démo)")
        self.chip_demo.setVisible(False)
        head.addWidget(self.chip_demo)
        pg.setConfigOptions(antialias=True, background="w", foreground="#333")
        self.plot_grid = QGridLayout()
        self.plot_grid.setSpacing(4)
        self.plots: dict[str, pg.PlotWidget] = {}
        for key, title, xlab, ylab, row, col in self.PLOTS:
            pw = pg.PlotWidget()
            pw.setTitle(title, size="10pt")
            pw.setLabel("bottom", xlab)
            pw.setLabel("left", ylab)
            pw.showGrid(x=True, y=True, alpha=0.25)
            self.plots[key] = pw
            self.plot_grid.addWidget(pw, row, col)
        self.plot_torque = self.plots["torque_slip"]
        self.plot_current = self.plots["current_slip"]
        lay.addLayout(self.plot_grid)
        return card

    def _table_card(self) -> QFrame:
        card, lay, head = _card("Paramètres identifiés")
        self.lbl_table_note = QLabel("")
        self.lbl_table_note.setStyleSheet("color: #666;")
        head.insertWidget(1, self.lbl_table_note)
        self.table = QTableWidget(len(ROWS), 1 + len(COLUMNS))
        self.table.setHorizontalHeaderLabels(["Méthode"] + [label for _, label in COLUMNS])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setMinimumHeight(130)
        lay.addWidget(self.table)
        return card

    # --- data loading --------------------------------------------------------------

    def _choose(self, loader) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Charger un fichier d'essais", "", "CSV (*.csv)")
        if path:
            loader(path)

    def _set_status(self, label: QLabel, ok: bool, text: str) -> None:
        label.setText(text)
        label.setStyleSheet("color: #1e7d3a;" if ok else "color: #b3261e;")

    def load_bench_file(self, path) -> bool:
        """Load the bench-test CSV; on error, show the loader's French message. Returns success."""
        try:
            bench = load_bench_tests(path)
            plate = nameplate(bench.meta)
        except LoaderError as exc:
            self.bench = None
            self._set_status(self.lbl_bench, False, f"Essais : {exc}")
            self.btn_bench_preview.setEnabled(False)
            self.status_message.emit(str(exc))
            self._refresh_chip()
            return False
        self.bench = bench
        name = _name(path)
        if plate.v_phase is not None:
            self.spin_v.setValue(plate.v_phase)
        if plate.f is not None:
            self.spin_f.setValue(plate.f)
        if plate.pole_pairs is not None:
            self.spin_p.setValue(plate.pole_pairs)
        self.lbl_speed.setText("—" if plate.rated_speed is None
                               else f"{fr_fixed(plate.rated_speed * RAD_S_TO_RPM, 0)} tr/min")
        if bench.dc is not None:
            self.spin_r1.setValue(ident.r1_from_dc(bench.dc))
            self.spin_t_r1.setValue(bench.dc.temperature_k - T_ZERO_C)
        parts = [f"{len(bench.no_load)} à vide", "1 rotor bloqué", "DC ✓" if bench.dc else "sans DC"]
        if bench.winding_temperature_k is not None:
            parts.append(f"bobinage {fr_fixed(bench.winding_temperature_k - T_ZERO_C, 0)} °C")
        demo = " (démo)" if bench.is_demo else ""
        self._set_status(self.lbl_bench, True, f"{name} — chargé{demo}\n" + " · ".join(parts))
        self.btn_bench_preview.setEnabled(True)
        self.status_message.emit(f"Essais chargés : {name}{demo}")
        self._refresh_chip()
        self._refresh_table()
        return True

    def load_points_file(self, path) -> bool:
        """Load the load-point CSV; on error, show the loader's French message. Returns success."""
        try:
            lp = load_load_points(path)
        except LoaderError as exc:
            self.points_file = None
            self._set_status(self.lbl_points, False, f"Points en charge : {exc}")
            self.btn_points_preview.setEnabled(False)
            self.status_message.emit(str(exc))
            self._refresh_chip()
            self._refresh_plots()
            return False
        self.points_file = lp
        g = [p.slip for p in lp.points]
        demo = " (démo)" if lp.is_demo else ""
        self._set_status(self.lbl_points, True,
                         f"{_name(path)} — chargé{demo}\n{len(lp.points)} points, "
                         f"g = {fr(min(g), 2)} … {fr(max(g), 2)}")
        self.btn_points_preview.setEnabled(True)
        self.status_message.emit(f"Points en charge chargés : {_name(path)}{demo}")
        self._refresh_chip()
        self._refresh_plots()
        return True

    def load_demo(self) -> None:
        from evlab.io.paths import data_dir

        data = data_dir()
        self.load_bench_file(data / demo_data.BENCH_FILE)
        self.load_points_file(data / demo_data.LOAD_FILE)

    def preview_bench(self) -> _PreviewDialog | None:
        if self.bench is None:
            return None
        b = self.bench
        rows = []
        if b.dc:
            rows.append(["dc", f"U_dc = {fr(b.dc.v_dc, 4)}", fr(b.dc.i_dc, 4), "—", "—",
                         fr_fixed(b.dc.temperature_k - T_ZERO_C, 1)])
        for kind, tests in (("vide", b.no_load), ("rotor bloqué", (b.locked,))):
            for t in tests:
                rows.append([kind, fr(t.v_phase, 4), fr(t.i_line, 4), fr(t.p_total, 4), fr(t.f, 3), "—"])
        dlg = _PreviewDialog(self, f"Aperçu — {_name(b.path)}",
                             ["Essai", "V simple (V)", "I (A)", "P (W)", "f (Hz)", "T (°C)"], rows)
        dlg.show()
        return dlg

    def preview_points(self) -> _PreviewDialog | None:
        if self.points_file is None:
            return None
        rows = [[fr(p.slip, 3), fr(p.v_phase, 4), fr(p.i_line, 4), fr(p.torque, 4), fr(p.power_factor, 3)]
                for p in self.points_file.points]
        dlg = _PreviewDialog(self, f"Aperçu — {_name(self.points_file.path)}",
                             ["g", "V simple (V)", "I (A)", "T (N·m)", "cos φ"], rows)
        dlg.show()
        return dlg

    def _is_demo(self) -> bool:
        return bool((self.bench and self.bench.is_demo) or (self.points_file and self.points_file.is_demo))

    def _refresh_chip(self) -> None:
        self.chip_demo.setVisible(self._is_demo())
        self.lbl_table_note.setText("(données synthétiques bruitées, démo)" if self._is_demo() else "")

    # --- identification ------------------------------------------------------------

    def method(self) -> str:
        return next(k for k, rb in self.radios.items() if rb.isChecked())

    def records(self) -> ident.TestRecords:
        """Core TestRecords from the loaded file and the Machine fields (raises ValueError)."""
        if self.bench is None:
            raise ValueError("chargez d'abord le fichier d'essais (DC, à vide, rotor bloqué)")
        r1 = self.spin_r1.value()
        dc = ident.DcTest.from_resistance(r1, self.spin_t_r1.value() + T_ZERO_C) if r1 > 0 else None
        b = self.bench
        return ident.TestRecords(
            dc=dc,
            t_hot_k=b.winding_temperature_k if dc else None,
            no_load=b.no_load,
            locked=b.locked,
            pole_pairs=self.spin_p.value(),
            v_rated=self.spin_v.value(),
            f_rated=self.spin_f.value(),
            p_mech=None if len({t.v_phase for t in b.no_load}) >= 2 else 0.0,
        )

    def identify(self) -> bool:
        """Start the identification in a pool thread. Returns False if the inputs are refused."""
        method = self.method()
        try:
            records = self.records()
            if method != "classical" and self.points_file is None:
                raise ValueError("l'optimisation a besoin du fichier de points en charge")
        except ValueError as exc:
            msg = f"Identification impossible : {exc}"
            self.status_message.emit(msg)
            self.identification_failed.emit(msg)
            return False
        reference = reference_motor(self.bench.meta) if self.bench else None
        worker = CoreWorker(
            ident.compare_methods,
            records,
            method,
            points=self.points_file.points if self.points_file else None,
            layout=self.combo_layout.currentData(),
            reference=reference,
            is_demo=self._is_demo(),
            source="Identification TP3",
        )
        worker.signals.progress.connect(lambda stage: self.status_message.emit(STAGES.get(stage, stage)))
        worker.signals.finished.connect(self._on_done)
        worker.signals.failed.connect(self._on_failed)
        self._worker = worker
        self.btn_identify.setEnabled(False)
        self.busy.emit(True)
        self.status_message.emit("Identification en cours…")
        QThreadPool.globalInstance().start(worker)
        return True

    def _on_done(self, result: ident.MethodComparison) -> None:
        self.result = result
        self.btn_identify.setEnabled(True)
        self.busy.emit(False)
        self._refresh_table()
        self._refresh_plots()
        self.session.set_motor(result.published)
        self.motor_published.emit(result.published)
        label = "optimisation" if result.fit is not None else "formules classiques"
        msg = f"Identification terminée ({label}) — moteur publié pour les onglets 2 à 7"
        if result.fit is not None and result.fit.high_correlation:
            pairs = ", ".join(f"{PARAM_LABELS[a]}–{PARAM_LABELS[b]} ρ = {fr_fixed(rho, 2)}"
                              for a, b, rho in result.fit.high_correlation)
            msg += f" ⚠ paramètres mal séparés par les données : {pairs}"
        self.status_message.emit(msg)
        self.identification_done.emit(result)

    def _on_failed(self, message: str) -> None:
        self.btn_identify.setEnabled(True)
        self.busy.emit(False)
        msg = f"Échec de l'identification : {message}"
        self.status_message.emit(msg)
        self.identification_failed.emit(msg)

    # --- drawing -----------------------------------------------------------------------

    def _refresh_table(self) -> None:
        res = self.result
        reference = res.reference if res else (reference_motor(self.bench.meta) if self.bench else None)
        bold = QFont()
        bold.setBold(True)
        for r, row in enumerate(ROWS):
            if row == "reference":
                label = f"Référence ({reference.source})" if reference else "Référence"
            else:
                label = ROW_LABELS[row]
            self.table.setItem(r, 0, QTableWidgetItem(label))
            for c, (name, _) in enumerate(COLUMNS, start=1):
                item = QTableWidgetItem("—")
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if row == "reference" and reference is not None:
                    value = getattr(reference, name)
                    item.setText(fr(value))
                    item.setData(VALUE_ROLE, value)
                elif res is not None and row in res.shown:
                    value = getattr(res.motor(row), name)
                    err = res.errors[row][name]
                    item.setText(fr(value) + (f" ({fr_pct(err)})" if err is not None else ""))
                    item.setData(VALUE_ROLE, value)
                    item.setToolTip(self._tooltip(row, name))
                elif res is not None and row == "classical":
                    item.setToolTip("calculé comme point de départ de l'optimisation ; "
                                    "choisir « Comparer les deux » pour l'afficher")
                self.table.setItem(r, c, item)
            if res is not None and row == "fit" and row in res.shown:
                for c in range(self.table.columnCount()):
                    self.table.item(r, c).setFont(bold)

    def _tooltip(self, row: str, name: str) -> str:
        res = self.result
        if row == "fit" and res is not None and res.fit is not None:
            if name in res.fit.ci95:
                lo, hi = res.fit.ci95[name]
                return f"Intervalle de confiance à 95 % : [{fr(lo, 4)} ; {fr(hi, 4)}] Ω"
            return "Rf n'est pas ajustée : elle vient de l'essai à vide (voir A13)"
        return "Formules classiques (TP3 / TD5)"

    def _refresh_plots(self) -> None:
        for pw in self.plots.values():
            pw.clear()
        legend = []
        res = self.result
        t_top = 0.0
        if res is not None:
            g = np.linspace(0.0, 1.0, 401)[1:]  # g ∈ (0, 1]: motoring, from near no-load to standstill
            for row in res.shown:
                m = res.motor(row)
                pen = pg.mkPen(COLORS[row], width=2)
                name = f"modèle ({ROW_LABELS[row].lower()})"
                n = np.asarray(circuit.mechanical_speed(m, g)) * RAD_S_TO_RPM
                t, i = circuit.torque(m, g), circuit.stator_current(m, g)
                t_top = max(t_top, float(np.max(t)))
                for key, x, y in (("torque_speed", n, t), ("torque_slip", g, t),
                                  ("current_speed", n, i), ("current_slip", g, i)):
                    self.plots[key].plot(x, y, pen=pen, name=name)
                legend.append(f"<span style='color:{COLORS[row]}'>━━</span> {name}")
            g_c, t_max = circuit.breakdown(res.published)
            text = pg.TextItem(f"C_max = {fr(t_max, 4)} N·m\ng_c = {fr_fixed(g_c, 2)}",
                               color="#333", anchor=(-0.1, 1.1))
            text.setPos(g_c, t_max)
            self.plot_torque.addItem(text)
            self.plot_torque.plot([g_c], [t_max], pen=None, symbol="+", symbolSize=12,
                                  symbolPen=pg.mkPen("#333"))
        if self.points_file is not None:
            pts = self.points_file.points
            demo = " (démo)" if self.points_file.is_demo else ""
            name = f"points d'essai{demo}"
            kw = dict(pen=None, symbol="o", symbolSize=6, symbolBrush=None,
                      symbolPen=pg.mkPen(COLORS["points"], width=1.5), name=name)
            m = res.published if res is not None else self._plate_motor()
            g = [p.slip for p in pts]
            n = [float(circuit.mechanical_speed(m, p.slip, f=p.f)) * RAD_S_TO_RPM for p in pts]
            t, i = [p.torque for p in pts], [p.i_line for p in pts]
            for key, x, y in (("torque_speed", n, t), ("torque_slip", g, t),
                              ("current_speed", n, i), ("current_slip", g, i)):
                self.plots[key].plot(x, y, **kw)
            legend.append(f"<span style='color:{COLORS['points']}'>○</span> {name}")
        self.lbl_legend.setText("&nbsp;&nbsp;&nbsp;".join(legend))
        if t_top > 0:  # headroom above the curves for the C_max / g_c label, same scale on both torque plots
            for key in ("torque_speed", "torque_slip"):
                self.plots[key].setYRange(0.0, 1.35 * t_top, padding=0)

    def _plate_motor(self):
        """Session motor with the pole pairs of the Machine fields (point speeds before identification)."""
        from dataclasses import replace

        return replace(self.session.motor, pole_pairs=self.spin_p.value())


def _name(path) -> str:
    from pathlib import Path

    return Path(str(path)).name
