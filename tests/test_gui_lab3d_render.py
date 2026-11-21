"""Tab 9 really renders in 3D and responds to the mouse (tools/lab3d_render_check.py under a virtual X server).

The other GUI tests run on Qt's « offscreen » platform, which has no 3D API (Qt Quick 3D draws nothing there).
This test starts the check in a subprocess on Xvfb with Mesa OpenGL; it is skipped where xvfb-run is missing
(Windows, macOS: run the tool directly on the desktop)."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[1] / "tools" / "lab3d_render_check.py"


@pytest.mark.skipif(shutil.which("xvfb-run") is None, reason="xvfb-run not available")
def test_lab3d_renders_picks_and_animates(tmp_path):
    env = {**os.environ, "QT_QPA_PLATFORM": "xcb", "QSG_RHI_BACKEND": "opengl"}
    cmd = ["xvfb-run", "-a", "-s", "-screen 0 1280x1024x24", sys.executable, str(TOOL), "--out", str(tmp_path)]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=600)
    start = proc.stdout.find("{")
    assert start >= 0, proc.stdout + proc.stderr
    rep = json.loads(proc.stdout[start:])
    if not rep["render_ok"]:
        pytest.skip(f"no 3D graphics API on this X server ({rep['platform']})")
    assert rep["checks"] == {k: True for k in rep["checks"]}, rep
    assert proc.returncode == 0
    assert (tmp_path / "1_moteur_coupe.png").exists() and (tmp_path / "6_chaine_de_traction.png").exists()
