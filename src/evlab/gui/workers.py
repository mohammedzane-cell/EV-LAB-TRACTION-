"""Run a core function off the GUI thread (QThreadPool) and report back with signals."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, Signal

# Workers still running. A tab may drop its reference when it starts a new
# computation; without this set the Python-side signals object could be
# garbage-collected while the pool thread still emits from it.
_RUNNING: set["CoreWorker"] = set()


class WorkerSignals(QObject):
    """Signals of a CoreWorker; created on the GUI thread, emitted from the worker thread."""

    progress = Signal(str)  # stage key sent by the core function
    finished = Signal(object)  # result
    failed = Signal(str)  # message of the ValueError raised by the core


class CoreWorker(QRunnable):
    """Calls fn(*args, progress=signals.progress.emit, **kwargs) in a pool thread.

    The core only raises ValueError for bad inputs; anything else is a bug and
    is reported too, so the GUI never stays busy forever.
    """

    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.signals = WorkerSignals()
        _RUNNING.add(self)

    def run(self) -> None:
        try:
            try:
                result = self.fn(*self.args, progress=self.signals.progress.emit, **self.kwargs)
            except ValueError as exc:
                self.signals.failed.emit(str(exc))
            except Exception as exc:  # noqa: BLE001 - report, never hang the GUI
                self.signals.failed.emit(f"erreur interne ({type(exc).__name__}) : {exc}")
            else:
                self.signals.finished.emit(result)
        finally:
            _RUNNING.discard(self)


_GUI_GC = None  # pyqtgraph GarbageCollector, one per process


def collect_garbage_in_gui_thread() -> None:
    """Python's cyclic garbage collection only in the GUI thread, on a 1 s timer (started once).

    Left automatic, the collector runs in whichever thread allocates when its threshold is reached,
    e.g. a CoreWorker building the PDF report, and may then finalise Qt objects of the GUI thread there:
    PySide aborts with a segmentation fault. pyqtgraph's GarbageCollector disables the automatic
    collection and collects from a QTimer of the GUI thread instead. Memory is reclaimed at most
    1 s later; no computation changes. The optimisation's worker processes are spawned (fresh
    interpreters, automatic collection).
    """
    global _GUI_GC
    if _GUI_GC is None:
        from pyqtgraph.util.garbage_collector import GarbageCollector

        _GUI_GC = GarbageCollector(interval=1.0, debug=False)
