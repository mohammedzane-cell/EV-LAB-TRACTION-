"""Small shared widgets: French spin boxes, cards, KPI tiles. Presentation only."""

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
    """White rounded card with a bold title; returns (card, body layout, header layout)."""
    frame = QFrame()
    frame.setObjectName("card")
    frame.setStyleSheet("#card { background: white; border: 1px solid #d9dce1; border-radius: 6px; }")
    lay = QVBoxLayout(frame)
    head = QHBoxLayout()
    label = QLabel(title)
    f = label.font()
    f.setBold(True)
    label.setFont(f)
    head.addWidget(label)
    head.addStretch(1)
    lay.addLayout(head)
    return frame, lay, head


def set_demo_chip(lbl: QLabel, labels: list[str]) -> None:
    """Show a démo chip when any input is démo; its tooltip lists them (labels from io.notes.demo_labels)."""
    lbl.setVisible(bool(labels))
    lbl.setToolTip("Valeurs démo : " + " ; ".join(labels) if labels else "")


def chip(text: str) -> QLabel:
    """Rounded label, e.g. "points synthétiques (démo)"."""
    lbl = QLabel(text)
    lbl.setStyleSheet("QLabel { border: 1px solid #c9ccd2; border-radius: 10px; padding: 2px 10px; color: #555; }")
    return lbl


class KpiTile(QFrame):
    """Title + large value + unit."""

    def __init__(self, title: str, unit: str) -> None:
        super().__init__()
        self.setObjectName("kpi")
        self.setStyleSheet("#kpi { background: white; border: 1px solid #d9dce1; border-radius: 6px; }")
        lay = QVBoxLayout(self)
        self.title = QLabel(title)
        self.title.setStyleSheet("color: #666;")
        self.value = QLabel("—")
        f = self.value.font()
        f.setPointSize(f.pointSize() + 7)
        f.setBold(True)
        self.value.setFont(f)
        self.unit = unit
        lay.addWidget(self.title)
        lay.addWidget(self.value)

    def set_value(self, text: str) -> None:
        self.value.setText(f"{text} {self.unit}" if text != "—" else "—")
