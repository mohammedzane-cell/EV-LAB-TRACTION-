"""Main window: seven tabs sharing one Session (one motor, one chain) and a status bar."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QMainWindow, QProgressBar, QTabWidget

from evlab.core.session import Session
from evlab.gui.tab_efficiency import EfficiencyTab
from evlab.gui.tab_envelope import EnvelopeTab
from evlab.gui.tab_identification import IdentificationTab
from evlab.gui.tab_optimisation import OptimisationTab
from evlab.gui.tab_thermal import ThermalTab
from evlab.gui.tab_vehicle import VehicleTab
from evlab.gui.tab_winding import WindingTab

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
        # tab 2 → tab 3: the efficiency map uses the drive settings and boundary of the envelope
        env_tab, eff_tab = self.tabs.widget(1), self.tabs.widget(2)
        if hasattr(env_tab, "envelope_done") and hasattr(eff_tab, "on_envelope"):
            env_tab.envelope_done.connect(eff_tab.on_envelope)
            if env_tab.envelope is not None:
                eff_tab.on_envelope(env_tab.envelope)
        self.refresh_status()

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
