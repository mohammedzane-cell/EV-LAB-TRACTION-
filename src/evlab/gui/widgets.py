"""Small shared widgets: French spin boxes, cards, KPI tiles, chips. Presentation only.

Their look comes from gui/style.qss (object names #card, #cardTitle, #kpi, #kpiLabel,
#kpiValue and the chip / role properties), applied by gui/theme.py.
"""

from __future__ import annotations

from PySide6.QtCore import QLocale, Qt
from PySide6.QtWidgets import QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout

FRENCH = QLocale(QLocale.Language.French, QLocale.Country.France)


def french_spin(lo: float, hi: float, decimals: int, suffix: str, value: float) -> QDoubleSpinBox:
    """QDoubleSpinBox with a decimal comma, right-aligned, with a unit suffix."""
    s = QDoubleSpinBox()
    s.setLocale(FRENCH)
    s.setRange(lo, hi)
    s.setDecimals(decimals)
    s.setSuffix(f" {suffix}")
    s.setValue(value)
    s.setAlignment(Qt.AlignmentFlag.AlignRight)
    return s


def card(title: str) -> tuple[QFrame, QVBoxLayout, QHBoxLayout]:
    """Rounded card with a bold title (style.qss #card); returns (card, body layout, header layout)."""
    frame = QFrame()
    frame.setObjectName("card")
    lay = QVBoxLayout(frame)
    head = QHBoxLayout()
    label = QLabel(title)
    label.setObjectName("cardTitle")
    head.addWidget(label)
    head.addStretch(1)
    lay.addLayout(head)
    return frame, lay, head


def set_demo_chip(lbl: QLabel, labels: list[str]) -> None:
    """Show a démo chip when any input is démo; its tooltip lists them (labels from io.notes.demo_labels)."""
    lbl.setVisible(bool(labels))
    lbl.setToolTip("Valeurs démo : " + " ; ".join(labels) if labels else "")


def chip(text: str, kind: str = "demo") -> QLabel:
    """Rounded label: "demo" (amber, e.g. "points synthétiques (démo)") or "alert" (red)."""
    if kind not in ("demo", "alert"):
        raise ValueError(f"chip kind must be 'demo' or 'alert', got {kind!r}")
    lbl = QLabel(text)
    lbl.setProperty("chip", kind)
    return lbl


def muted(lbl: QLabel) -> QLabel:
    """Secondary text in the muted colour of the theme."""
    lbl.setProperty("role", "muted")
    return lbl


class KpiTile(QFrame):
    """Title + large value + unit."""

    def __init__(self, title: str, unit: str) -> None:
        super().__init__()
        self.setObjectName("kpi")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(2)
        self.title = QLabel(title)
        self.title.setObjectName("kpiLabel")
        self.value = QLabel("—")
        self.value.setObjectName("kpiValue")
        self.unit = unit
        lay.addWidget(self.title)
        lay.addWidget(self.value)

    def set_value(self, text: str) -> None:
        self.value.setText(f"{text} {self.unit}" if text != "—" else "—")
