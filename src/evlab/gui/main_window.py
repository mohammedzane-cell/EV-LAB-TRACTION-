"""Main window: seven tabs sharing one Session (one motor, one chain) and a status bar."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from PySide6.QtCore import QThreadPool, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QFileDialog, QInputDialog, QLabel, QMainWindow, QProgressBar, QTabWidget

from evlab.core.session import Session
from evlab.gui.tab_efficiency import EfficiencyTab
from evlab.gui.tab_envelope import EnvelopeTab
from evlab.gui.tab_identification import IdentificationTab
from evlab.gui.tab_optimisation import OptimisationTab
from evlab.gui.tab_thermal import ThermalTab
from evlab.gui.tab_vehicle import VehicleTab
from evlab.gui.tab_winding import WindingTab
from evlab.gui.workers import CoreWorker

WINDOW_TITLE = "EV-Traction Lab : Laboratoire virtuel de traction (ME3)"

TAB_CLASSES = (
    IdentificationTab,
    EnvelopeTab,
    EfficiencyTab,
    VehicleTab,
    ThermalTab,
    WindingTab,
    OptimisationTab,
)


def tab_label(title: str) -> str:
    """Escape '&' so Qt shows it instead of treating it as a shortcut marker."""
    return title.replace("&", "&&")


class MainWindow(QMainWindow):
    """EV-Traction Lab main window."""

    export_done = Signal(object)  # Path of the written file
    export_failed = Signal(str)

    def __init__(self, session: Session | None = None) -> None:
        super().__init__()
        self.session = session if session is not None else Session()
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(1280, 800)

        self.busy_bar = QProgressBar()
        self.busy_bar.setRange(0, 0)  # indeterminate
        self.busy_bar.setMaximumWidth(140)
        self.busy_bar.setVisible(False)
        self.statusBar().addPermanentWidget(self.busy_bar)
        self.statusBar().addPermanentWidget(QLabel("Python 3 · PySide6"))

        self.tabs = QTabWidget()
        for cls in TAB_CLASSES:
            tab = cls(self.session)
            self.tabs.addTab(tab, tab_label(tab.title))
            if hasattr(tab, "status_message"):
                tab.status_message.connect(lambda msg, t=tab: self._status_from(t, msg))
            if hasattr(tab, "busy"):
                tab.busy.connect(self.busy_bar.setVisible)
            if hasattr(tab, "motor_published"):
                tab.motor_published.connect(self._on_motor_published)
        self.setCentralWidget(self.tabs)
        self._build_menu()
        self._export_worker: CoreWorker | None = None
        self.group = "Groupe ME3"
        # tab 2 → tab 3: the efficiency map uses the drive settings and boundary of the envelope
        env_tab, eff_tab = self.tabs.widget(1), self.tabs.widget(2)
        if hasattr(env_tab, "envelope_done") and hasattr(eff_tab, "on_envelope"):
            env_tab.envelope_done.connect(eff_tab.on_envelope)
            if env_tab.envelope is not None:
                eff_tab.on_envelope(env_tab.envelope)
        # tabs 2, 3 → tab 4: the vehicle uses the envelope and the loss map; its cycle goes back to tab 3
        veh_tab = self.tabs.widget(3)
        if hasattr(veh_tab, "on_envelope"):
            env_tab.envelope_done.connect(veh_tab.on_envelope)
            eff_tab.map_done.connect(veh_tab.on_map)
            veh_tab.loss_settings_provider = eff_tab.settings
            veh_tab.cycle_points.connect(eff_tab.set_cycle_points)
        # tab 4 → tab 5: the thermal model is fed by the cycle losses
        th_tab = self.tabs.widget(4)
        if hasattr(th_tab, "on_cycle") and hasattr(veh_tab, "simulation_done"):
            veh_tab.simulation_done.connect(th_tab.on_cycle)
        # tab 7: the optimisation problem is assembled from tabs 1–5; a chosen design goes back to them
        opt_tab = self.tabs.widget(6)
        if hasattr(opt_tab, "problem_provider"):
            opt_tab.problem_provider = self.optimisation_problem
            opt_tab.load_design.connect(self.load_design)
        self.refresh_status()

    # --- reports -------------------------------------------------------------------

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu("Fichier")
        self.act_pdf = QAction("Exporter PDF…", self)
        self.act_pdf.setShortcut(QKeySequence("Ctrl+P"))
        self.act_pdf.triggered.connect(lambda: self._export_dialog("pdf"))
        self.act_excel = QAction("Exporter Excel…", self)
        self.act_excel.setShortcut(QKeySequence("Ctrl+E"))
        self.act_excel.triggered.connect(lambda: self._export_dialog("xlsx"))
        act_quit = QAction("Quitter", self)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        menu.addAction(self.act_pdf)
        menu.addAction(self.act_excel)
        menu.addSeparator()
        menu.addAction(act_quit)
        tab1 = self.tabs.widget(0)
        if hasattr(tab1, "btn_pdf"):
            tab1.btn_pdf.setEnabled(True)
            tab1.btn_pdf.setToolTip("Rapport PDF de toute la session (menu Fichier)")
            tab1.btn_pdf.clicked.connect(self.act_pdf.trigger)

    def _export_dialog(self, kind: str) -> None:
        group, ok = QInputDialog.getText(self, "Rapport", "Groupe / auteurs :", text=self.group)
        if not ok:
            return
        self.group = group or self.group
        name = f"ev_traction_{dt.date.today():%Y%m%d}.{kind}"
        filt = "PDF (*.pdf)" if kind == "pdf" else "Excel (*.xlsx)"
        path, _ = QFileDialog.getSaveFileName(self, "Exporter", name, filt)
        if path:
            self.export(kind, path, self.group)

    def snapshot(self, group: str):
        """io.snapshot.Snapshot of the current tabs (results not computed yet are left None)."""
        from evlab.core import winding as wd
        from evlab.io.snapshot import Snapshot

        t1, t2, t3, t4, t5, t6, t7 = (self.tabs.widget(i) for i in range(7))
        motor = self.session.motor
        dset, lset = t2.settings(), t3.settings()
        env = t2.envelope if t2.envelope is not None and t2.envelope.settings == dset else None
        emap = t3.emap if t3.emap is not None and t3.emap.envelope is env and t3.emap.settings == lset else None
        sizing = res = cycle = None
        if getattr(t4, "result", None) is not None:
            sizing, res, cycle, _, _ = t4.result
        thermal = t5.result if t5.result is not None and t5.cycle is not None and t5.cycle[0] is res else None
        return Snapshot(
            group=group, date=dt.date.today(), motor=motor, drive_settings=dset, loss_settings=lset,
            thermal_params=t5.params(), winding=t6.winding or wd.Winding(36, 4, 3, 7),
            identification=t1.result, envelope=env, emap=emap,
            vehicle=t4.vehicle() if cycle is not None else None, sizing=sizing, drive_result=res, cycle=cycle,
            thermal=thermal, insulation_class=t5.combo_class.currentData(), n_thermal_cycles=t5.spin_cycles.value(),
            pareto=t7.result,
        )

    def export(self, kind: str, path, group: str) -> bool:
        """Write the PDF report ("pdf") or the Excel workbook ("xlsx") in a worker thread."""
        from evlab.io import excel, report
        from evlab.io.snapshot import complete

        try:
            snap = self.snapshot(group)
        except ValueError as exc:
            self.statusBar().showMessage(f"Export impossible : {exc}")
            self.export_failed.emit(str(exc))
            return False
        build = report.build_report if kind == "pdf" else excel.build_workbook
        worker = CoreWorker(lambda progress: build(complete(snap), Path(path)))
        worker.signals.finished.connect(self._export_ok)
        worker.signals.failed.connect(self._export_ko)
        self._export_worker = worker
        self.busy_bar.setVisible(True)
        self.statusBar().showMessage(f"Export {kind.upper()} en cours…")
        QThreadPool.globalInstance().start(worker)
        return True

    def _export_ok(self, path) -> None:
        self.busy_bar.setVisible(False)
        self.statusBar().showMessage(f"Exporté : {path}")
        self.export_done.emit(path)

    def _export_ko(self, message: str) -> None:
        self.busy_bar.setVisible(False)
        self.statusBar().showMessage(f"Échec de l'export : {message}")
        self.export_failed.emit(message)

    def optimisation_problem(self):
        """core.optimise.Problem from the current state of tabs 1 to 5 (raises ValueError)."""
        from evlab.core import optimise

        env_tab, eff_tab, veh_tab, th_tab = (self.tabs.widget(i) for i in (1, 2, 3, 4))
        if getattr(veh_tab, "result", None) is None:
            raise ValueError("simulez d'abord le cycle dans l'onglet 4 · Véhicule & WLTC")
        _sizing, _res, cycle, _emap, _veh = veh_tab.result
        return optimise.Problem(
            motor=self.session.motor, drive=env_tab.settings(), loss_settings=eff_tab.settings(),
            vehicle=veh_tab.vehicle(), cycle=cycle, thermal=th_tab.params(),
            insulation_class=th_tab.combo_class.currentData(), n_thermal_cycles=th_tab.spin_cycles.value(),
        )

    def load_design(self, base_motor, design) -> None:
        """Load an optimised design into every tab: rewound motor, V/f law of tab 2, gear ratio of tab 4."""
        from evlab.core import optimise

        env_tab, veh_tab = self.tabs.widget(1), self.tabs.widget(3)
        motor = optimise.rewound(base_motor, design.k_n)
        env_tab.spin_boost.setValue(design.boost)
        env_tab.spin_margin.setValue(100.0 * design.margin)
        veh_tab.spin_g.setValue(design.gear_ratio)  # kept as the user's ratio, not re-proposed
        self.session.set_motor(motor)
        self._on_motor_published(motor)

    def _status_from(self, tab, message: str) -> None:
        """Show a tab's message only if that tab is visible (background recomputes stay quiet)."""
        if self.tabs.currentWidget() is tab:
            self.statusBar().showMessage(message)

    def _on_motor_published(self, _motor) -> None:
        """Tab 1 published a motor: update the status bar and let the other tabs recompute."""
        self.refresh_status(keep_message=True)
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if hasattr(tab, "on_motor_changed"):
                tab.on_motor_changed()

    def refresh_status(self, keep_message: bool = False) -> None:
        """Show which motor the whole chain is using (window title and status bar)."""
        m = self.session.motor
        demo = " (démo)" if m.is_demo else ""
        self.motor_text = f"Moteur : {m.source}{demo}"
        self.setToolTip(self.motor_text)
        if not keep_message:
            self.statusBar().showMessage(self.motor_text)
