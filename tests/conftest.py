"""Run Qt headless in tests (no display needed); never read or write the user's real settings."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path):
    """QSettings (the remembered theme) go to a fresh folder for every test."""
    from PySide6.QtCore import QSettings

    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    yield
