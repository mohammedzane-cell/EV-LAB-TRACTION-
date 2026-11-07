"""Guards the strict architecture: core/ never imports Qt, does no I/O, never prints."""

import ast
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "src" / "evlab" / "core"
FORBIDDEN_MODULES = ("PySide6", "PyQt5", "PyQt6", "pyqtgraph", "matplotlib", "evlab.gui", "evlab.io")
FORBIDDEN_CALLS = {"print", "open", "input"}


def _core_files():
    files = sorted(CORE.glob("*.py"))
    assert files, "core/ has no modules"
    return files


def test_core_has_no_gui_or_io_imports():
    for path in _core_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                assert not name.startswith(FORBIDDEN_MODULES), f"{path.name} imports {name}"


def test_core_does_not_print_or_open_files():
    for path in _core_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in FORBIDDEN_CALLS, f"{path.name} calls {node.func.id}()"
