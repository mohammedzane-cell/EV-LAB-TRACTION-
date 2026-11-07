"""io.femm_model: FEM model of the stator (FEMM 4.2). FEMM tests skip cleanly when FEMM is absent."""

import json
import math
import sys

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
    with pytest.raises(ValueError, match="gap_layers"):
        fm.FemCase(gap_layers=0)


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


def test_lua_args_match_pyfemm(monkeypatch):
    """Same text as pyfemm's doargs (checked against it when pyfemm is installed)."""
    args = ("Cu", 1, 0.0, -10, 2.5e-3, 3 + 4j)
    assert fm.lua_args(*args) == '("Cu",1,0.0,-10,0.0025,(3+4*I))'
    assert fm.lua_args() == "()"
    femm = pytest.importorskip("femm")
    assert fm.lua_args(*args) == femm.doargs(*args)


def test_no_pyfemm_needed_to_write_the_model(monkeypatch):
    monkeypatch.setitem(sys.modules, "femm", None)  # import femm now raises ImportError
    rec = fm.LuaRecorder()
    fm._build(rec, fm.FemCase(), fm.Path("/tmp/x.fem"))
    assert len(rec.lines) > 500


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


def test_peak_and_rms():
    assert fm.peak_from_rms(5.0) == pytest.approx(7.0710678)  # TD5 Ex 1: I_µ = 230/46 = 5 A RMS
    assert fm.rms_from_peak(6.0) == pytest.approx(4.2426407)
    assert fm.FemCase(current=6.0).current_rms == pytest.approx(4.2426407)


def test_symmetry_step_and_solved_frames():
    assert fm.FemCase(n_frames=12).symmetry_step == 2 and fm.solved_indices(fm.FemCase(n_frames=12)) == (0, 1)
    assert fm.FemCase(n_frames=5).symmetry_step is None and fm.solved_indices(fm.FemCase(n_frames=5)) == (0, 1, 2, 3, 4)
    case = fm.FemCase(n_frames=6)
    a, b, c = case.currents(0.0)
    assert case.currents(case.frame_time(1)) == pytest.approx((-b, -c, -a))  # A+ → C− → B+ permutation


def _stepped_b(case, currents, theta):
    """B_r ∝ stepped MMF of the slot conductors (exact, no FEMM): F jumps by Σ i·N at each slot."""
    w = case.winding
    c = sum(i * wd.slot_conductors(w, ph, case.turns_per_coil) for ph, i in zip(wd.PHASES, currents))
    slots = 2 * math.pi * np.arange(w.z) / w.z
    f = (np.mod(theta, 2 * math.pi)[:, None] > slots[None, :]) @ c
    return -2e-3 * (f - c @ (1 - np.arange(w.z) / w.z))  # zero mean, as the air-gap flux


def test_rotate_frame_turns_the_field_by_one_belt():
    case = fm.FemCase(n_frames=12, n_gap=720, n_radial=2, n_angular=24)
    theta, r, th, _ = fm.sample_points(case)
    f0 = fm.FemFrame(0.0, case.currents(0.0), theta, _stepped_b(case, case.currents(0.0), theta), r, th,
                     np.tile(_stepped_b(case, case.currents(0.0), th), (2, 1)))
    for m in (1, 2, 5):
        rot = fm.rotate_frame(f0, case, m)
        t = m / (6 * case.frequency)
        assert rot.t == pytest.approx(t) and rot.currents == pytest.approx(case.currents(t))
        assert np.allclose(rot.b_r, _stepped_b(case, case.currents(t), theta), atol=1e-12)
        assert np.allclose(rot.b_mag[0], _stepped_b(case, case.currents(t), th), atol=1e-12)


def test_shift_off_grid_interpolates():
    grid = 2 * math.pi * np.arange(100) / 100
    assert np.allclose(fm._shift(np.cos(grid), grid, 0.3), np.cos(grid - 0.3), atol=2e-3)


class FakeFemm:
    """Stands in for pyfemm (native path): B_r from the stepped MMF of the circuit currents set."""

    def __init__(self, case):
        self.case, self.calls, self.i = case, [], {}

    def __getattr__(self, name):
        def call(*args):
            self.calls.append(name)
        return call

    def mi_modifycircprop(self, ph, prop, value):
        self.calls.append("mi_modifycircprop")
        self.i[ph] = value

    def mo_getcircuitproperties(self, ph):
        return [self.i[ph], 0.0, 0.0]

    def mo_getb(self, x, y):
        th = math.atan2(y, x)
        b = _stepped_b(self.case, [self.i[ph] for ph in wd.PHASES], np.array([th]))[0]
        return [b * math.cos(th), b * math.sin(th)]


@pytest.fixture
def native(monkeypatch):
    """Run io.femm_model.run through the Windows (pyfemm-native) path with FakeFemm."""
    monkeypatch.setattr(fm, "_native", lambda: True)
    monkeypatch.setattr(fm, "_ensure_display", lambda: None)
    monkeypatch.setattr(fm, "femm_available", lambda: (True, "FEMM 4.2 disponible"))

    def use(case):
        fake = FakeFemm(case)
        monkeypatch.setitem(sys.modules, "femm", fake)
        return fake
    return use


def test_native_path_and_symmetry_without_femm(native, tmp_path):
    case = fm.FemCase(n_frames=12, n_gap=72, n_radial=2, n_angular=24)
    fake = native(case)
    seen = []
    res = fm.run(case, tmp_path, progress=lambda k, n: seen.append((k, n)), frames_png=False)
    assert res.solved == (0, 1) and len(res.frames) == 12 and seen == [(1, 2), (2, 2)]
    i = fake.calls.index("mi_analyze")
    assert fake.calls[i - 4:i + 2] == ["mi_modifycircprop"] * 3 + ["mi_saveas", "mi_analyze", "mi_loadsolution"]
    assert "mi_drawline" in fake.calls  # pyfemm's own composites, no Lua file on Windows
    native(case)
    full = fm.run(case, tmp_path, frames_png=False, solve=tuple(range(12)))
    assert full.solved == tuple(range(12))
    for a, b in zip(res.frames, full.frames):
        assert a.t == pytest.approx(b.t)
        assert np.allclose(a.b_r, b.b_r, atol=1e-12) and np.allclose(a.b_mag, b.b_mag, atol=1e-12)


def test_solve_must_cover_every_frame():
    with pytest.raises(ValueError, match="derivable"):
        fm.run(fm.FemCase(n_frames=12), "/tmp", solve=(0,))
    with pytest.raises(ValueError, match="derivable"):
        fm.run(fm.FemCase(n_frames=5), "/tmp", solve=(0, 1))
    with pytest.raises(ValueError, match="solve indices"):
        fm.run(fm.FemCase(n_frames=6), "/tmp", solve=(0, 6))


def test_cache_round_trip(native, tmp_path):
    case = fm.FemCase(n_frames=6, n_gap=72, n_radial=2, n_angular=24, current=7.07)
    native(case)
    res = fm.run(case, tmp_path / "png", frames_png=True)
    root = tmp_path / "cache"
    folder = fm.save_cache(res, root)
    assert folder.name == "m19_7.07A_10sp_y7_6im" == fm.cache_key(case)
    assert sorted(p.name for p in folder.iterdir()) == sorted(["b_r_demo.csv", "meta.json"] + [
        f"frame_{k:03d}.png" for k in range(6)])
    assert "theta [rad],B_r frame_000 [T]" in (folder / "b_r_demo.csv").read_text().splitlines()[0]
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    assert meta["demo"] and meta["solved"] == [0] and meta["case"]["current_peak"] == 7.07
    back = fm.load_cache(folder)
    assert back.cached and back.case == case and back.solved == (0,)
    for a, b in zip(res.frames, back.frames):
        assert np.array_equal(a.b_r, b.b_r) and a.currents == b.currents and b.b_mag is None
        assert b.png.read_bytes()[:4] == b"\x89PNG"
    assert fm.cached_runs(root) == [folder] and fm.find_cache(case, root) == folder
    assert fm.find_cache(fm.FemCase(), root) is None and fm.cached_runs(tmp_path / "none") == []
    assert fm.cache_key(fm.FemCase(gap_layers=10)).endswith("_g10")
    (folder / "b_r_demo.csv").write_text("theta\n1,2\n")
    with pytest.raises(ValueError, match="cache FEM"):
        fm.load_cache(folder)


def test_committed_cache_loads():
    runs = fm.cached_runs()
    assert runs, "data/fem_cache should hold the pre-computed runs"
    for folder in runs:
        res = fm.load_cache(folder)
        cmp, _ = fm.analytic_fields(res)
        assert len(res.frames) == res.case.n_frames and all(f.png.exists() for f in res.frames)
        assert cmp.rotation_speed == pytest.approx(cmp.expected_speed, rel=0.01)


# --- with FEMM ----------------------------------------------------------------------

@pytest.fixture(scope="module")
def linear_run(tmp_path_factory):
    """Frames 0 and T/6 solved directly; frames 2…5 derived from frame 0 by the symmetry.

    10 mesh layers across the gap: with the default 3 the meshes of the two frames differ enough at the
    slot-lip corners to give 1,9 % pointwise (0,3 % RMS, B1 identical to 0,01 %), see A32.
    """
    case = fm.FemCase(n_frames=6, material="linear", n_radial=20, n_angular=120, gap_layers=10)
    return fm.run(case, tmp_path_factory.mktemp("fem"), solve=(0, 1))


@needs_femm
def test_symmetry_matches_a_solved_frame(linear_run):
    """FEMM's frame at T/6 equals frame 0 turned by 3 slots (30° mech.) with A+ → C− → B+: |ΔB_r| < 1 %."""
    f0, f1 = linear_run.frames[:2]
    rot = fm.rotate_frame(f0, linear_run.case, 1)
    assert linear_run.solved == (0, 1)
    assert np.max(np.abs(rot.b_r - f1.b_r)) < 0.01 * np.max(np.abs(f1.b_r))
    assert np.max(np.abs(rot.b_mag - f1.b_mag)) < 0.02 * np.max(f1.b_mag)  # iron/slot mesh is not refined


@needs_femm
def test_frames_and_pngs(linear_run):
    assert len(linear_run.frames) == 6
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
