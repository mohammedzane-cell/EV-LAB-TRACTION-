"""Entry point: `python -m evlab` (or the `evlab` command) starts the GUI."""

from __future__ import annotations

import sys


def main() -> int:
    """Start the Qt application and show the main window."""
    from PySide6.QtWidgets import QApplication

    from evlab.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
