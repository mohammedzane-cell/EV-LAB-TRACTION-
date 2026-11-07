"""Fichier → Exporter PDF / Excel (pytest-qt, offscreen)."""

import re

import pytest
from openpyxl import load_workbook
from PySide6.QtWidgets import QFileDialog, QInputDialog

from evlab.gui.main_window import MainWindow

TIMEOUT = 120_000


@pytest.fixture
def win(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitUntil(lambda: w.tabs.widget(1).envelope is not None, timeout=TIMEOUT)
    t4 = w.tabs.widget(3)
    with qtbot.waitSignal(t4.simulation_done, timeout=TIMEOUT):
        w.tabs.setCurrentIndex(3)
    return w


def test_menu(win):
    menu = win.menuBar().actions()[0]
    assert menu.text() == "Fichier"
    texts = [a.text() for a in menu.menu().actions() if a.text()]
    assert texts == ["Exporter PDF…", "Exporter Excel…", "Quitter"]
    assert win.tabs.widget(0).btn_pdf.isEnabled()


def test_export_pdf_and_excel(qtbot, win, tmp_path):
    pdf = tmp_path / "r.pdf"
    with qtbot.waitSignal(win.export_done, timeout=TIMEOUT) as b:
        assert win.export("pdf", pdf, "Groupe GUI")
    assert b.args[0] == pdf and pdf.exists()
    assert 1 <= len(re.findall(rb"/Type\s*/Page(?![s\w])", pdf.read_bytes())) <= 3
    xl = tmp_path / "r.xlsx"
    with qtbot.waitSignal(win.export_done, timeout=TIMEOUT):
        win.export("xlsx", xl, "Groupe GUI")
    wb = load_workbook(xl, read_only=True)
    _, res, _, _, _ = win.tabs.widget(3).result
    kpi = {r[0]: r[1] for r in list(wb["Cycle_KPI"].iter_rows(values_only=True))[1:]}
    assert kpi["consommation"] == pytest.approx(res.summary.wh_per_km, rel=1e-15)
    assert "Exporté" in win.statusBar().currentMessage()


def test_dialogs_from_the_tab1_button(qtbot, win, tmp_path, monkeypatch):
    target = tmp_path / "via_bouton.pdf"
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Groupe 7", True)))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), "")))
    with qtbot.waitSignal(win.export_done, timeout=TIMEOUT):
        win.tabs.widget(0).btn_pdf.click()
    assert target.exists() and win.group == "Groupe 7"


def test_cancelled_dialog_writes_nothing(win, tmp_path, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("x", False)))
    win.act_excel.trigger()
    assert not list(tmp_path.iterdir())
