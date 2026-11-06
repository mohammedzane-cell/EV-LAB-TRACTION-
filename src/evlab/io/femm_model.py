"""2-D FEMM model of the 36-slot, 4-pole stator with a simplified rotor (optional, needs pyfemm + FEMM 4.2).

Only used when pyfemm and FEMM 4.2 are installed (Windows, or Linux through Wine
with a display, e.g. Xvfb). Everything else in the application works without it.

Model (docs/assumptions.md A32): planar magnetostatic; stator with semi-open
rectangular slots, two layers per slot; smooth solid iron rotor without bars
(magnetising field of the stator currents only); slot currents assigned from
core.winding.slot_table: the phase of each layer, sign ±, N_c turns; balanced
currents i_k(t) = I·cos(ωt − 2πk/3) stepped over one electrical period.
For each frame, a Lua loop inside FEMM samples B on a polar grid (|B| map) and
along a circle in the middle of the air gap (B_r(θ)); matplotlib draws the frames.
"""

from __future__ import annotations

import atexit
import importlib.util
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from evlab.core import winding as wd

MATERIALS = ("M-19 Steel", "linear")


@dataclass(frozen=True)
class StatorGeometry:
    """Dimensions in mm (A32)."""

    r_outer: float = 100.0  # stator outer radius
    r_bore: float = 65.0  # stator bore radius
    gap: float = 0.5  # air gap
    slot_opening: float = 2.5  # width b0
    lip: float = 1.0  # opening height h0
    slot_width: float = 6.0  # body width bs
    slot_depth: float = 18.0  # body depth hs
    stack: float = 150.0  # axial length (does not change B in 2-D)

    @property
    def r_rotor(self) -> float:
        return self.r_bore - self.gap

    @property
    def r_mid_gap(self) -> float:
        return self.r_bore - self.gap / 2.0

    def slot_pitch(self, z: int) -> float:
        """Slot pitch at the bore, mm."""
        return 2.0 * math.pi * self.r_bore / z


@dataclass(frozen=True)
class FemCase:
    """One FEM run: winding, geometry, currents and sampling."""

    winding: wd.Winding = field(default_factory=lambda: wd.Winding(36, 4, 3, 7))
    geometry: StatorGeometry = field(default_factory=StatorGeometry)
    turns_per_coil: int = 10
    current: float = 6.0  # peak phase current, A
    frequency: float = 50.0  # Hz (only sets the time axis)
    n_frames: int = 12  # per electrical period
    material: str = "M-19 Steel"
    n_gap: int = 720  # samples along the mid-gap circle
    n_radial: int = 40  # |B| map grid
    n_angular: int = 240

    def __post_init__(self) -> None:
        if self.material not in MATERIALS:
            raise ValueError(f"material must be one of {MATERIALS}, got {self.material!r}")
        for name in ("turns_per_coil", "n_frames", "n_gap", "n_radial", "n_angular"):
            v = getattr(self, name)
            if not isinstance(v, int) or v < 1:
                raise ValueError(f"{name} must be an integer >= 1, got {v!r}")
        if not math.isfinite(self.current) or self.current <= 0:
            raise ValueError(f"current must be > 0 A, got {self.current!r}")


@dataclass(frozen=True)
class FemFrame:
    """One solved instant: currents, air-gap B_r(θ) and the |B| map (polar grid)."""

    t: float  # s
    currents: tuple[float, float, float]  # A, phases A, B, C
    theta: np.ndarray  # rad, mid-gap samples
    b_r: np.ndarray  # T, radial flux density in the middle of the gap
    r_grid: np.ndarray  # mm
    th_grid: np.ndarray  # rad
    b_mag: np.ndarray  # T, shape (n_radial, n_angular)
    png: Path | None = None


@dataclass(frozen=True)
class FemResult:
    case: FemCase
    frames: tuple[FemFrame, ...]
    solve_seconds: float

    def fundamental(self) -> np.ndarray:
        """Air-gap B_r fundamental amplitude per frame, T (FFT bin p of B_r(θ))."""
        p = self.case.winding.pole_pairs
        return np.array([2.0 * abs(np.fft.rfft(f.b_r)[p]) / f.b_r.size for f in self.frames])


# --- availability -----------------------------------------------------------------------

def _femm_exe() -> Path | None:
    for p in (Path.home() / ".wine/drive_c/femm42/bin/femm.exe", Path("C:/femm42/bin/femm.exe"),
              Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "femm42/bin/femm.exe"):
        if p.exists():
            return p
    return None


def femm_available() -> tuple[bool, str]:
    """(available, reason): pyfemm importable, FEMM 4.2 found, and Wine + a display (or Xvfb) on Linux."""
    if importlib.util.find_spec("femm") is None:
        return False, "pyfemm n'est pas installé"
    if _femm_exe() is None:
        return False, "FEMM 4.2 introuvable (femm.exe)"
    if sys.platform != "win32":
        if shutil.which("wine") is None:
            return False, "Wine introuvable (FEMM est un programme Windows)"
        if not os.environ.get("DISPLAY") and shutil.which("Xvfb") is None:
            return False, "pas d'affichage X ni de Xvfb pour lancer FEMM"
    return True, "FEMM 4.2 disponible"


_xvfb: subprocess.Popen | None = None


def _ensure_display() -> None:
    """On Linux without DISPLAY, start a private Xvfb (FEMM opens a hidden window)."""
    global _xvfb
    if sys.platform == "win32" or os.environ.get("DISPLAY"):
        return
    for n in range(91, 120):
        if not Path(f"/tmp/.X{n}-lock").exists():
            _xvfb = subprocess.Popen(["Xvfb", f":{n}", "-screen", "0", "1024x768x24", "-nolisten", "tcp"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            os.environ["DISPLAY"] = f":{n}"
            atexit.register(_stop_display)
            time.sleep(0.5)
            return
    raise RuntimeError("no free X display for Xvfb")


def _stop_display() -> None:
    """Stop the private Xvfb started by _ensure_display (at interpreter exit)."""
    global _xvfb
    if _xvfb is not None:
        _xvfb.terminate()
        _xvfb = None


def _exchange(femm, expr: str, timeout: float = 900.0) -> str:
    """Send one Lua expression to FEMM through pyfemm's file link and wait for its complete reply.

    pyfemm 0.1.3 on Linux can return before FEMM has answered (a stale or half-written ofile),
    so the next command overwrites the input file and is lost. Here: remove any stale reply, write
    the command atomically, wait for a reply that is non-empty and no longer growing, then delete it.
    On Windows pyfemm talks to FEMM through COM, which is synchronous.
    """
    if getattr(femm, "windowsOS", False):
        return str(femm.HandleToFEMM.mlab2femm(expr))
    ifile, ofile = Path(femm.ifile), Path(femm.ofile)
    ofile.unlink(missing_ok=True)
    tmp = ifile.with_suffix(".tmp")
    tmp.write_text(f"flput({expr})", encoding="ascii")
    os.replace(tmp, ifile)
    t0, last = time.monotonic(), None
    while True:
        if ofile.exists():
            text = ofile.read_text(errors="replace")
            if text.strip() and text == last:
                ofile.unlink(missing_ok=True)
                if text.lstrip().startswith("e"):
                    raise RuntimeError(f"FEMM : {text.strip()}")
                return text.strip()
            last = text
        if time.monotonic() - t0 > timeout:
            raise RuntimeError(f"FEMM did not answer within {timeout:.0f} s: {expr[:80]}")
        time.sleep(0.02)


def _dofile(femm, script: Path, text: str) -> None:
    """Run a Lua script inside FEMM and wait for it to finish."""
    script.write_text(text, encoding="ascii")
    _exchange(femm, f"dofile('{_femm_path(script)}')")


def _femm_path(p: Path) -> str:
    """Path as FEMM sees it (Wine maps / to Z:)."""
    s = str(p.resolve())
    return s.replace("\\", "/") if sys.platform == "win32" else "Z:" + s


# --- model ----------------------------------------------------------------------------

def _rot(x: float, y: float, a: float) -> tuple[float, float]:
    c, s = math.cos(a), math.sin(a)
    return x * c - y * s, x * s + y * c


def slot_angles(w: wd.Winding) -> np.ndarray:
    """Mechanical angle of each slot axis, rad (slot s at 2π·s/Z, as in core.winding)."""
    return 2.0 * math.pi * np.arange(w.z) / w.z


class LuaRecorder:
    """Records pyfemm-style calls as FEMM Lua lines, so the whole geometry is sent as one dofile.

    Each pyfemm call is a round trip to FEMM (a file exchange under Wine): ~1100 calls took 40 s.
    mi_drawline / mi_drawarc are pyfemm composites, expanded here into FEMM's Lua primitives.
    """

    def __init__(self) -> None:
        self.lines: list[str] = []

    def mi_drawline(self, x1, y1, x2, y2) -> None:
        self.mi_addnode(x1, y1)
        self.mi_addnode(x2, y2)
        self.mi_addsegment(x1, y1, x2, y2)

    def mi_drawarc(self, x1, y1, x2, y2, angle, maxseg) -> None:
        self.mi_addnode(x1, y1)
        self.mi_addnode(x2, y2)
        self.mi_addarc(x1, y1, x2, y2, angle, maxseg)

    def __getattr__(self, name: str):
        if not name.startswith(("mi_", "newdocument")):
            raise AttributeError(name)
        from femm import doargs

        def call(*args) -> None:
            self.lines.append(f"{name}{doargs(*args)}")

        return call

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


def _build(femm, case: FemCase, fem_file: Path) -> None:
    """Draw the model with `femm` (pyfemm or a LuaRecorder) and save it."""
    g, w = case.geometry, case.winding
    femm.newdocument(0)
    femm.mi_probdef(0, "millimeters", "planar", 1e-8, g.stack, 30)
    femm.mi_addmaterial("Air", 1, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0)
    femm.mi_addmaterial("Cu", 1, 1, 0, 0, 58, 0, 0, 1, 0, 0, 0)
    if case.material == "linear":
        femm.mi_addmaterial("Iron", 4000, 4000, 0, 0, 0, 0, 0, 1, 0, 0, 0)
        iron = "Iron"
    else:
        femm.mi_getmaterial(case.material)
        iron = case.material
    for ph in wd.PHASES:
        femm.mi_addcircprop(ph, 0, 1)
    femm.mi_addboundprop("A0", 0, 0, 0, 0, 0, 0, 0, 0, 0)

    r_open = g.r_bore + g.lip
    r_mid = r_open + g.slot_depth / 2.0
    r_bot = r_open + g.slot_depth
    xb = math.sqrt(g.r_bore**2 - (g.slot_opening / 2) ** 2)
    angles = slot_angles(w)
    bore_pts = []
    for a in angles:
        local = [(xb, -g.slot_opening / 2), (r_open, -g.slot_opening / 2), (r_open, -g.slot_width / 2),
                 (r_mid, -g.slot_width / 2), (r_bot, -g.slot_width / 2), (r_bot, g.slot_width / 2),
                 (r_mid, g.slot_width / 2), (r_open, g.slot_width / 2), (r_open, g.slot_opening / 2),
                 (xb, g.slot_opening / 2)]
        p = [_rot(x, y, a) for x, y in local]
        chain = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7), (7, 8), (8, 9),
                 (1, 8), (3, 6)]  # opening / body line, layer split line
        for i, j in chain:
            femm.mi_drawline(p[i][0], p[i][1], p[j][0], p[j][1])
        bore_pts.append((p[0], p[9]))
    span_open = math.degrees(2 * math.asin(g.slot_opening / 2 / g.r_bore))
    span_tooth = 360.0 / w.z - span_open
    for k, (p0, p9) in enumerate(bore_pts):
        femm.mi_drawarc(p0[0], p0[1], p9[0], p9[1], span_open, 1)
        q0 = bore_pts[(k + 1) % w.z][0]
        femm.mi_drawarc(p9[0], p9[1], q0[0], q0[1], span_tooth, 1)
    for r in (g.r_rotor, g.r_outer):
        femm.mi_drawarc(r, 0, -r, 0, 180, 1)
        femm.mi_drawarc(-r, 0, r, 0, 180, 1)
    femm.mi_selectarcsegment(0, g.r_outer)
    femm.mi_selectarcsegment(0, -g.r_outer)
    femm.mi_setarcsegmentprop(1, "A0", 0, 0)
    femm.mi_clearselected()

    def label(x, y, mat, circuit="<None>", turns=0, mesh=0.0):
        femm.mi_addblocklabel(x, y)
        femm.mi_selectlabel(x, y)
        femm.mi_setblockprop(mat, 0 if mesh else 1, mesh, circuit, 0, 0, turns)
        femm.mi_clearselected()


    table = wd.slot_table(w)
    for a, slot in zip(angles, table):
        for (ph, sign), r in ((slot.top, (r_open + r_mid) / 2), (slot.bottom, (r_mid + r_bot) / 2)):
            label(*_rot(r, 0.0, a), "Cu", ph, sign * case.turns_per_coil)
        label(*_rot(g.r_bore + g.lip / 2, 0.0, a), "Air")
    half = math.pi / w.z
    label(*_rot((r_bot + g.r_outer) / 2, 0.0, half), iron, mesh=0.0)
    label(*_rot(g.r_mid_gap, 0.0, half), "Air", mesh=g.gap / 3)
    label(0.0, 0.0, iron)
    femm.mi_saveas(_femm_path(fem_file))


def sample_points(case: FemCase) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(θ mid-gap in rad, r grid in mm, θ grid in rad, xy of every sampled point in mm, gap points first)."""
    g = case.geometry
    theta = 2.0 * math.pi * (np.arange(case.n_gap) + 0.5) / case.n_gap
    r_grid = np.linspace(g.r_rotor * 0.35, g.r_outer * 0.999, case.n_radial)
    th_grid = 2.0 * math.pi * np.arange(case.n_angular) / case.n_angular
    rr, tt = np.meshgrid(r_grid, th_grid, indexing="ij")
    xy = np.vstack([np.column_stack([g.r_mid_gap * np.cos(theta), g.r_mid_gap * np.sin(theta)]),
                    np.column_stack([(rr * np.cos(tt)).ravel(), (rr * np.sin(tt)).ravel()])])
    return theta, r_grid, th_grid, xy


def _lua_frame(currents: tuple[float, float, float], fem_path: str, check_path: str) -> str:
    """Lua for one frame: set the three circuit currents, save, solve, load, write back the solved currents.

    Sent as one dofile: separate pyfemm calls (a file exchange each under Wine) were sometimes lost.
    FEMM solves the model saved on disk, hence the save before mi_analyze.
    """
    lines = [f'mi_modifycircprop("{ph}",1,{i!r})' for ph, i in zip(wd.PHASES, currents)]
    lines += [f"mi_saveas('{fem_path}')", "mi_analyze(1)", "mi_loadsolution()",
              f"h=openfile('{check_path}','w')"]
    lines += [f'c,v,f=mo_getcircuitproperties("{ph}") write(h,c,"\\n")' for ph in wd.PHASES]
    lines += ["closefile(h)"]
    return "\n".join(lines) + "\n"


def _lua_sample(path_out: str, xy: np.ndarray) -> str:
    """Lua 4 for FEMM: B at every point of xy (mm), one "bx by" line per point.

    FEMM's Lua has mo_getpointvalues (A, Bx, By, …), not mo_getb (a pyfemm wrapper); no trigonometry
    in Lua (Lua 4 works in degrees).
    """
    pts = ",".join(f"{x:.6f},{y:.6f}" for x, y in xy)
    return (f"P={{{pts}}}\n"
            f"h=openfile('{path_out}','w')\n"
            f"for i=1,{2 * len(xy)},2 do a,bx,by=mo_getpointvalues(P[i],P[i+1]) write(h,bx,' ',by,'\\n') end\n"
            "closefile(h)\n")


def run(case: FemCase, out_dir: str | Path, progress: Callable[[int, int], None] | None = None,
        cancelled: Callable[[], bool] | None = None, frames_png: bool = True) -> FemResult:
    """Build the model once, solve n_frames magnetostatic cases over one period, sample and draw them."""
    ok, reason = femm_available()
    if not ok:
        raise RuntimeError(reason)
    import femm

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    _ensure_display()
    work = Path(tempfile.mkdtemp(prefix="evlab_femm_"))
    t_start = time.perf_counter()
    femm.openfemm(1)
    frames = []
    try:
        rec = LuaRecorder()
        _build(rec, case, work / "stator.fem")
        _dofile(femm, work / "geometry.lua", rec.text())
        theta, r_grid, th_grid, xy = sample_points(case)
        out_file = work / "b.txt"
        sample_lua = _lua_sample(_femm_path(out_file), xy)
        for k in range(case.n_frames):
            if cancelled is not None and cancelled():
                break
            t = k / (case.n_frames * case.frequency)
            wt = 2.0 * math.pi * case.frequency * t
            cur = tuple(case.current * math.cos(wt + wd.PHASE_SHIFT[ph]) for ph in wd.PHASES)
            check = work / "currents.txt"
            _dofile(femm, work / "frame.lua", _lua_frame(cur, _femm_path(work / "stator.fem"), _femm_path(check)))
            solved = np.loadtxt(check).ravel()
            if not np.allclose(solved, cur, rtol=1e-9, atol=1e-9 * case.current):
                raise RuntimeError(f"FEMM solved frame {k} with currents {solved} instead of {cur}")
            # pyfemm wraps every command in flput(...) on Linux, so the sampling loop is a Lua file
            _dofile(femm, work / "sample.lua", sample_lua + "mo_close()\n")
            b = np.loadtxt(out_file).reshape(-1, 2)
            bg, bm = b[: case.n_gap], b[case.n_gap:].reshape(case.n_radial, case.n_angular, 2)
            b_r = bg[:, 0] * np.cos(theta) + bg[:, 1] * np.sin(theta)
            frame = FemFrame(t, cur, theta, b_r, r_grid, th_grid, np.hypot(bm[..., 0], bm[..., 1]))
            if frames_png:
                frame = _with_png(frame, case, out / f"frame_{k:03d}.png")
            frames.append(frame)
            if progress is not None:
                progress(k + 1, case.n_frames)
    finally:
        femm.closefemm()
        shutil.rmtree(work, ignore_errors=True)
    return FemResult(case, tuple(frames), time.perf_counter() - t_start)


def _with_png(frame: FemFrame, case: FemCase, path: Path) -> FemFrame:
    from dataclasses import replace

    from evlab.io.figures import png_bytes
    from matplotlib.figure import Figure

    fig = Figure(figsize=(5.2, 4.6), layout="constrained")
    ax = fig.add_subplot(projection="polar")
    th, r = np.meshgrid(np.append(frame.th_grid, 2 * math.pi), frame.r_grid)
    b = np.concatenate([frame.b_mag, frame.b_mag[:, :1]], axis=1)
    mesh = ax.pcolormesh(th, r, b, cmap="inferno", vmin=0, vmax=2.0, shading="gouraud")
    ax.set_ylim(0, case.geometry.r_outer)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(f"|B| (T) — t = {frame.t * 1000:.2f} ms".replace(".", ","), fontsize=9)
    fig.colorbar(mesh, ax=ax, shrink=0.8, label="|B| (T)")
    path.write_bytes(png_bytes(fig, dpi=110))
    return replace(frame, png=path)


# --- comparison with the analytical MMF of tab 6 -----------------------------------------

FEMM_SIGN = -1.0  # FEMM's positive circuit current gives B_r of opposite sign to core.winding's MMF convention


@dataclass(frozen=True)
class Comparison:
    """FEM air-gap fundamental against μ0·F1/(k_c·g) (T); ratio = FEM / analytical with Carter."""

    b1_fem: float
    b1_fem_spread: float  # (max − min)/mean over the frames
    mmf1: float  # A·turns, three-phase fundamental at the peak current (core.winding)
    carter: float
    b1_smooth: float  # μ0·F1/g
    b1_carter: float  # μ0·F1/(k_c·g)
    ratio: float
    rotation_speed: float  # rad/s, mechanical, from the FEM frames
    expected_speed: float  # 2πf/p


def analytic_fields(result: FemResult) -> tuple[Comparison, np.ndarray]:
    """Comparison and the analytical fundamental B(θ) of every frame at the FEM sample angles (T)."""
    case, w, g = result.case, result.case.winding, result.case.geometry
    n_theta = w.z * 32
    rf = wd.rotating_field(w, case.frequency, case.current, n_theta, max(4, case.n_frames), case.turns_per_coil)
    mmf1 = float(rf.fundamental_amplitude.mean())
    kc = wd.carter_factor(g.slot_pitch(w.z) * 1e-3, g.slot_opening * 1e-3, g.gap * 1e-3)
    b_smooth = wd.gap_flux_density(mmf1, g.gap * 1e-3)
    b_carter = wd.gap_flux_density(mmf1, g.gap * 1e-3, kc)
    b1 = result.fundamental()
    p = w.pole_pairs
    curves = []
    for k, f in enumerate(result.frames):
        mmf = sum(i * np.interp(f.theta, rf.theta, wd.phase_mmf(w, ph, n_theta)[1], period=2 * math.pi)
                  for ph, i in zip(wd.PHASES, f.currents)) * case.turns_per_coil
        c = np.fft.rfft(mmf)[p] * 2.0 / mmf.size
        curves.append(FEMM_SIGN * wd.gap_flux_density(1.0, g.gap * 1e-3, kc) * abs(c)
                      * np.cos(p * f.theta + np.angle(c)))
    if len(result.frames) >= 2:
        pos = np.array([np.angle(np.fft.rfft(f.b_r)[p]) for f in result.frames])
        t = np.array([f.t for f in result.frames])
        speed = float(-np.polyfit(t, np.unwrap(pos), 1)[0] / p)
    else:
        speed = math.nan
    cmp = Comparison(float(b1.mean()), float(np.ptp(b1) / b1.mean()) if b1.size else math.nan, mmf1, kc,
                     b_smooth, b_carter, float(b1.mean() / b_carter), speed, 2 * math.pi * case.frequency / p)
    return cmp, np.array(curves)
