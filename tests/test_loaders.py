"""io.loaders and io.demo_data: demo files, French error messages, end-to-end identification."""

import math
from pathlib import Path

import pytest

from evlab.core import circuit
from evlab.core import identification as ident
from evlab.io import demo_data
from evlab.io.loaders import LoaderError, load_bench_tests, load_load_points, reference_motor

DATA = Path(__file__).resolve().parents[1] / "data"
BENCH = DATA / demo_data.BENCH_FILE
LOAD = DATA / demo_data.LOAD_FILE


def test_demo_files_are_up_to_date_with_the_generator(tmp_path):
    p1, p2 = demo_data.write_demo_files(tmp_path)
    assert p1.read_text(encoding="utf-8") == BENCH.read_text(encoding="utf-8"), \
        "data/bench_tests_demo.csv is stale: run python -m evlab.io.demo_data"
    assert p2.read_text(encoding="utf-8") == LOAD.read_text(encoding="utf-8")


def test_load_bench_demo():
    b = load_bench_tests(BENCH)
    assert b.is_demo
    assert b.dc is not None and b.dc.temperature_k == pytest.approx(293.15)
    assert len(b.no_load) == 8
    assert b.winding_temperature_k == pytest.approx(348.15)
    assert b.locked.v_phase == pytest.approx(97.8172 / math.sqrt(3))
    assert b.no_load[0].v_phase == pytest.approx(151.794 / math.sqrt(3))


def test_load_points_demo():
    lp = load_load_points(LOAD)
    assert lp.is_demo
    assert len(lp.points) == 12
    assert lp.points[0].slip == pytest.approx(0.02) and lp.points[-1].slip == pytest.approx(0.40)
    assert lp.points[0].v_phase == pytest.approx(230.0, rel=1e-5)  # U = 398,372 V line


def test_reference_motor_from_metadata():
    ref = reference_motor(load_bench_tests(BENCH).meta)
    assert ref is not None and ref.is_demo
    assert (ref.r1, ref.r_fe, ref.x_m, ref.x_leak, ref.r2p) == (0.5, 230.0, 46.0, 4.0, 2.0)
    assert reference_motor({}) is None


def test_noise_free_demo_identifies_the_reference(tmp_path):
    spec = demo_data.DemoSpec(noise=0.0)
    p1, p2 = demo_data.write_demo_files(tmp_path, spec)
    b = load_bench_tests(p1)
    rec = ident.TestRecords(dc=b.dc, t_hot_k=b.winding_temperature_k, no_load=b.no_load, locked=b.locked,
                            pole_pairs=2, v_rated=230.0, f_rated=50.0, p_mech=None)
    rep = ident.run_identification(rec, method="exact")
    ref = spec.motor
    for n in ("r1", "r_fe", "x_m", "x_leak", "r2p"):
        assert getattr(rep.motor, n) == pytest.approx(getattr(ref, n), rel=2e-3), n  # CSV keeps 6 digits
    fit = ident.fit_load_points(load_load_points(p2).points, rep.motor, p_mech=rep.p_mech, n_starts=1)
    for n in ("x_m", "x_leak", "r2p"):
        assert getattr(fit.motor, n) == pytest.approx(getattr(ref, n), rel=2e-3), n


def test_noisy_demo_runs_the_whole_chain():
    b = load_bench_tests(BENCH)
    rec = ident.TestRecords(dc=b.dc, t_hot_k=b.winding_temperature_k, no_load=b.no_load, locked=b.locked,
                            pole_pairs=2, v_rated=230.0, f_rated=50.0, p_mech=None)
    rep = ident.run_identification(rec, method="classical")
    fit = ident.fit_load_points(load_load_points(LOAD).points, rep.motor, p_mech=rep.p_mech)
    assert fit.success and circuit.breakdown(fit.motor)[1] > 0


# --- French error messages ----------------------------------------------------------

def _write(tmp_path, text, name="essais.csv"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


BENCH_HEAD = "essai,U [V],I [A],P [W],f [Hz],T [°C]\n"
BENCH_OK = BENCH_HEAD + "dc,4,5,,,20\nvide,400,5,700,50,75\nrotor_bloque,100,14,1200,50,75\n"


def test_minimal_bench_file_is_not_demo(tmp_path):
    b = load_bench_tests(_write(tmp_path, BENCH_OK))
    assert not b.is_demo and b.meta == {}


@pytest.mark.parametrize("text, msg", [
    ("", "fichier vide"),
    ("# commentaire seul\n\n", "fichier vide"),
    (BENCH_HEAD, "en-tête seul"),
    ("essai,U [V],P [W],f [Hz],T [°C]\nvide,400,700,50,75\n", "colonne(s) manquante(s) : « I »"),
    ("essai,U [kV],I [A],P [W],f [Hz],T [°C]\nvide,0.4,5,700,50,75\n",
     "unité incorrecte pour la colonne « U » : « kV » (attendu : « V »)"),
    ("essai,U,I [A],P [W],f [Hz],T [°C]\nvide,400,5,700,50,75\n", "unité incorrecte pour la colonne « U » : aucune"),
    (BENCH_HEAD + "vide,400,5,abc,50,75\nrotor_bloque,100,14,1200,50,75\n", "« abc » n'est pas un nombre"),
    (BENCH_HEAD + "vide,400,5,,50,75\nrotor_bloque,100,14,1200,50,75\n", "valeur manquante dans la colonne « P »"),
    (BENCH_HEAD + "court-circuit,400,5,700,50,75\n", "type d'essai « court-circuit » inconnu"),
    (BENCH_HEAD + "rotor_bloque,100,14,1200,50,75\n", "aucun essai « vide »"),
    (BENCH_HEAD + "vide,400,5,700,50,75\n", "exactement un essai « rotor_bloque » (trouvé : 0)"),
    (BENCH_HEAD + "vide,400,5,-700,50,75\nrotor_bloque,100,14,1200,50,75\n", "ligne 2 (vide) : la puissance P doit être > 0 W (valeur lue : « -700 »)"),
    (BENCH_HEAD + "vide,400,0,700,50,75\nrotor_bloque,100,14,1200,50,75\n", "ligne 2 (vide) : le courant I doit être > 0 A"),
    (BENCH_HEAD + "dc,4,5,,,20\ndc,4,5,,,20\n", "plusieurs essais « dc »"),
])
def test_bench_errors_in_french(tmp_path, text, msg):
    with pytest.raises(LoaderError) as exc:
        load_bench_tests(_write(tmp_path, text))
    assert msg in str(exc.value)
    assert "essais.csv" in str(exc.value) or "ligne" in str(exc.value)


LOAD_HEAD = "g [-],U [V],I [A],T [N·m],cos_phi [-],f [Hz]\n"


@pytest.mark.parametrize("text, msg", [
    ("", "fichier vide"),
    ("g [-],U [V],I [A],cos_phi [-],f [Hz]\n0.02,398,6,0.5,50\n", "colonne(s) manquante(s) : « T »"),
    ("g [-],U [V],I [A],T [kN·m],cos_phi [-],f [Hz]\n0.02,398,6,0.01,0.5,50\n", "unité incorrecte pour la colonne « T »"),
    (LOAD_HEAD + "0.02,398,6,10,1.3,50\n" * 3, "valeur invalide"),
    (LOAD_HEAD + "0.02,398,6,10,0.5,50\n", "au moins 3 points"),
    (LOAD_HEAD + "0.02,0,6,10,0.5,50\n" * 3, "la tension U doit être > 0 V"),
])
def test_load_point_errors_in_french(tmp_path, text, msg):
    with pytest.raises(LoaderError, match=None) as exc:
        load_load_points(_write(tmp_path, text, "charge.csv"))
    assert msg in str(exc.value)


def test_missing_file():
    with pytest.raises(LoaderError, match="Fichier introuvable"):
        load_bench_tests("nulle_part.csv")


def test_loader_error_is_a_value_error():
    assert issubclass(LoaderError, ValueError)


def test_nameplate_from_demo_file():
    from evlab.io.loaders import nameplate

    plate = nameplate(load_bench_tests(BENCH).meta)
    assert plate.v_phase == 230.0 and plate.f == 50.0 and plate.pole_pairs == 2
    assert plate.rated_speed == pytest.approx(1350 * 2 * math.pi / 60)  # tr/min -> rad/s at the edge
    empty = nameplate({})
    assert empty.v_phase is None and empty.rated_speed is None
    with pytest.raises(LoaderError, match="plaque"):
        nameplate({"plaque.paires_de_poles": "deux"})
