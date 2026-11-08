"""data/tests/: synthetic test datasets (io.demo_data) — good files identify, bad files fail in French.

Criteria for the fit (2,5 % noise, 10 load points g = 0,01…0,08, as specified), chosen from a
300-seed Monte Carlo of the same chain (data/tests/README.md):
- Xm and R'2 within 5 % (95 % of seeds: within 4,1 % and 1,9 %);
- X: the reference inside the fit's 95 % confidence interval (X is weakly visible far below
  breakdown: 95 % of seeds within 8–24 %);
- Rf within ±16 % (one no-load point after subtracting copper loss and p_mec: 95th
  percentile 16,1–16,3 %). Noise-free files give every parameter back within 1 %.
"""

import re
import warnings
from pathlib import Path

import numpy as np
import pytest

from evlab.core import identification as ident
from evlab.core import vehicle
from evlab.io import demo_data
from evlab.io.cycles import load_cycle
from evlab.io.format import fr, fr_pct
from evlab.io.loaders import LoaderError, load_bench_tests, load_load_points, nameplate, reference_motor

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "data" / "tests"
MOTORS = tuple(demo_data.TEST_MOTOR_VALUES)
CYCLES = tuple(demo_data.TEST_CYCLES)
FIT_TOL = 5.0  # %, Xm and R'2
RF_BOUND = 16.0  # %, Rf (95th percentile of the no-load estimate at 2,5 % noise)
A_MAX = 1.2  # m/s²
ENGLISH = re.compile(r"\b(must|got|invalid|should|expected|error)\b", re.IGNORECASE)


def _identify(name: str):
    bench = load_bench_tests(TESTS / f"bench_tests_{name}.csv")
    points = load_load_points(TESTS / f"load_points_{name}.csv")
    plate = nameplate(bench.meta)
    rec = ident.TestRecords(dc=bench.dc, t_hot_k=bench.winding_temperature_k, no_load=bench.no_load,
                            locked=bench.locked, pole_pairs=plate.pole_pairs, v_rated=plate.v_phase,
                            f_rated=plate.f, p_mech=None)
    with warnings.catch_warnings():
        warnings.simplefilter("error", ident.IdentifiabilityWarning)  # none expected on these files
        res = ident.compare_methods(rec, "both", points=points.points, layout="tp3",
                                    reference=reference_motor(bench.meta), is_demo=True, source=name)
    return bench, points, res


def test_files_are_the_generator_output():
    expected = demo_data.dataset_texts()
    assert sorted(p.name for p in TESTS.glob("*.csv")) == sorted(expected)
    for name, text in expected.items():
        assert (TESTS / name).read_text(encoding="utf-8") == text, f"{name}: python -m evlab.io.demo_data --tests"


@pytest.mark.parametrize("name", MOTORS)
def test_motor_files_identify_within_the_bounds(name):
    bench, points, res = _identify(name)
    ref, _p_n = demo_data.dataset_motor(name)
    assert bench.is_demo and points.is_demo  # "# démo: …" header → labelled démo
    assert len(points.points) == 10
    assert [p.slip for p in points.points] == pytest.approx(np.linspace(0.01, 0.08, 10), abs=5e-5)
    for k in ("v_phase", "f_rated", "pole_pairs", "r1", "r_fe", "x_m", "x_leak", "r2p"):
        assert getattr(res.reference, k) == pytest.approx(getattr(ref, k))
    fit, err = res.fit, res.errors["fit"]
    assert abs(err["x_m"]) <= FIT_TOL and abs(err["r2p"]) <= FIT_TOL
    lo, hi = fit.ci95["x_leak"]
    assert lo <= ref.x_leak <= hi
    assert abs(err["r_fe"]) <= RF_BOUND
    assert res.published == res.motor("fit") and res.published.is_demo


@pytest.mark.parametrize("name", MOTORS)
def test_readme_shows_the_app_table(name):
    """data/tests/README.md quotes tab 1 exactly as the app prints it: value (error %)."""
    text = (TESTS / "README.md").read_text(encoding="utf-8")
    _bench, _points, res = _identify(name)
    for method in ("classical", "fit"):
        m = res.motor(method)
        for k in ("r_fe", "x_m", "x_leak", "r2p"):
            cell = f"{fr(getattr(m, k))} ({fr_pct(res.errors[method][k])})"
            assert cell in text, f"{name} {method} {k}: {cell} missing from README"
    assert "fichiers synthétiques, pas des mesures" in text


@pytest.mark.parametrize("name", CYCLES)
def test_cycles_are_smooth_synthetic_and_not_wltc(name):
    path = TESTS / f"{name}.csv"
    head = path.read_text(encoding="utf-8").splitlines()[0]
    assert head.startswith("# démo:") and "PAS un cycle WLTC" in head
    c = load_cycle(path)
    assert c.is_demo and c.name == f"{name} (démo)" and "wltc" not in name.lower()
    stats = vehicle.cycle_stats(c)
    assert 600.0 <= stats.duration <= 1200.0
    a = np.diff(c.v) / np.diff(c.t)
    assert np.max(np.abs(a)) <= A_MAX + 1e-9
    assert np.max(np.abs(np.diff(a))) < 0.5  # smooth: no acceleration step (m/s² per s)
    assert c.v[0] == 0.0 and c.v[-1] == 0.0 and np.all(c.v >= 0.0)


BAD = (
    ("bench_tests_bad_negative.csv", load_bench_tests,
     "bench_tests_bad_negative.csv, ligne 20 (vide) : la puissance P doit être > 0 W (valeur lue : « -"),
    ("load_points_bad_slip.csv", load_load_points,
     "load_points_bad_slip.csv, ligne 23 : glissement g = « 1.2 » hors de ]0 ; 1[ "
     "(un essai en charge est en fonctionnement moteur : 0 < g < 1)"),
    ("cycle_bad_time.csv", load_cycle,
     "cycle_bad_time.csv, ligne 104 : le temps doit être strictement croissant (99 s puis 95 s)"),
    ("cycle_bad_header.csv", load_cycle, "cycle_bad_header.csv : colonne(s) manquante(s) : « t », « v »"),
)


@pytest.mark.parametrize("filename, loader, message", BAD, ids=[b[0] for b in BAD])
def test_bad_files_raise_a_clear_french_error(filename, loader, message):
    with pytest.raises(LoaderError) as exc:
        loader(TESTS / filename)
    text = str(exc.value)
    assert text.startswith(message)
    assert not ENGLISH.search(text), text  # no English left from a lower layer
    assert filename in demo_data.BAD_FILES


def test_pyinstaller_build_copies_data_tests():
    """packaging/EVLab.spec copies the whole data/ folder (data/tests/ included) next to the executable."""
    spec = (ROOT / "packaging" / "EVLab.spec").read_text(encoding="utf-8")
    assert 'shutil.copytree(ROOT / "data", dist / "data"' in spec
    assert TESTS.parent == ROOT / "data" and (TESTS / "README.md").exists()
