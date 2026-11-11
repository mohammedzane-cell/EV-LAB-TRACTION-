"""io.paths: data/ from the source tree, next to a frozen executable, or from EVLAB_DATA."""

import sys
from pathlib import Path

from evlab import __main__ as entry
from evlab.io import paths

ROOT = Path(__file__).resolve().parents[1]


def test_source_tree(monkeypatch):
    monkeypatch.delenv("EVLAB_DATA", raising=False)
    assert paths.app_root() == ROOT and paths.data_dir() == ROOT / "data"
    assert (paths.data_dir() / "bench_tests_demo.csv").exists()


def test_frozen_build(monkeypatch, tmp_path):
    monkeypatch.delenv("EVLAB_DATA", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "EVLab" / "EVLab.exe"))
    assert paths.data_dir() == (tmp_path / "EVLab" / "data").resolve()


def test_override(monkeypatch, tmp_path):
    monkeypatch.setenv("EVLAB_DATA", str(tmp_path))
    assert paths.data_dir() == tmp_path.resolve()


def test_smoke_flag_runs_the_self_test(monkeypatch):
    from evlab import smoke

    seen = []
    monkeypatch.setattr(smoke, "run", lambda out=None: seen.append(out) or 0)
    assert entry.main(["--smoke", "dossier"]) == 0 and seen == ["dossier"]
