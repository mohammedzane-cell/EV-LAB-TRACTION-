"""Tab "7 · Optimisation": Pareto front Wh/km vs 0–50 km/h on the tested models (core.optimise).

Thin view: bounds and budget in, core.optimise.pareto_front in a QThreadPool
worker (progress, cancel), Pareto plot with clickable points, baseline vs
selected design table with the gain in % per KPI, and loading a design into
all tabs. Every number comes from core/; this module only converts units for
display (K → °C, ratios → %).
"""

from __future__ import annotations

import math
import os

import pyqtgraph as pg
from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from evlab.core import optimise as op
from evlab.core import thermal
from evlab.core.session import Session
from evlab.gui.format import fr, fr_fixed, fr_pct
from evlab.gui.widgets import card, chip, french_spin
from evlab.gui.workers import CoreWorker
from evlab.io.notes import R1_ZERO_NOTE

TITLE = "7 · Optimisation"
LEFT_WIDTH = 300
T_ZERO_C = 273.15
VAR_ROWS = (  # name, label, unit, decimals, low, high, scale (display = value × scale)
    ("gear_ratio", "Rapport G", "", 2, 2.5, 4.5, 1.0),
    ("boost", "Boost V/f", "V", 1, 0.0, 8.0, 1.0),
    ("margin", "Marge", "%", 0, 0.60, 0.95, 100.0),
    ("k_n", "Rebobinage k_N", "", 3, 0.85, 1.20, 1.0),
)
KPI_ROWS = (  # key, label, unit, converter for display
    ("wh_per_km", "Consommation", "Wh/km", lambda v: fr(v)),
    ("t_0_50", "0–50 km/h", "s", lambda v: fr(v)),
    ("t_winding_max", "T max bobinage", "°C", lambda v: fr_fixed(v - T_ZERO_C, 1)),
    ("min_margin", "Marge couple (cycle)", "", lambda v: fr(v)),
    ("i_cycle_max", "Courant max (cycle)", "A", lambda v: fr(v)),
)


class OptimisationTab(QWidget):
    """Tab 7: bounds → Pareto front; pick a design and load it into every tab."""

    status_message = Signal(str)
    busy = Signal(bool)
    pareto_done = Signal(object)  # core.optimise.ParetoResult
    pareto_failed = Signal(str)
    design_selected = Signal(object)  # Evaluation
    load_design = Signal(object, object)  # (base MotorParams, Design)

    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session
        self.title = TITLE
        self.problem_provider = None  # set by the main window: () -> core.optimise.Problem
        self.problem: op.Problem | None = None
        self.result: op.ParetoResult | None = None
        self.selected: op.Evaluation | None = None
        self._cancel = False
        self._worker: CoreWorker | None = None

        root = QHBoxLayout(self)
        left = QWidget()
        left.setFixedWidth(LEFT_WIDTH)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        box = QGroupBox("Bornes des variables")
        grid = QGridLayout(box)
        grid.addWidget(QLabel("min"), 0, 1)
        grid.addWidget(QLabel("max"), 0, 2)
        self.bound_spins: dict[str, tuple] = {}
        for r, (name, label, unit, dec, lo, hi, scale) in enumerate(VAR_ROWS, start=1):
            s_lo = french_spin(0.0, 1e3, dec, unit, lo * scale)
            s_hi = french_spin(0.0, 1e3, dec, unit, hi * scale)
            lbl = QLabel(label)
            lbl.setToolTip({"gear_ratio": "Rapport de réduction G = ωm/ωroue",
                            "boost": "Tension de la loi V/f à f → 0",
                            "margin": "Fraction utilisable du couple de décrochage",
                            "k_n": "Spires × k_N à section de cuivre constante"}[name])
            grid.addWidget(lbl, r, 0)
            grid.addWidget(s_lo, r, 1)
            grid.addWidget(s_hi, r, 2)
            self.bound_spins[name] = (s_lo, s_hi, scale)
        hint = QLabel("min = max fixe la variable. k_N : spires × k_N à section de cuivre constante.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #555;")
        grid.addWidget(hint, len(VAR_ROWS) + 1, 0, 1, 3)
        lv.addWidget(box)

        budget = QGroupBox("Budget (évolution différentielle)")
        bf = QFormLayout(budget)
        self.spin_points = QSpinBox()
        self.spin_points.setRange(2, 20)
        self.spin_points.setValue(6)
        self.spin_pop = QSpinBox()
        self.spin_pop.setRange(3, 50)
        self.spin_pop.setValue(15)
        self.spin_budget = QSpinBox()
        self.spin_budget.setRange(6, 50_000)
        self.spin_budget.setSingleStep(100)
        self.spin_budget.setValue(op.BUDGET)
        self.spin_budget.setToolTip("Budget fixe d'évaluations par point de Pareto, quel que soit le nombre "
                                    "de variables libres : générations = budget / (population × variables) − 1")
        self.spin_workers = QSpinBox()
        self.spin_workers.setRange(1, max(1, os.cpu_count() or 1))
        self.spin_workers.setValue(max(1, os.cpu_count() or 1))
        self.spin_seed = QSpinBox()
        self.spin_seed.setRange(0, 10_000)
        bf.addRow("Points de Pareto", self.spin_points)
        bf.addRow("Population (× variables)", self.spin_pop)
        bf.addRow("Évaluations / point", self.spin_budget)
        bf.addRow("Processus", self.spin_workers)
        bf.addRow("Graine", self.spin_seed)
        self.lbl_budget = QLabel("")
        self.lbl_budget.setWordWrap(True)
        self.lbl_budget.setStyleSheet("color: #555;")
        bf.addRow(self.lbl_budget)
        lv.addWidget(budget)

        self.btn_run = QPushButton("Lancer l'optimisation")
        self.btn_run.setMinimumHeight(34)
        self.btn_run.setStyleSheet(
            "QPushButton { background: #2f6fd6; color: white; font-weight: bold; border-radius: 4px; }"
            "QPushButton:disabled { background: #9db7e6; }"
        )
        self.btn_run.clicked.connect(self.run)
        self.btn_cancel = QPushButton("Annuler")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel)
        self.progress = QProgressBar()
        self.progress.setFormat("%v / %m évaluations")
        row = QHBoxLayout()
        row.addWidget(self.btn_run, 2)
        row.addWidget(self.btn_cancel, 1)
        lv.addLayout(row)
        lv.addWidget(self.progress)
        lv.addStretch(1)
        root.addWidget(left)

        right = QVBoxLayout()
        plot_card, pl, head = card("Front de Pareto : consommation vs 0–50 km/h")
        self.chip_demo = chip("démo")
        self.chip_demo.setVisible(False)
        head.addWidget(self.chip_demo)
        self.chip_r1 = chip(R1_ZERO_NOTE)
        self.chip_r1.setStyleSheet(self.chip_r1.styleSheet().replace("color: #555", "color: #b3261e"))
        head.addWidget(self.chip_r1)
        self.on_motor_changed()
        pg.setConfigOptions(antialias=True, background="w", foreground="#333")
        self.plot = pg.PlotWidget()
        self.plot.setLabel("bottom", "0–50 km/h (s)")
        self.plot.setLabel("left", "Consommation (Wh/km)")
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.addLegend(offset=(-10, 10))
        pl.addWidget(self.plot)
        self.lbl_click = QLabel("Cliquer un point du front pour le sélectionner.")
        self.lbl_click.setStyleSheet("color: #555;")
        pl.addWidget(self.lbl_click)
        right.addWidget(plot_card, 3)

        tab_card, tl, thead = card("Base vs design sélectionné")
        self.btn_load = QPushButton("Charger ce design dans tous les onglets")
        self.btn_load.setEnabled(False)
        self.btn_load.clicked.connect(self._load_selected)
        thead.addWidget(self.btn_load)
        tables = QHBoxLayout()
        self.kpi_table = self._table(len(KPI_ROWS), ["KPI", "Base", "Sélection", "Gain"])
        self.var_table = self._table(len(VAR_ROWS), ["Variable", "Base", "Sélection"])
        tables.addWidget(self.kpi_table, 3)
        tables.addWidget(self.var_table, 2)
        tl.addLayout(tables)
        right.addWidget(tab_card, 2)
        root.addLayout(right, 1)
        for s in (self.spin_points, self.spin_pop, self.spin_budget):
            s.valueChanged.connect(lambda _v: self._show_budget())
        for s_lo, s_hi, _ in self.bound_spins.values():
            s_lo.valueChanged.connect(lambda _v: self._show_budget())
            s_hi.valueChanged.connect(lambda _v: self._show_budget())
        self._show_budget()

    @staticmethod
    def _table(rows: int, headers: list[str]) -> QTableWidget:
        t = QTableWidget(rows, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        return t

    # --- inputs -------------------------------------------------------------------

    def on_motor_changed(self) -> None:
        """Tab 1 published a motor: warn that the thermal constraint is not meaningful when R1 = 0."""
        self.chip_r1.setVisible(thermal.stator_copper_missing(self.session.motor))

    def bounds(self) -> op.Bounds:
        vals = {name: (lo.value() / sc, hi.value() / sc) for name, (lo, hi, sc) in self.bound_spins.items()}
        return op.Bounds(**vals)

    def _per_point(self) -> tuple[int, int, int]:
        """(free variables, generations, evaluations per Pareto point), from core.optimise."""
        try:
            n_free = len(self.bounds().free())
        except ValueError:
            return 0, 0, 0
        if n_free == 0:
            return 0, 0, 0
        pop = self.spin_pop.value()
        gens = op.generations(self.spin_budget.value(), pop, n_free)
        return n_free, gens, op.run_evaluations(pop, n_free, gens)

    def expected_evaluations(self) -> int:
        return self.spin_points.value() * self._per_point()[2]

    def _show_budget(self) -> None:
        n_free, gens, per = self._per_point()
        self.lbl_budget.setText(f"{n_free} variable(s) libre(s) → {gens} générations, {per} évaluations par point ; "
                                f"{self.expected_evaluations()} au total ({self.spin_points.value()} points)")

    # --- run -------------------------------------------------------------------

    def run(self) -> bool:
        """Start the ε-constraint sweep in a pool thread. Returns False if the inputs are refused."""
        try:
            if self.problem_provider is None:
                raise ValueError("problème non défini")
            problem = self.problem_provider()
            bounds = self.bounds()
            if not bounds.free():
                raise ValueError("toutes les variables sont fixées (min = max)")
        except ValueError as exc:
            msg = f"Optimisation impossible : {exc}"
            self.status_message.emit(msg)
            self.pareto_failed.emit(msg)
            return False
        self.problem = problem
        self._cancel = False
        kw = dict(n_points=self.spin_points.value(), seed=self.spin_seed.value(), popsize=self.spin_pop.value(),
                  budget=self.spin_budget.value(), workers=self.spin_workers.value())

        def job(progress):
            return op.pareto_front(problem, bounds, progress=lambda k, n: progress(f"{k}:{n}"),
                                   cancelled=lambda: self._cancel, **kw)

        worker = CoreWorker(job)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(self._on_done)
        worker.signals.failed.connect(self._on_failed)
        self._worker = worker
        self.progress.setRange(0, self.expected_evaluations())
        self.progress.setValue(0)
        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.busy.emit(True)
        self.status_message.emit("Optimisation en cours…")
        QThreadPool.globalInstance().start(worker)
        return True

    def cancel(self) -> None:
        self._cancel = True
        self.status_message.emit("Annulation demandée (fin de la génération en cours)…")

    def _on_progress(self, text: str) -> None:
        k, n = (int(x) for x in text.split(":"))
        self.progress.setValue(min(n, self.progress.maximum()))
        self.status_message.emit(f"Optimisation : point {k + 1}/{self.spin_points.value()}, {n} évaluations")

    def _on_done(self, result: op.ParetoResult) -> None:
        self.result = result
        self._finish()
        self.chip_demo.setVisible(self.session.motor.is_demo or self.problem.cycle.is_demo
                                  or self.problem.vehicle.is_demo)
        self._draw()
        if result.front:
            self.select(min(result.front, key=lambda e: e.wh_per_km))
        state = "annulée" if result.message == "cancelled" else "terminée"
        self.status_message.emit(f"Optimisation {state} : {len(result.log)} évaluations, "
                                 f"{len(result.front)} points sur le front")
        self.pareto_done.emit(result)

    def _on_failed(self, message: str) -> None:
        self._finish()
        msg = f"Échec de l'optimisation : {message}"
        self.status_message.emit(msg)
        self.pareto_failed.emit(msg)

    def _finish(self) -> None:
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.busy.emit(False)

    # --- plot and tables ------------------------------------------------------------

    def _draw(self) -> None:
        r = self.result
        self.plot.clear()
        feas = [e for e in r.log if e.feasible and math.isfinite(e.t_0_50)]
        if feas:
            self.plot.plot([e.t_0_50 for e in feas], [e.wh_per_km for e in feas], pen=None, symbol="o",
                           symbolSize=4, symbolBrush=(150, 150, 150, 90), symbolPen=None,
                           name="évaluations admissibles")
        self.front_item = pg.ScatterPlotItem(
            [e.t_0_50 for e in r.front], [e.wh_per_km for e in r.front], size=11,
            brush=pg.mkBrush("#2e9e5b"), pen=pg.mkPen("#1b5e35"), data=list(range(len(r.front))),
            hoverable=True, name="front de Pareto")
        self.front_item.sigClicked.connect(self._clicked)
        self.plot.addItem(self.front_item)
        self.plot.plot([e.t_0_50 for e in r.front], [e.wh_per_km for e in r.front],
                       pen=pg.mkPen("#2e9e5b", width=1, style=Qt.PenStyle.DashLine))
        b = r.baseline
        if math.isfinite(b.t_0_50):
            self.plot.plot([b.t_0_50], [b.wh_per_km], pen=None, symbol="star", symbolSize=16,
                           symbolBrush="#e08a1e", symbolPen=pg.mkPen("#8a5208"), name="base")

    def _clicked(self, _item, points, _ev=None) -> None:
        if points:
            self.select(self.result.front[int(points[0].data())])

    def select(self, e: op.Evaluation) -> None:
        """Show a design against the baseline."""
        self.selected = e
        b = self.result.baseline
        g = op.kpi_changes(b, e)
        for r, (key, label, unit, conv) in enumerate(KPI_ROWS):
            value, kind = g[key]
            change = (fr_pct(value) if kind == "%" else f"{fr_fixed(value, 1)} K".replace("-", "−", 1)
                      if math.isfinite(value) else "")
            cells = (f"{label}" + (f" ({unit})" if unit else ""), conv(getattr(b, key)), conv(getattr(e, key)),
                     change or "—")
            for c, text in enumerate(cells):
                it = QTableWidgetItem(text)
                if c:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if c == 3 and key in ("wh_per_km", "t_0_50") and math.isfinite(value):
                    it.setForeground(pg.mkColor("#1e7d3a" if value < 0 else "#b3261e"))
                self.kpi_table.setItem(r, c, it)
        for r, (name, label, unit, dec, _lo, _hi, sc) in enumerate(VAR_ROWS):
            cells = (label + (f" ({unit})" if unit else ""), fr_fixed(getattr(b.design, name) * sc, dec),
                     fr_fixed(getattr(e.design, name) * sc, dec))
            for c, text in enumerate(cells):
                it = QTableWidgetItem(text)
                if c:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.var_table.setItem(r, c, it)
        self.btn_load.setEnabled(True)
        self.lbl_click.setText(f"Sélection : {fr(e.wh_per_km)} Wh/km, {fr(e.t_0_50)} s pour 0–50 km/h")
        self.design_selected.emit(e)

    def _load_selected(self) -> None:
        if self.selected is not None and self.problem is not None:
            self.load_design.emit(self.problem.motor, self.selected.design)
            self.status_message.emit("Design chargé dans les onglets 1 à 6")
