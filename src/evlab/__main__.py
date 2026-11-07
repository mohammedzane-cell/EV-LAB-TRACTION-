"""Entry point: `python -m evlab` (or the `evlab` command, or EVLab.exe) starts the GUI.

`--smoke [out_dir]` runs the start-up self-test instead (evlab.smoke) and exits.
"""

from __future__ import annotations

import multiprocessing
import sys


def main(argv: list[str] | None = None) -> int:
    """Start the Qt application and show the main window (or run the smoke test)."""
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "--smoke":
        from evlab import smoke

        return smoke.run(argv[1] if len(argv) > 1 else None)
    from PySide6.QtWidgets import QApplication

    from evlab.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    multiprocessing.freeze_support()  # tab 7's process pool re-launches the frozen executable
    sys.exit(main())
