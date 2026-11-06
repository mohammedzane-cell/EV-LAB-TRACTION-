"""Shared placeholder widget for tabs that are not implemented yet."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from evlab.core.session import Session


class PlaceholderTab(QWidget):
    """Empty tab showing its title and "Module à venir"."""

    def __init__(self, session: Session, title: str) -> None:
        super().__init__()
        self.session = session
        self.title = title
        label = QLabel(f"{title}\n\nModule à venir")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(self)
        layout.addWidget(label)
