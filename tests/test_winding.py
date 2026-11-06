import math

import numpy as np
import pytest

from evlab.core import winding as wd

REF = {  # CLAUDE.md: Z = 36, 2p = 4, m = 3
    9: {"kw": {1: 0.9598, 5: 0.2176, 7: 0.1774}},
    7: {"kd1": 0.9598, "kp1": 0.9397, "kw": {1: 0.9019, 5: -0.0378, 7: -0.1359}},
}


@pytest.fixture(params=[9, 7])
def w(request):
    return wd.Winding(z=36, poles=4, m=3, y=request.param)


# --- geometry and factors -----------------------------------------------------------

def test_geometry():
    w = wd.Winding(z=36, poles=4, m=3, y=7)
    assert (w.q, w.tau, w.pole_pairs) == (3, 9, 2)
    assert w.alpha == pytest.approx(math.radians(20))


@pytest.mark.parametrize("y", [9, 7])
@pytest.mark.parametrize("nu", [1, 5, 7])
def test_winding_factors_claude_md(y, nu):
    w = wd.Winding(z=36, poles=4, m=3, y=y)
    assert wd.winding_factor(w, nu) == pytest.approx(REF[y]["kw"][nu], abs=1e-4)


def test_distribution_and_pitch_factors_y7():
    w = wd.Winding(z=36, poles=4, m=3, y=7)
    assert wd.distribution_factor(w, 1) == pytest.approx(0.9598, abs=1e-4)
    assert wd.pitch_factor(w, 1) == pytest.approx(0.9397, abs=1e-4)
    assert wd.winding_factor(w, 1) == pytest.approx(wd.distribution_factor(w, 1) * wd.pitch_factor(w, 1))


def test_factors_vectorised():
    w = wd.Winding(z=36, poles=4, m=3, y=7)
    nu = np.array([1, 5, 7])
    assert np.allclose(wd.winding_factor(w, nu), [0.9019, -0.0378, -0.1359], atol=1e-4)


# --- validation -----------------------------------------------------------------

def test_non_integer_pitch_rejected():
    with pytest.raises(ValueError, match="integer number of slots") as exc:
        wd.Winding(z=36, poles=4, m=3, y=7.5)  # "5/6 pitch" of τ = 9
    assert "τ = 9" in str(exc.value) and "y = 7 or y = 8" in str(exc.value)


@pytest.mark.parametrize("kw, msg", [
    (dict(z=36, poles=4, m=3, y=0), "1 <= y <= τ"),
    (dict(z=36, poles=4, m=3, y=10), "1 <= y <= τ"),
    (dict(z=30, poles=4, m=3, y=7), "q = Z/(2p·m)"),
    (dict(z=36, poles=5, m=3, y=7), "even"),
    (dict(z=0, poles=4, m=3, y=7), "z"),
    (dict(z=36, poles=4, m=3.0, y=7), "m"),
])
def test_validation(kw, msg):
    with pytest.raises(ValueError, match=msg.replace("(", r"\(").replace(")", r"\)")):
        wd.Winding(**kw)


# --- slot table ----------------------------------------------------------------

def test_slot_table_belts_and_layers(w):
    table = wd.slot_table(w)
    assert len(table) == 36
    belts = [table[s].top for s in range(0, 36, 3)]
    assert belts[:6] == [("A", 1), ("C", -1), ("B", 1), ("A", -1), ("C", 1), ("B", -1)]
    assert belts[6:] == belts[:6]  # second pole pair
    for s in range(36):
        phase, sign = table[s].top
        assert table[(s + w.y) % 36].bottom == (phase, -sign)
    # every phase has Z/m coil sides per layer, balanced signs
    for ph in "ABC":
        tops = [t.top[1] for t in table if t.top[0] == ph]
        assert len(tops) == 12 and sum(tops) == 0


def test_full_pitch_layers_are_identical():
    table = wd.slot_table(wd.Winding(z=36, poles=4, m=3, y=9))
    assert all(t.top == t.bottom for t in table)
    table7 = wd.slot_table(wd.Winding(z=36, poles=4, m=3, y=7))
    # y = τ − 2: bottom[s] = top[s + 2], so 2 slots of every 3-slot belt mix two phases
    assert all(table7[s].bottom == table7[(s + 2) % 36].top for s in range(36))
    assert sum(t.top != t.bottom for t in table7) == 24


def test_slot_labels(w):
    table = wd.slot_table(w)
    assert table[0].labels() == ("A+", "A+")
    assert table[1].labels() == ("A+", "A+" if w.y == 9 else "C−")


# --- MMF ----------------------------------------------------------------------

@pytest.mark.parametrize("nu", [1, 5, 7, 11, 13])
def test_mmf_harmonics_match_kw_over_nu(w, nu):
    theta, f_a = wd.phase_mmf(w, "A", n_theta=36 * 128)
    spec = wd.mmf_spectrum(w, f_a, nu_max=15)
    ratio = spec[nu] / spec[1]
    expected = abs(wd.winding_factor(w, nu)) / nu / abs(wd.winding_factor(w, 1))
    assert ratio == pytest.approx(expected, rel=0.01)


def test_mmf_is_stepped_with_zero_mean(w):
    theta, f_a = wd.phase_mmf(w, "A", n_theta=36 * 16)
    assert abs(f_a.mean()) < 1e-12
    assert len(np.unique(np.round(f_a, 9))) <= 36  # piecewise constant between slots
    assert theta[0] > 0 and theta[-1] < 2 * math.pi  # samples between slot positions


def test_analytical_amplitude(w):
    """Fundamental of one phase: (4/π)·(N·kw1)/(2p)·i per pole, here with N = Z/m coils of 1 turn."""
    theta, f_a = wd.phase_mmf(w, "A", n_theta=36 * 128, turns_per_coil=1, current=1.0)
    amp = wd.mmf_spectrum(w, f_a, nu_max=1, normalise=False)[1]
    n_ph = w.z / w.m
    assert amp == pytest.approx(4 / math.pi * n_ph * wd.winding_factor(w, 1) / w.poles, rel=0.01)


# --- rotating field --------------------------------------------------------------

def test_rotating_field_fundamental(w):
    f = 50.0
    rf = wd.rotating_field(w, f=f, current=10.0, n_theta=36 * 32, n_t=180)
    assert rf.mmf.shape == (180, 36 * 32)
    amp, pos = rf.fundamental_amplitude, rf.fundamental_position
    assert np.ptp(amp) / amp.mean() < 1e-3  # constant amplitude
    speed = np.polyfit(rf.t, np.unwrap(pos * w.pole_pairs) / w.pole_pairs, 1)[0]
    assert speed == pytest.approx(2 * math.pi * f / w.pole_pairs, rel=1e-3)  # rad/s, mechanical
    # three-phase fundamental = 3/2 × one phase at peak current
    _, f_a = wd.phase_mmf(w, "A", n_theta=36 * 32, current=10.0)
    one = wd.mmf_spectrum(w, f_a, nu_max=1, normalise=False)[1]
    assert amp.mean() == pytest.approx(1.5 * one, rel=1e-3)
    assert rf.t[-1] < 1 / f  # one electrical period, end excluded


def test_rotating_field_is_sum_of_phases(w):
    rf = wd.rotating_field(w, f=50.0, current=1.0, n_theta=360, n_t=12)
    k = 5
    total = sum(i[k] * wd.phase_mmf(w, ph, n_theta=360)[1] for ph, i in zip("ABC", rf.currents))
    assert np.allclose(rf.mmf[k], total)


# --- EMF (TD2 Ex 1) -------------------------------------------------------------

def test_td2_ex1():
    """60 Hz, 900 tr/min, 48 slots × 12 conductors = 576 conductors, Φ = 0.04 Wb, Kb = 1."""
    p = wd.pole_pairs_from_speed(60.0, 900 * 2 * math.pi / 60)
    assert p == 4  # 8 poles
    n = wd.turns_from_conductors(576, m=3)
    assert n == 96
    e = wd.emf(60.0, n, 1.0, 0.04)
    assert e == pytest.approx(4.44 * 60 * 96 * 0.04)
    assert e == pytest.approx(1023.0, abs=0.5)
    assert math.sqrt(3) * e == pytest.approx(1772.0, abs=0.5)  # no-load line voltage, star


def test_emf_uses_kw1():
    w = wd.Winding(z=36, poles=4, m=3, y=7)
    n = wd.turns_per_phase(w, turns_per_coil=10)
    assert n == 120  # 36 coils / 3 phases × 10 turns
    assert wd.emf(50.0, n, wd.winding_factor(w, 1), 0.01) == pytest.approx(4.44 * 50 * 120 * 0.9019 * 0.01, rel=1e-4)


def test_pole_pairs_from_speed_validation():
    assert wd.pole_pairs_from_speed(50.0, 1000 * 2 * math.pi / 60) == 3  # synchronous speed
    with pytest.raises(ValueError, match="integer"):
        wd.pole_pairs_from_speed(50.0, 1450 * 2 * math.pi / 60)  # a motor speed, with slip


def test_even_harmonics_vanish(w):
    _, f_a = wd.phase_mmf(w, "A", n_theta=36 * 128)
    spec = wd.mmf_spectrum(w, f_a, nu_max=12)
    an = wd.analytical_spectrum(w, 12)
    for nu in (2, 4, 6, 8, 10, 12):
        assert spec[nu] < 1e-9 and an[nu] == 0.0
    assert spec[3] == pytest.approx(an[3], rel=0.01)  # one phase alone keeps its triplens
