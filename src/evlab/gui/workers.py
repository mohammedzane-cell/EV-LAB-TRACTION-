"""Run a core function off the GUI thread (QThreadPool) and report back with signals."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, Signal


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

    def run(self) -> None:
        try:
            result = self.fn(*self.args, progress=self.signals.progress.emit, **self.kwargs)
        except ValueError as exc:
            self.signals.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - report, never hang the GUI
            self.signals.failed.emit(f"erreur interne ({type(exc).__name__}) : {exc}")
        else:
            self.signals.finished.emit(result)
