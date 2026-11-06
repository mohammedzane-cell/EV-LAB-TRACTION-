"""io.cycles: CSV drive cycles, validation, 1 s resampling; official WLTC files when present."""

from pathlib import Path

import numpy as np
import pytest

from evlab.core.vehicle import cycle_stats
from evlab.io.cycles import load_cycle
from evlab.io.loaders import LoaderError

DATA = Path(__file__).resolve().parents[1] / "data"
KMH = 1 / 3.6


def _write(tmp_path, text, name="cycle.csv"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_demo_cycle():
    c = load_cycle(DATA / "cycle_demo.csv")
    assert c.is_demo and "démo" in c.name
    st = cycle_stats(c)
    assert np.all(np.diff(c.t) == 1.0) and c.t[0] == 0.0
    assert c.v[0] == 0.0 and c.v[-1] == 0.0
    assert 300 < st.duration < 1200 and st.v_max <= 60 * KMH + 1e-9


def test_resampling_to_one_second(tmp_path):
    p = _write(tmp_path, "t [s],v [km/h]\n0,0\n2.5,9\n5,18\n7,0\n")
    c = load_cycle(p)
    assert np.array_equal(c.t, np.arange(0.0, 8.0))
    assert c.v[1] == pytest.approx(3.6 * KMH)  # linear: 9 km/h · 1/2.5
    assert c.v[5] == pytest.approx(18 * KMH)
    assert c.v[7] == 0.0
    assert not c.is_demo


@pytest.mark.parametrize("text, msg", [
    ("", "fichier vide"),
    ("t [s],v [m/s]\n0,0\n1,1\n", "unité incorrecte pour la colonne « v »"),
    ("t [s]\n0\n1\n", "colonne(s) manquante(s) : « v »"),
    ("t [s],v [km/h]\n0,0\n1,5\n1,6\n", "le temps doit être strictement croissant"),
    ("t [s],v [km/h]\n0,0\n2,5\n1,6\n", "le temps doit être strictement croissant"),
    ("t [s],v [km/h]\n0,0\n1,-5\n", "vitesse négative"),
    ("t [s],v [km/h]\n0,0\n", "au moins 2 points"),
    ("t [s],v [km/h]\n0,0\n1,abc\n", "n'est pas un nombre"),
])
def test_cycle_errors_in_french(tmp_path, text, msg):
    with pytest.raises(LoaderError) as exc:
        load_cycle(_write(tmp_path, text))
    assert msg in str(exc.value)


# --- official WLTC files (provided by the user; never invented or downloaded) -------

WLTC1 = DATA / "wltc_class1.csv"
WLTC3 = DATA / "wltc_class3.csv"


@pytest.mark.skipif(not WLTC3.exists(), reason="data/wltc_class3.csv not provided yet")
def test_wltc_class3_totals():
    st = cycle_stats(load_cycle(WLTC3))
    assert st.duration == pytest.approx(1800.0)
    assert st.distance == pytest.approx(23_270.0, rel=0.005)
    assert st.v_max == pytest.approx(131.3 * KMH, abs=0.05 * KMH)


@pytest.mark.skipif(not WLTC1.exists(), reason="data/wltc_class1.csv not provided yet")
def test_wltc_class1_totals():
    """Low + Medium = first 1022 s (CLAUDE.md); a trailing second Low phase must repeat the first one."""
    c = load_cycle(WLTC1)
    lm = c.t <= 1022.0
    st = cycle_stats(type(c)(t=c.t[lm], v=c.v[lm], name=c.name, is_demo=c.is_demo))
    assert st.duration == pytest.approx(1022.0)
    assert st.distance == pytest.approx(8_091.0, rel=0.005)
    assert st.v_max == pytest.approx(64.4 * KMH, abs=0.05 * KMH)
    if c.t[-1] > 1022.0:
        low = c.v[c.t <= 589.0]  # Low phase: 0–589 s
        tail = c.v[c.t >= 1022.0]
        n = min(len(low), len(tail))
        assert np.allclose(tail[:n], low[:n], atol=0.05 * KMH), "the extra phase is not a repeat of Low"
