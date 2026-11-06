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
                tab.status_message.connect(self.statusBar().showMessage)
            if hasattr(tab, "busy"):
                tab.busy.connect(self.busy_bar.setVisible)
            if hasattr(tab, "motor_published"):
                tab.motor_published.connect(lambda _m: self.refresh_status(keep_message=True))
        self.setCentralWidget(self.tabs)
        self.refresh_status()

    def refresh_status(self, keep_message: bool = False) -> None:
        """Show which motor the whole chain is using (window title and status bar)."""
        m = self.session.motor
        demo = " (démo)" if m.is_demo else ""
        self.motor_text = f"Moteur : {m.source}{demo}"
        self.setToolTip(self.motor_text)
        if not keep_message:
            self.statusBar().showMessage(self.motor_text)
