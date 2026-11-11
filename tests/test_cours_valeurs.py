"""core.cours_valeurs: live values of « Avec votre moteur » and the inputs of the worked examples."""

import math

import numpy as np
import pytest

from evlab.core import circuit, drive, losses, optimise, thermal, vehicle
from evlab.core import cours_valeurs as cv
from evlab.core import identification as ident
from evlab.core.session import td5_ex1
from evlab.io import cours


@pytest.fixture(scope="module")
def demo():
    return cours.donnees_demo()


@pytest.fixture(scope="module")
def ex(demo):
    return cv.exemples(demo)


def test_no_motor_gives_none():
    assert cv.valeurs_moteur(None) is None


def test_reference_motor_values():
    m = td5_ex1()
    v = cv.valeurs_moteur(m)
    assert v["g_c"] == pytest.approx(0.5) and v["t_max"] == pytest.approx(126.29, abs=0.01)
    assert v["i_mu"] == pytest.approx(5.0) and v["n_s"] == pytest.approx(1500.0)
    assert v["e_n"] == pytest.approx(230.0)  # R1 = 0: E = V at no load
    assert v["tbd_f100"] == pytest.approx(v["tbd_fn"] / 4.0)  # field weakening, R1 = 0: T_bd ∝ 1/f²
    assert v["p_fer_n"] == pytest.approx(3 * 230.0**2 / 230.0)
    assert v["r2_kn"] == pytest.approx(2.0 * cv.K_N_EX**2) and v["x_kn"] == pytest.approx(4.0 * cv.K_N_EX**2)
    assert v["flux_limite_v"] == pytest.approx(optimise.FLUX_LIMIT * 230.0 / 50.0)
    assert v["r1_nul"].startswith("oui") and v["r1_classe"] == "—" and v["t_r1"] == "—"
    env = drive.envelope(m, drive.demo_settings(n_points=150))
    st = losses.LossSettings()
    assert v["p_nom"] == pytest.approx(vehicle.rated_power(m, env, st))
    assert v["classe"] == vehicle.wltc_class(v["p_nom"] / vehicle.demo_quadricycle().mass)


def test_identified_motor_values(demo):
    m = cv.demo_motor(demo)
    v = cv.valeurs_moteur(m)
    assert m.r1 > 0 and m.is_demo and v["source"].endswith("(démo)")
    assert v["r1_nul"] == "non"
    t_class = thermal.INSULATION_CLASSES["F"] + 273.15
    assert v["r1_classe"] == pytest.approx(m.r1 * (234.5 + t_class - 273.15) / (234.5 + m.r1_temperature_k - 273.15))
    assert v["t_r1"] == pytest.approx(m.r1_temperature_k - 273.15)
    assert v["r1_tw"] == pytest.approx(losses.stator_resistance(m, losses.LossSettings(winding_temperature_k=m.r1_temperature_k)))


def test_demo_motor_is_the_published_fit(demo):
    res = ident.compare_methods(demo.records, "both", points=demo.points, layout="tp3", reference=demo.reference,
                                is_demo=True, source="Identification")
    assert cv.demo_motor(demo) == res.published == res.motor("fit")


def test_examples_are_finite_numbers(ex):
    assert len(ex) > 150
    for k, x in ex.items():
        assert isinstance(x, float | int) and math.isfinite(x), k


def test_noise_free_files_give_the_reference_back(ex):
    """The noisy 1,77 Ω is noise: the same chain on noise-free files returns R'2 and X exactly."""
    assert ex["r2_exact_sans_bruit"] == pytest.approx(ex["demo_ref_r2"], rel=1e-3)
    assert ex["x_exact_sans_bruit"] == pytest.approx(ex["demo_ref_x"], rel=1e-3)
    assert abs(ex["r2_exact"] - ex["demo_ref_r2"]) > 0.1  # the noisy value really is off


def test_examples_are_consistent(ex):
    assert ex["rapport_tournant"] == pytest.approx(1.5, rel=1e-5)  # 3/2, to the FFT resolution
    assert ex["best_eta_bilan"] == pytest.approx(ex["demo_eta_max"], rel=1e-9)
    total = sum(ex[f"best_{k}"] for k in ("p_out", "p_cu1", "p_cu2", "p_fe", "p_mech", "p_inv"))
    assert total == pytest.approx(ex["best_p_in"], rel=1e-6)  # the power balance closes
    assert ex["vie_moins_10"] == pytest.approx(2 * ex["vie_classe"]) and ex["vie_plus_10"] == pytest.approx(ex["vie_classe"] / 2)
    assert ex["tau_essai_min"] == pytest.approx(ex["tau_lent_min"], rel=0.01)
    assert ex["ref_pfer"] == pytest.approx(ex["ref_pfer_formule"])  # R1 = 0: 3E²/Rf = 3V²/Rf
    assert ex["ref_gc"] == pytest.approx(ex["ref_gc_num"], rel=1e-6)
    assert ex["r2_kn"] == pytest.approx(ex["r2_k1"] * ex["k_n2"])


def test_duplicate_keys_are_refused(monkeypatch, demo):
    monkeypatch.setattr(cv, "_exemples_validation", lambda: {"ref_gc": 0.5})
    with pytest.raises(ValueError, match="duplicate"):
        cv.exemples(demo)


def test_no_qt_no_io_in_the_module():
    src = cv.__file__
    text = open(src, encoding="utf-8").read()
    assert "PySide6" not in text and "open(" not in text and "print(" not in text
    assert "evlab.io" not in text


def test_reference_values_quoted_by_the_course():
    m = td5_ex1()
    assert circuit.breakdown_slip(m) == pytest.approx(0.5)
    assert np.isclose(circuit.max_torque(m), 126.29, atol=0.01)
