"""Where the input files live: data/ next to the source tree, or next to the frozen executable."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def app_root() -> Path:
    """Repository root when run from source; folder of EVLab.exe in a PyInstaller build."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def data_dir() -> Path:
    """data/ (demo CSV files, WLTC files dropped in by the user, FEM cache); EVLAB_DATA overrides it."""
    override = os.environ.get("EVLAB_DATA")
    return Path(override).expanduser().resolve() if override else app_root() / "data"
