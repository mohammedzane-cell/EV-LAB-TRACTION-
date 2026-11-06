"""Smoke tests: every module imports, the main window opens with its 7 tabs."""

import importlib

import pytest

CORE = ["session", "circuit", "identification", "drive", "losses",
        "vehicle", "thermal", "winding", "optimise"]
IO = ["loaders", "report_pdf", "export_excel"]
GUI = ["main_window", "tab_identification", "tab_envelope", "tab_efficiency",
       "tab_vehicle", "tab_thermal", "tab_winding", "tab_optimisation"]

TAB_TITLES = [
    "1 · Identification",
    "2 · Enveloppe",
    "3 · Rendement",
    "4 · Véhicule & WLTC",
    "5 · Thermique",
    "6 · Bobinage",
    "7 · Optimisation",
]


@pytest.mark.parametrize("name", CORE)
def test_import_core(name):
    mod = importlib.import_module(f"evlab.core.{name}")
    assert mod.__doc__, f"evlab.core.{name} has no docstring"


@pytest.mark.parametrize("name", IO)
def test_import_io(name):
    assert importlib.import_module(f"evlab.io.{name}").__doc__


@pytest.mark.parametrize("name", GUI)
def test_import_gui(name):
    assert importlib.import_module(f"evlab.gui.{name}").__doc__


def test_main_window_opens_with_seven_tabs(qtbot):
    from evlab.gui.main_window import MainWindow

    win = MainWindow()
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    assert win.windowTitle() == "EV-Traction Lab"
    assert win.tabs.count() == 7
    # Qt stores '&&' for a literal '&' (a single '&' would be hidden as a shortcut marker)
    labels = [win.tabs.tabText(i) for i in range(win.tabs.count())]
    assert labels[3] == "4 · Véhicule && WLTC"
    assert [lab.replace("&&", "&") for lab in labels] == TAB_TITLES
    assert [win.tabs.widget(i).title for i in range(7)] == TAB_TITLES
    assert win.statusBar().currentMessage() == "Moteur : TD5 Ex 1"


def test_status_bar_flags_demo_motor(qtbot):
    from dataclasses import replace

    from evlab.core.session import Session, td5_ex1
    from evlab.gui.main_window import MainWindow

    win = MainWindow(Session(replace(td5_ex1(), source="TP3", is_demo=True)))
    qtbot.addWidget(win)
    assert win.statusBar().currentMessage() == "Moteur : TP3 (démo)"


def test_entry_point_exists():
    from evlab.__main__ import main

    assert callable(main)
