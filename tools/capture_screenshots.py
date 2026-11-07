"""Redo the docs/images/ screenshots by driving the real app along docs/demo_script.md.

Usage (from the repository root, app installed with `pip install -e .[dev]`):

    python tools/capture_screenshots.py                 # writes docs/images/*.png
    python tools/capture_screenshots.py --out /tmp/x --numbers numbers.json
    python tools/capture_screenshots.py --theme dark --out /tmp/sombre

Clicks the demo path (tab 1 démo data → "Comparer les deux" → Identifier, then tabs 2 to 7,
the FEM window on its saved 7,07 A run, the quick Pareto run 3 points × 300 evaluations on
4 processes, "Charger ce design dans tous les onglets"), grabs each view at 1280 × 800 and
prints, as JSON, every number the demo script quotes, read from the widgets themselves.
Runs headless (QT_QPA_PLATFORM=offscreen) unless a display platform is already set.
Not part of the application: a documentation tool. The __main__ guard is required, since
tab 7 starts worker processes that re-import this file.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIZE = (1280, 800)
FEM_RUN = "7,07 A"  # saved FEM run shown in 06b_fem.png (magnetising current of TD5 Ex 1)


def _table(t) -> list[list[str]]:
    return [[t.item(r, c).text() if t.item(r, c) else "" for c in range(t.columnCount())]
            for r in range(t.rowCount())]


def capture(out: Path, theme_name: str = "light") -> dict:
    """Drive the app in the given theme, save the PNGs in `out`, return the displayed numbers."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication, QLabel

    from evlab.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    out.mkdir(parents=True, exist_ok=True)

    def pump(ms: int = 300) -> None:
        t = time.time()
        while (time.time() - t) * 1000 < ms:
            app.processEvents()
            time.sleep(0.01)

    def wait(signal, action=None, timeout: float = 600.0):
        """Run `action`, then wait for `signal`; return its arguments."""
        loop, box = QEventLoop(), {}

        def got(*args):
            box["args"] = args
            loop.quit()

        signal.connect(got)
        if action is not None:
            action()
        QTimer.singleShot(int(timeout * 1000), loop.quit)
        if "args" not in box:
            loop.exec()
        signal.disconnect(got)
        if "args" not in box:
            raise RuntimeError(f"timeout waiting for {signal}")
        pump(400)
        return box["args"]

    def shot(widget, name: str) -> None:
        pump(500)
        widget.grab().save(str(out / f"{name}.png"))

    nums: dict = {}
    w = MainWindow(theme_name=theme_name)  # never the remembered theme: captures are reproducible
    w.resize(*SIZE)
    w.show()
    pump(800)
    if w.tabs.widget(1).envelope is None:
        wait(w.tabs.widget(1).envelope_done, timeout=120)
    nums["status_start"] = w.statusBar().currentMessage()
    shot(w, "00_fenetre")

    # tab 1: démo bench data, both methods, Identifier
    t1 = w.tabs.widget(0)
    t1.load_demo()
    pump()
    t1.radios["both"].setChecked(True)
    res = wait(t1.identification_done, t1.identify)[0]
    m = w.session.motor
    nums["tab1_table"] = _table(t1.table)
    nums["tab1_motor"] = dict(source=m.source, r1=m.r1, r1_temperature_k=m.r1_temperature_k, p_mech=m.p_mech)
    nums["tab1_ci95_r2p"] = res.fit.ci95["r2p"] if res.fit else None
    shot(w, "01_identification")

    t2 = w.tabs.widget(1)
    w.tabs.setCurrentIndex(1)
    pump(1500)
    nums["tab2_tiles"] = {k: t.value.text() for k, t in t2.tiles.items()}
    nums["tab2_zones"] = t2.lbl_zones.text()
    nums["tab2_demo"] = t2.chip_demo.toolTip()
    shot(w, "02_enveloppe")

    t3 = w.tabs.widget(2)
    if t3.stale:
        wait(t3.map_done, lambda: w.tabs.setCurrentIndex(2))
    else:
        w.tabs.setCurrentIndex(2)
    nums["tab3_best"] = t3.lbl_best.text()
    shot(w, "03_rendement")

    t4 = w.tabs.widget(3)
    wait(t4.simulation_done, lambda: w.tabs.setCurrentIndex(3))
    nums["tab4_tiles"] = {k: t.value.text() for k, t in t4.tiles.items()}
    nums["tab4_labels"] = [t4.lbl_class.text(), t4.lbl_gear.text(), t4.lbl_cycle.text(), t4.lbl_warning.text()]
    shot(w, "04_vehicule")

    t5 = w.tabs.widget(4)
    wait(t5.thermal_done, lambda: w.tabs.setCurrentIndex(4))
    nums["tab5_tiles"] = {k: t.value.text() for k, t in t5.tiles.items()}
    nums["tab5_r1_zero_chip"] = t5.chip_r1.isVisibleTo(t5)
    shot(w, "05_thermique")

    t6 = w.tabs.widget(5)
    w.tabs.setCurrentIndex(5)
    pump(800)
    shot(w, "06_bobinage")
    dlg = t6.open_fem()
    dlg.resize(*SIZE)
    dlg.show()
    pump(800)
    runs = [i for i in range(dlg.combo_cache.count()) if FEM_RUN in dlg.combo_cache.itemText(i)]
    if runs:
        dlg.combo_cache.setCurrentIndex(runs[0])
        dlg.load_cached(dlg.combo_cache.currentData())
        pump(1500)
    nums["fem"] = [lbl.text() for lbl in dlg.findChildren(QLabel) if "Fondamental" in lbl.text()]
    shot(dlg, "06b_fem")
    dlg.close()

    # tab 7: quick Pareto run, minimum-consumption point of the front
    t7 = w.tabs.widget(6)
    w.tabs.setCurrentIndex(6)
    pump(500)
    t7.spin_points.setValue(3)
    t7.spin_budget.setValue(300)
    t7.spin_workers.setValue(4)
    t0 = time.time()
    pareto = wait(t7.pareto_done, t7.run, timeout=1200)[0]
    nums["tab7_seconds"] = round(time.time() - t0, 1)
    t7.select(min(pareto.front, key=lambda e: e.wh_per_km))
    pump(500)
    nums["tab7_kpi"] = _table(t7.kpi_table)
    nums["tab7_variables"] = _table(t7.var_table)
    shot(w, "07_optimisation")

    # load that design everywhere: tab 2 shows its envelope and the E/f warning
    wait(t2.envelope_done, t7._load_selected, timeout=300)
    w.tabs.setCurrentIndex(1)
    nums["design_tab2_tiles"] = {k: t.value.text() for k, t in t2.tiles.items()}
    nums["design_tab2_flux"] = t2.lbl_flux.text()
    shot(w, "02b_enveloppe_design")
    w.close()
    return nums


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "images", help="folder for the PNGs")
    ap.add_argument("--numbers", type=Path, help="also write the displayed numbers to this JSON file")
    ap.add_argument("--theme", choices=("light", "dark"), default="light", help="UI theme (default light)")
    args = ap.parse_args()
    nums = capture(args.out, args.theme)
    text = json.dumps(nums, ensure_ascii=False, indent=1, default=str)
    if args.numbers:
        args.numbers.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
