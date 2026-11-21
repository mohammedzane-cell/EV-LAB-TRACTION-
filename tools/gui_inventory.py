"""Inventory of every control, plot and menu entry of the app, for the UI-redesign preservation check.

Usage (from the repository root):

    python tools/gui_inventory.py out.json            # inventory after the demo path
    python tools/gui_inventory.py --diff before.json after.json

The inventory walks each tab's own attributes (the names the main window and the tests use:
spin_v, btn_compute, plot_torque …) and records, for each widget: its type, its text, its value,
range, decimals and unit (spin boxes), its items (combo boxes), its checked and enabled state,
the title, axis labels and curve names of a plot, the headers of a table. Then every menu action.
The demo path is the one of docs/demo_script.md up to tab 5 (démo files, « Comparer les deux »,
Identifier, cycle, thermal), so the values read are those a user sees.
`--diff` prints what disappeared, what appeared and what changed between two inventories.
Not part of the application: a documentation tool (headless, QT_QPA_PLATFORM=offscreen).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path


def _plot(pw) -> dict:
    item = pw.getPlotItem()
    axes = {}
    for name in ("left", "bottom"):
        ax = item.getAxis(name)
        axes[name] = ax.labelText + (f" ({ax.labelUnits})" if ax.labelUnits else "")
    curves = sorted(str(c.name()) for c in item.listDataItems() if c.name())
    return {"title": item.titleLabel.text, "axes": axes, "curves": curves}


def _widget(w) -> dict | None:
    import pyqtgraph as pg
    from PySide6.QtWidgets import (QAbstractButton, QAbstractSpinBox, QComboBox, QGroupBox, QLabel, QLineEdit,
                                   QSlider, QTableWidget, QTextBrowser, QTreeWidget)

    d: dict = {"type": type(w).__name__, "enabled": w.isEnabled(), "tooltip": w.toolTip()}
    if isinstance(w, pg.PlotWidget):
        d.update(_plot(w))
    elif isinstance(w, QAbstractSpinBox):
        d.update(value=w.value(), min=w.minimum(), max=w.maximum(), suffix=w.suffix(),
                 decimals=getattr(w, "decimals", lambda: 0)())
    elif isinstance(w, QComboBox):
        d.update(items=[w.itemText(k) for k in range(w.count())], current=w.currentText())
    elif isinstance(w, QAbstractButton):
        d.update(text=w.text(), checkable=w.isCheckable(), checked=w.isChecked())
    elif isinstance(w, QGroupBox):
        d.update(text=w.title())
    elif isinstance(w, QTableWidget):
        heads = [w.horizontalHeaderItem(k).text() if w.horizontalHeaderItem(k) else "" for k in range(w.columnCount())]
        d.update(columns=heads, rows=w.rowCount())
    elif isinstance(w, QSlider):
        d.update(value=w.value(), min=w.minimum(), max=w.maximum())
    elif isinstance(w, QLineEdit):
        d.update(text=w.text())
    elif isinstance(w, QLabel):
        d.update(text=w.text())
    elif isinstance(w, (QTextBrowser, QTreeWidget)):
        pass
    else:
        return d if type(w).__name__ in ("KpiTile", "FigureCanvasQTAgg") else None
    if type(w).__name__ == "KpiTile":
        d.update(text=w.title.text(), value=w.value.text())
    return d


def _tab(tab) -> dict:
    from PySide6.QtWidgets import QWidget

    out = {}
    for name, val in sorted(vars(tab).items()):
        if isinstance(val, QWidget):
            d = _widget(val)
            if d is not None:
                out[name] = d
        elif isinstance(val, dict) and val:
            for k, v in val.items():  # radios, tiles … kept in dicts; bound spin boxes in (lo, hi, scale) tuples
                parts = [v] if isinstance(v, QWidget) else [x for x in (v if isinstance(v, tuple) else ()) if isinstance(x, QWidget)]
                for j, x in enumerate(parts):
                    d = _widget(x)
                    if d is not None:
                        out[f"{name}[{k}]" + (f"[{j}]" if len(parts) > 1 else "")] = d
    return out


def inventory() -> dict:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QEventLoop, QSettings, QTimer
    from PySide6.QtWidgets import QApplication

    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tempfile.mkdtemp(prefix="evlab_inv_"))
    from evlab.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)

    def wait(signal, action, timeout=300.0):
        loop, box = QEventLoop(), {}
        signal.connect(lambda *a: (box.setdefault("a", a), loop.quit()))
        action()
        QTimer.singleShot(int(timeout * 1000), loop.quit)
        if "a" not in box:
            loop.exec()
        t = time.time()
        while time.time() - t < 0.3:
            app.processEvents()

    w = MainWindow(theme_name="light")
    w.resize(1280, 800)
    w.show()
    if w.tabs.widget(1).envelope is None:
        wait(w.tabs.widget(1).envelope_done, lambda: None, 120)
    t1 = w.tabs.widget(0)
    t1.load_demo()
    t1.radios["both"].setChecked(True)
    wait(t1.identification_done, t1.identify)
    wait(w.tabs.widget(3).simulation_done, lambda: w.tabs.setCurrentIndex(3))
    wait(w.tabs.widget(4).thermal_done, lambda: w.tabs.setCurrentIndex(4))
    for k in range(w.tabs.count()):
        w.tabs.setCurrentIndex(k)
        app.processEvents()
    inv = {"tabs": {w.tabs.widget(k).title: _tab(w.tabs.widget(k)) for k in range(w.tabs.count())},
           "menus": {m.text(): [a.text() + (f" [{a.shortcut().toString()}]" if not a.shortcut().isEmpty() else "")
                                for a in m.menu().actions() if a.text()]
                     for m in w.menuBar().actions() if m.menu()},
           "help_buttons": [b.toolTip() for b in getattr(w, "help_buttons", [])]}
    from PySide6.QtCore import QThreadPool

    QThreadPool.globalInstance().waitForDone(60_000)  # no worker may report to a deleted tab
    app.processEvents()
    w.close()
    return inv


def diff(a: dict, b: dict) -> list[str]:
    """Human-readable differences between two inventories (a = before, b = after)."""
    out = []
    for tab in sorted(set(a["tabs"]) | set(b["tabs"])):
        ta, tb = a["tabs"].get(tab, {}), b["tabs"].get(tab, {})
        for name in sorted(set(ta) - set(tb)):
            out.append(f"{tab} · DISPARU  {name}: {ta[name]}")
        for name in sorted(set(tb) - set(ta)):
            out.append(f"{tab} · AJOUTÉ   {name}: {tb[name]}")
        for name in sorted(set(ta) & set(tb)):
            if ta[name] != tb[name]:
                keys = sorted(k for k in set(ta[name]) | set(tb[name]) if ta[name].get(k) != tb[name].get(k))
                out.append(f"{tab} · MODIFIÉ  {name}: " +
                           "; ".join(f"{k}: {ta[name].get(k)!r} → {tb[name].get(k)!r}" for k in keys))
    for key in ("menus", "help_buttons"):
        if a.get(key) != b.get(key):
            out.append(f"{key} · MODIFIÉ  {a.get(key)!r} → {b.get(key)!r}")
    return out


def main() -> None:
    if len(sys.argv) == 4 and sys.argv[1] == "--diff":
        a, b = (json.loads(Path(p).read_text(encoding="utf-8")) for p in sys.argv[2:])
        lines = diff(a, b)
        print("\n".join(lines) if lines else "aucune différence")
        return
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    inv = inventory()
    Path(sys.argv[1]).write_text(json.dumps(inv, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    n = sum(len(t) for t in inv["tabs"].values())
    print(f"{n} éléments dans {len(inv['tabs'])} onglets, {sum(len(v) for v in inv['menus'].values())} entrées de menu")


if __name__ == "__main__":
    main()
