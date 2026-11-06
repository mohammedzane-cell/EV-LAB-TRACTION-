"""io.femm_model: FEM model of the stator (FEMM 4.2). FEMM tests skip cleanly when FEMM is absent."""

import math

import numpy as np
import pytest

from evlab.core import winding as wd
from evlab.io import femm_model as fm

FEMM_OK, FEMM_REASON = fm.femm_available()
needs_femm = pytest.mark.skipif(not FEMM_OK, reason=f"FEMM indisponible : {FEMM_REASON}")


# --- without FEMM -------------------------------------------------------------------

def test_case_validation():
    with pytest.raises(ValueError, match="material"):
        fm.FemCase(material="Unobtainium")
    with pytest.raises(ValueError, match="current"):
        fm.FemCase(current=0.0)
    with pytest.raises(ValueError, match="n_frames"):
        fm.FemCase(n_frames=0)


def test_geometry():
    g = fm.StatorGeometry()
    assert g.r_rotor == pytest.approx(64.5) and g.r_mid_gap == pytest.approx(64.75)
    assert g.slot_pitch(36) == pytest.approx(2 * math.pi * 65 / 36)
    assert g.slot_opening < g.slot_width < g.slot_pitch(36)


def test_lua_recorder_expands_pyfemm_composites():
    rec = fm.LuaRecorder()
    rec.mi_drawline(0, 0, 1, 2.5)
    rec.mi_setblockprop("Cu", 1, 0, "A", 0, 0, -10)
    assert rec.lines == ["mi_addnode(0,0)", "mi_addnode(1,2.5)", "mi_addsegment(0,0,1,2.5)",
                         'mi_setblockprop("Cu",1,0,"A",0,0,-10)']
    with pytest.raises(AttributeError):
        rec.not_a_femm_call


def test_model_uses_the_slot_table():
    rec = fm.LuaRecorder()
    fm._build(rec, fm.FemCase(), fm.Path("/tmp/x.fem"))
    labels = [ln for ln in rec.lines if ln.startswith('mi_setblockprop("Cu"')]
    assert len(labels) == 72  # two layers × 36 slots
    table = wd.slot_table(fm.FemCase().winding)
    first = [(s.top, s.bottom) for s in table[:2]]
    assert labels[0] == f'mi_setblockprop("Cu",1,0.0,"{first[0][0][0]}",0,0,{first[0][0][1] * 10})'
    assert labels[3] == f'mi_setblockprop("Cu",1,0.0,"{first[1][1][0]}",0,0,{first[1][1][1] * 10})'
    assert sum(1 for ln in rec.lines if ln.startswith("mi_addarc")) == 2 * 36 + 4


def test_frame_script_saves_before_solving_and_checks_currents():
    lua = fm._lua_frame((6.0, -3.0, -3.0), "Z:/a.fem", "Z:/c.txt")
    lines = lua.splitlines()
    assert lines.index("mi_saveas('Z:/a.fem')") < lines.index("mi_analyze(1)")
    assert sum("mo_getcircuitproperties" in ln for ln in lines) == 3


def test_sample_points():
    case = fm.FemCase(n_gap=36, n_radial=3, n_angular=8)
    theta, r, th, xy = fm.sample_points(case)
    assert xy.shape == (36 + 3 * 8, 2)
    assert np.allclose(np.hypot(*xy[:36].T), case.geometry.r_mid_gap)


def test_unavailable_reason(monkeypatch):
    monkeypatch.setattr(fm.importlib.util, "find_spec", lambda name: None)
    ok, reason = fm.femm_available()
    assert not ok and "pyfemm" in reason


# --- with FEMM ----------------------------------------------------------------------

@pytest.fixture(scope="module")
def linear_run(tmp_path_factory):
    case = fm.FemCase(n_frames=3, material="linear", n_radial=20, n_angular=120)
    return fm.run(case, tmp_path_factory.mktemp("fem"))


@needs_femm
def test_frames_and_pngs(linear_run):
    assert len(linear_run.frames) == 3
    for f in linear_run.frames:
        assert f.png is not None and f.png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        assert f.b_mag.shape == (20, 120) and np.isfinite(f.b_r).all()


@needs_femm
def test_air_gap_fundamental_against_the_analytical_mmf(linear_run):
    cmp, curves = fm.analytic_fields(linear_run)
    assert cmp.b1_fem_spread < 0.005  # constant amplitude
    assert 0.90 < cmp.ratio < 1.10  # within ~10 % of μ0·F1/(k_c·g)
    assert cmp.b1_fem < cmp.b1_smooth  # slotting lowers B below μ0·F1/g
    assert cmp.rotation_speed == pytest.approx(cmp.expected_speed, rel=0.01)
    p = linear_run.case.winding.pole_pairs
    for f, a in zip(linear_run.frames, curves):  # same position and sign as the analytical wave
        cb, ca = np.fft.rfft(f.b_r)[p], np.fft.rfft(a)[p]
        assert (cb / ca).real > 0 and abs(np.angle(cb / ca)) < 0.01


@needs_femm
def test_saturation_lowers_the_fundamental(tmp_path, linear_run):
    """At 3× the current, M-19 steel saturates: B1/(μ0F1/k_c g) drops below the linear case."""
    hot = fm.run(fm.FemCase(n_frames=1, material="M-19 Steel", current=18.0, n_radial=4, n_angular=24),
                 tmp_path, frames_png=False)
    r_lin = fm.analytic_fields(linear_run)[0].ratio
    r_sat = hot.fundamental()[0] / fm.analytic_fields(hot)[0].b1_carter
    assert r_sat < r_lin - 0.05
