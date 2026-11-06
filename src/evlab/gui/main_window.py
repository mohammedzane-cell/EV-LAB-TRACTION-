"""Main window: seven tabs sharing one Session (one motor, one chain) and a status bar."""

from __future__ import annotations

from PySide6.QtWidgets import QMainWindow, QTabWidget

from evlab.core.session import Session
from evlab.gui.tab_efficiency import EfficiencyTab
from evlab.gui.tab_envelope import EnvelopeTab
from evlab.gui.tab_identification import IdentificationTab
from evlab.gui.tab_optimisation import OptimisationTab
from evlab.gui.tab_thermal import ThermalTab
from evlab.gui.tab_vehicle import VehicleTab
from evlab.gui.tab_winding import WindingTab

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
        self.setWindowTitle("EV-Traction Lab")
        self.resize(1200, 800)

        self.tabs = QTabWidget()
        for cls in TAB_CLASSES:
            tab = cls(self.session)
            self.tabs.addTab(tab, tab_label(tab.title))
        self.setCentralWidget(self.tabs)
        self.refresh_status()

    def refresh_status(self) -> None:
        """Show which motor the whole chain is using."""
        m = self.session.motor
        demo = " (démo)" if m.is_demo else ""
        self.statusBar().showMessage(f"Moteur : {m.source}{demo}")
