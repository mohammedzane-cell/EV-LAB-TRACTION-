"""Run Qt headless in tests (no display needed)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
