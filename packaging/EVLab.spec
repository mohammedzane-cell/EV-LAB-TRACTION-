# PyInstaller spec: one-folder build of EV-Traction Lab.
#
#   pyinstaller --noconfirm packaging/EVLab.spec        (from the repository root)
#
# Output: dist/EVLab/EVLab(.exe), dist/EVLab/_internal/ (Python, Qt, numpy, scipy …) and
# dist/EVLab/data/ (demo CSV files, FEM cache; drop the official WLTC files here).
# PyInstaller does not cross-compile: run it on Windows for the Windows build
# (packaging/build_windows.bat). Self-test of the result: EVLab --smoke [dossier].
import shutil
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
WINDOWS = sys.platform == "win32"

a = Analysis(
    [str(ROOT / "packaging" / "evlab_launcher.py")],
    pathex=[str(ROOT / "src")],
    datas=[(str(ROOT / "src" / "evlab" / "gui" / "style.qss"), "evlab/gui"),  # UI theme (gui/theme.py)
           (str(ROOT / "src" / "evlab" / "gui" / "icons"), "evlab/gui/icons"),
           (str(ROOT / "src" / "evlab" / "docs" / "cours"), "evlab/docs/cours")],  # course pages (tab 8)
    # course pages are read with importlib.resources from the package evlab.docs.cours
    hiddenimports=["evlab.smoke", "evlab.docs", "evlab.docs.cours"],
    excludes=["tkinter", "PyQt5", "PyQt6", "PySide2", "IPython", "pytest", "pytestqt", "femm", "pymoo",
              # QTextBrowser shows the course: the web engine (and its ~200 MB) is never used
              "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
              "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.QtWebView"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EVLab",
    console=not WINDOWS,  # windowed on Windows (EVLab --smoke writes smoke.log instead of printing)
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="EVLab", upx=False)

# data/ next to the executable (evlab.io.paths.data_dir): visible and writable by the user
dist = Path(DISTPATH) / "EVLab"
shutil.copytree(ROOT / "data", dist / "data", dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("__pycache__"))
for doc in ("README.md", "docs/user_guide.md", "docs/demo_script.md"):
    if (ROOT / doc).exists():
        shutil.copy2(ROOT / doc, dist / Path(doc).name)
