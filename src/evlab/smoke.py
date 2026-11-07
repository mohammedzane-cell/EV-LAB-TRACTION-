"""Start-up self-test of an installed or frozen build: `EVLab --smoke [out_dir]` (no window interaction).

Checks, in order: the seven tabs exist; the demo files are found in data/ (tab 1); the
envelope (scipy) and the cycle (tab 4) are computed in worker threads; a two-process
optimisation (spawn pool: needs multiprocessing.freeze_support in a frozen build); the
PDF (reportlab + matplotlib fonts) and Excel exports. Prints one line per check; exit
code 0 when all pass. The same lines go to <out_dir>/smoke.log (a windowed build has no console).
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path


def _wait(app, condition, timeout: float) -> bool:
    t0 = time.monotonic()
    while not condition():
        if time.monotonic() - t0 > timeout:
            return False
        app.processEvents()
        time.sleep(0.02)
    return True


def run(out_dir: str | None = None) -> int:
    from PySide6.QtWidgets import QApplication

    from evlab.core import optimise as op
    from evlab.gui.main_window import MainWindow
    from evlab.io.paths import data_dir

    app = QApplication.instance() or QApplication(sys.argv)
    out = Path(out_dir or tempfile.mkdtemp(prefix="evlab_smoke_"))
    out.mkdir(parents=True, exist_ok=True)
    checks: list[tuple[str, bool, str]] = []

    log = (out / "smoke.log").open("w", encoding="utf-8")

    def say(line: str) -> None:
        log.write(line + "\n")
        log.flush()
        if sys.stdout is not None:  # None in a windowed (no console) Windows build
            print(line, flush=True)

    def check(name: str, ok: bool, detail: str = "") -> bool:
        checks.append((name, ok, detail))
        say(f"{'ok  ' if ok else 'FAIL'} {name}{' — ' + detail if detail else ''}")
        return ok

    w = MainWindow()
    w.show()
    check("7 onglets", w.tabs.count() == 7, ", ".join(w.tabs.tabText(i) for i in range(w.tabs.count())))
    check("dossier data", (data_dir() / "bench_tests_demo.csv").exists(), str(data_dir()))
    from evlab.io import femm_model as fm

    check("calculs FEM pré-calculés (onglet 6)", len(fm.cached_runs()) > 0, f"{len(fm.cached_runs())} calcul(s)")
    t1 = w.tabs.widget(0)
    t1.load_demo()
    check("fichiers démo (onglet 1)", t1.bench is not None and t1.points_file is not None)
    check("enveloppe (onglet 2)", _wait(app, lambda: w.tabs.widget(1).envelope is not None, 120))
    w.tabs.setCurrentIndex(3)
    t4 = w.tabs.widget(3)
    if check("cycle (onglet 4)", _wait(app, lambda: getattr(t4, "result", None) is not None, 180)):
        try:
            res = op.optimise(w.optimisation_problem(), op.Bounds(gear_ratio=(3.0, 4.0)), seed=0, popsize=5,
                              budget=10, workers=2)
            check("optimisation, 2 processus", len(res.log) == 10 and res.best.feasible,
                  f"{len(res.log)} évaluations")
        except Exception as exc:  # report any failure of the frozen process pool
            check("optimisation, 2 processus", False, repr(exc))
    for kind in ("pdf", "xlsx"):
        done: list = []
        w.export_done.connect(done.append)
        w.export_failed.connect(lambda m, d=done: d.append(None))
        path = out / f"smoke.{kind}"
        w.export(kind, path, "Test de démarrage")
        ok = _wait(app, lambda: bool(done), 120) and done[0] is not None and path.stat().st_size > 0
        check(f"export {kind.upper()}", ok, str(path))
    w.close()
    failed = [c for c in checks if not c[1]]
    say(f"{len(checks) - len(failed)}/{len(checks)} vérifications réussies")
    log.close()
    return 1 if failed else 0
