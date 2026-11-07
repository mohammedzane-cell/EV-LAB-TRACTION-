"""2-D FEMM model of the 36-slot, 4-pole stator with a simplified rotor (optional, needs pyfemm + FEMM 4.2).

Only used when pyfemm and FEMM 4.2 are installed (Windows: pyfemm's own calls; Linux:
FEMM under Wine with a display, e.g. Xvfb, through a robust file exchange). Everything
else in the application works without it, and saved runs (data/fem_cache/) can be
replayed without FEMM.

Model (docs/assumptions.md A32): planar magnetostatic; stator with semi-open
rectangular slots, two layers per slot; smooth solid iron rotor without bars
(magnetising field of the stator currents only); slot currents assigned from
core.winding.slot_table: the phase of each layer, sign ±, N_c turns; balanced
currents i_k(t) = I·cos(ωt − 2πk/3) stepped over one electrical period (I = peak).
Symmetry: the field at t + T/6 is the field at t turned by one phase belt (q slots,
π/(3p) mechanical) with the phases permuted A+ → C− → B+, so only t ∈ [0, T/6) is solved.
For each frame, a Lua loop inside FEMM samples B on a polar grid (|B| map) and
along a circle in the middle of the air gap (B_r(θ)); matplotlib draws the frames.
"""

from __future__ import annotations

import atexit
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np

from evlab.core import winding as wd
from evlab.io.paths import data_dir

MATERIALS = ("M-19 Steel", "linear")
CACHE_DIR = data_dir() / "fem_cache"
SQRT2 = math.sqrt(2.0)


def peak_from_rms(i_rms: float) -> float:
    """Peak value of a sinusoidal current, A: Î = √2·I_rms."""
    return SQRT2 * i_rms


def rms_from_peak(i_peak: float) -> float:
    """RMS value of a sinusoidal current, A: I_rms = Î/√2."""
    return i_peak / SQRT2


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
    current: float = 6.0  # PEAK phase current, A (balanced three-phase)
    frequency: float = 50.0  # Hz (only sets the time axis)
    n_frames: int = 12  # per electrical period
    material: str = "M-19 Steel"
    n_gap: int = 720  # samples along the mid-gap circle
    n_radial: int = 40  # |B| map grid
    n_angular: int = 240
    gap_layers: int = 3  # air-gap mesh size = gap / gap_layers

    def __post_init__(self) -> None:
        if self.material not in MATERIALS:
            raise ValueError(f"material must be one of {MATERIALS}, got {self.material!r}")
        for name in ("turns_per_coil", "n_frames", "n_gap", "n_radial", "n_angular", "gap_layers"):
            v = getattr(self, name)
            if not isinstance(v, int) or v < 1:
                raise ValueError(f"{name} must be an integer >= 1, got {v!r}")
        if not math.isfinite(self.current) or self.current <= 0:
            raise ValueError(f"current must be > 0 A, got {self.current!r}")

    @property
    def current_rms(self) -> float:
        """RMS phase current, A."""
        return rms_from_peak(self.current)

    @property
    def symmetry_step(self) -> int | None:
        """Frames per sixth of a period when n_frames is a multiple of 6 (symmetry usable), else None."""
        return self.n_frames // 6 if self.n_frames % 6 == 0 else None

    def frame_time(self, k: int) -> float:
        """Time of frame k, s."""
        return k / (self.n_frames * self.frequency)

    def currents(self, t: float) -> tuple[float, float, float]:
        """Phase currents i_A, i_B, i_C at time t, A."""
        wt = 2.0 * math.pi * self.frequency * t
        return tuple(self.current * math.cos(wt + wd.PHASE_SHIFT[ph]) for ph in wd.PHASES)


@dataclass(frozen=True)
class FemFrame:
    """One solved instant: currents, air-gap B_r(θ) and the |B| map (polar grid)."""

    t: float  # s
    currents: tuple[float, float, float]  # A, phases A, B, C
    theta: np.ndarray  # rad, mid-gap samples
    b_r: np.ndarray  # T, radial flux density in the middle of the gap
    r_grid: np.ndarray  # mm
    th_grid: np.ndarray  # rad
    b_mag: np.ndarray | None  # T, shape (n_radial, n_angular); None for a run loaded from the cache
    png: Path | None = None


@dataclass(frozen=True)
class FemResult:
    case: FemCase
    frames: tuple[FemFrame, ...]
    solve_seconds: float
    solved: tuple[int, ...] = ()  # frame indices solved by FEMM; the others come from the symmetry
    cached: bool = False  # loaded from data/fem_cache (pre-computed)

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
    """Linux/Wine only: send one Lua expression through pyfemm's file link and wait for its full reply.

    pyfemm 0.1.3 on Linux can return before FEMM has answered (a stale or half-written ofile),
    so the next command overwrites the input file and is lost. Here: remove any stale reply, write
    the command atomically, wait for a reply that is non-empty and no longer growing, then delete it.
    Not used on Windows, where pyfemm's own calls go through COM (synchronous).
    """
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


def lua_args(*args) -> str:
    """Lua argument list as pyfemm writes it (pyfemm's doargs): strings in double quotes, numbers by str(),
    complex j → *I. Local copy so that the model can be written without pyfemm installed."""
    parts = [f'"{a}"' if isinstance(a, str) else str(a).replace("j", "*I") for a in args]
    return "(" + ",".join(parts) + ")"


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

        def call(*args) -> None:
            self.lines.append(f"{name}{lua_args(*args)}")

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
    label(*_rot(g.r_mid_gap, 0.0, half), "Air", mesh=g.gap / case.gap_layers)
    label(0.0, 0.0, iron)
    femm.mi_saveas(_femm_path(fem_file))


def sample_points(case: FemCase) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(θ mid-gap in rad, r grid in mm, θ grid in rad, xy of every sampled point in mm, gap points first)."""
    g = case.geometry
    theta = 2.0 * math.pi * (np.arange(case.n_gap) + 0.5) / case.n_gap
    r_grid = np.linspace(g.r_rotor * 0.35, g.r_outer * 0.999, case.n_radial)
    th_grid = 2.0 * math.pi * (np.arange(case.n_angular) + 0.5) / case.n_angular  # off the slot axes
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


class _WineLink:
    """FEMM under Wine (Linux): whole scripts sent as dofile through the robust file exchange."""

    def __init__(self, femm, work: Path) -> None:
        self.femm, self.work = femm, work

    def build(self, case: FemCase, fem_file: Path) -> None:
        rec = LuaRecorder()
        _build(rec, case, fem_file)
        _dofile(self.femm, self.work / "geometry.lua", rec.text())

    def solve(self, currents: tuple[float, float, float], fem_file: Path) -> np.ndarray:
        check = self.work / "currents.txt"
        _dofile(self.femm, self.work / "frame.lua", _lua_frame(currents, _femm_path(fem_file), _femm_path(check)))
        return np.loadtxt(check).ravel()

    def sample(self, xy: np.ndarray) -> np.ndarray:
        out = self.work / "b.txt"
        # pyfemm wraps every command in flput(...) on Linux, so the sampling loop is a Lua file
        _dofile(self.femm, self.work / "sample.lua", _lua_sample(_femm_path(out), xy) + "mo_close()\n")
        return np.loadtxt(out).reshape(-1, 2)


class _NativeLink:
    """pyfemm's own calls (Windows: COM, synchronous)."""

    def __init__(self, femm, work: Path) -> None:
        self.femm = femm

    def build(self, case: FemCase, fem_file: Path) -> None:
        _build(self.femm, case, fem_file)

    def solve(self, currents: tuple[float, float, float], fem_file: Path) -> np.ndarray:
        f = self.femm
        for ph, i in zip(wd.PHASES, currents):
            f.mi_modifycircprop(ph, 1, i)
        f.mi_saveas(_femm_path(fem_file))  # FEMM solves the file saved on disk
        f.mi_analyze(1)
        f.mi_loadsolution()
        return np.array([complex(f.mo_getcircuitproperties(ph)[0]).real for ph in wd.PHASES])

    def sample(self, xy: np.ndarray) -> np.ndarray:
        b = np.array([self.femm.mo_getb(float(x), float(y)) for x, y in xy], dtype=float)
        self.femm.mo_close()
        return b.reshape(-1, 2)


def _native() -> bool:
    """pyfemm's own calls on Windows; the Wine file exchange elsewhere."""
    return sys.platform == "win32"


def _link(femm, work: Path):
    return _NativeLink(femm, work) if _native() else _WineLink(femm, work)


# --- symmetry ---------------------------------------------------------------------------

def solved_indices(case: FemCase) -> tuple[int, ...]:
    """Frames solved by FEMM: those with t in [0, T/6) when n_frames is a multiple of 6, else all."""
    step = case.symmetry_step
    return tuple(range(step if step is not None else case.n_frames))


def _shift(values: np.ndarray, grid: np.ndarray, angle: float) -> np.ndarray:
    """values(θ − angle) on the same uniform periodic θ grid (last axis): the pattern turned by +angle."""
    n = grid.size
    s = angle / (2.0 * math.pi / n)
    if abs(s - round(s)) < 1e-9:
        return np.roll(values, int(round(s)), axis=-1)
    flat = np.atleast_2d(values)
    out = np.array([np.interp(grid - angle, grid, row, period=2.0 * math.pi) for row in flat])
    return out.reshape(values.shape)


def rotate_frame(frame: FemFrame, case: FemCase, sixths: int) -> FemFrame:
    """Frame at t + sixths·T/6 derived from `frame`: B turned by sixths·π/(3p) mechanical (q slots).

    Slot s + q carries belt b + 1 (A+ → C− → B+ → A− → C+ → B−) and i_A(t + T/6) = −i_B(t),
    i_B(t + T/6) = −i_C(t), i_C(t + T/6) = −i_A(t): the current pattern, hence B, turns by q slots.
    """
    angle = sixths * math.pi / (3.0 * case.winding.pole_pairs)
    t = frame.t + sixths / (6.0 * case.frequency)
    b_mag = None if frame.b_mag is None else _shift(frame.b_mag, frame.th_grid, angle)
    return FemFrame(t, case.currents(t), frame.theta, _shift(frame.b_r, frame.theta, angle),
                    frame.r_grid, frame.th_grid, b_mag)


def run(case: FemCase, out_dir: str | Path, progress: Callable[[int, int], None] | None = None,
        cancelled: Callable[[], bool] | None = None, frames_png: bool = True,
        solve: tuple[int, ...] | None = None) -> FemResult:
    """Build the model once, solve the frames of [0, T/6) (or `solve`), derive the others by symmetry.

    progress(k, n) counts the frames solved by FEMM. `solve` forces frames to be solved directly
    (e.g. to check the symmetry); every other frame must be derivable from one of them.
    """
    base = solved_indices(case) if solve is None else tuple(sorted(set(solve)))
    step = case.symmetry_step
    if any(not 0 <= k < case.n_frames for k in base):
        raise ValueError(f"solve indices must be in [0, {case.n_frames}), got {base}")
    missing = [k for k in range(case.n_frames) if k not in base and (step is None or k % step not in base)]
    if missing:
        raise ValueError(f"frames {missing} are neither solved nor derivable by symmetry")
    ok, reason = femm_available()
    if not ok:
        raise RuntimeError(reason)
    import femm

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    _ensure_display()
    work = Path(tempfile.mkdtemp(prefix="evlab_femm_"))
    fem_file = work / "stator.fem"
    t_start = time.perf_counter()
    femm.openfemm(1)
    solved: dict[int, FemFrame] = {}
    try:
        link = _link(femm, work)
        link.build(case, fem_file)
        theta, r_grid, th_grid, xy = sample_points(case)
        for n_done, k in enumerate(base):
            if cancelled is not None and cancelled():
                break
            t = case.frame_time(k)
            cur = case.currents(t)
            got = link.solve(cur, fem_file)
            if not np.allclose(got, cur, rtol=1e-9, atol=1e-9 * case.current):
                raise RuntimeError(f"FEMM solved frame {k} with currents {got} instead of {cur}")
            b = link.sample(xy)
            bg, bm = b[: case.n_gap], b[case.n_gap:].reshape(case.n_radial, case.n_angular, 2)
            b_r = bg[:, 0] * np.cos(theta) + bg[:, 1] * np.sin(theta)
            solved[k] = FemFrame(t, cur, theta, b_r, r_grid, th_grid, np.hypot(bm[..., 0], bm[..., 1]))
            if progress is not None:
                progress(n_done + 1, len(base))
    finally:
        femm.closefemm()
        shutil.rmtree(work, ignore_errors=True)
    complete = len(solved) == len(base)
    frames = []
    for k in range(case.n_frames) if complete else sorted(solved):
        frame = solved[k] if k in solved else rotate_frame(solved[k % step], case, k // step)
        if frames_png:
            frame = _with_png(frame, case, out / f"frame_{k:03d}.png")
        frames.append(frame)
    return FemResult(case, tuple(frames), time.perf_counter() - t_start, tuple(sorted(solved)))


def _with_png(frame: FemFrame, case: FemCase, path: Path) -> FemFrame:
    from evlab.io.figures import png_bytes
    from matplotlib.figure import Figure

    fig = Figure(figsize=(5.2, 4.6), layout="constrained")
    ax = fig.add_subplot(projection="polar")
    th, r = np.meshgrid(np.append(frame.th_grid, frame.th_grid[0] + 2 * math.pi), frame.r_grid)
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


# --- cache of solved runs (data/fem_cache) -----------------------------------------------

def cache_key(case: FemCase) -> str:
    """Folder name of a run: iron, peak current, turns per coil, coil pitch, frames."""
    iron = "m19" if case.material == "M-19 Steel" else "lineaire"
    mesh = "" if case.gap_layers == 3 else f"_g{case.gap_layers}"
    return f"{iron}_{case.current:.4g}A_{case.turns_per_coil}sp_y{case.winding.y}_{case.n_frames}im{mesh}"


def _case_dict(case: FemCase) -> dict:
    w = case.winding
    return {"winding": {"z": w.z, "poles": w.poles, "m": w.m, "y": w.y}, "geometry": asdict(case.geometry),
            "turns_per_coil": case.turns_per_coil, "current_peak": case.current, "frequency": case.frequency,
            "n_frames": case.n_frames, "material": case.material, "n_gap": case.n_gap,
            "n_radial": case.n_radial, "n_angular": case.n_angular, "gap_layers": case.gap_layers}


def _case_from(d: dict) -> FemCase:
    return FemCase(winding=wd.Winding(**d["winding"]), geometry=StatorGeometry(**d["geometry"]),
                   turns_per_coil=d["turns_per_coil"], current=d["current_peak"], frequency=d["frequency"],
                   n_frames=d["n_frames"], material=d["material"], n_gap=d["n_gap"],
                   n_radial=d["n_radial"], n_angular=d["n_angular"], gap_layers=d.get("gap_layers", 3))


def save_cache(result: FemResult, root: str | Path | None = None) -> Path:
    """Write a run to root/<cache_key>/: frame PNGs, b_r_demo.csv (θ and B_r per frame) and meta.json."""
    if not result.frames:
        raise ValueError("no frame to save")
    folder = Path(root if root is not None else CACHE_DIR) / cache_key(result.case)
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    frames_meta = []
    for k, f in enumerate(result.frames):
        png = None
        if f.png is not None and Path(f.png).exists():
            png = f"frame_{k:03d}.png"
            shutil.copyfile(f.png, folder / png)
        frames_meta.append({"t_s": f.t, "currents_A": list(f.currents), "png": png})
    theta = result.frames[0].theta
    cols = np.column_stack([theta] + [f.b_r for f in result.frames])
    header = ",".join(["theta [rad]"] + [f"B_r frame_{k:03d} [T]" for k in range(len(result.frames))])
    np.savetxt(folder / "b_r_demo.csv", cols, delimiter=",", header=header, comments="", fmt="%.17g")
    meta = {"program": "FEMM 4.2", "demo": True, "note": "géométrie démo (A32), rotor lisse sans barres",
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "solve_seconds": result.solve_seconds, "solved": list(result.solved),
            "case": _case_dict(result.case), "frames": frames_meta}
    (folder / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    return folder


def load_cache(folder: str | Path) -> FemResult:
    """Read a run written by save_cache (b_mag is not stored: the |B| maps are the PNG frames)."""
    folder = Path(folder)
    try:
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        case = _case_from(meta["case"])
        data = np.loadtxt(folder / "b_r_demo.csv", delimiter=",", skiprows=1, ndmin=2)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"cache FEM illisible ({folder.name}) : {exc}") from exc
    if data.shape[1] != len(meta["frames"]) + 1 or data.shape[0] != case.n_gap:
        raise ValueError(f"cache FEM incohérent ({folder.name}) : {data.shape} pour {len(meta['frames'])} images")
    _, r_grid, th_grid, _ = sample_points(case)
    frames = tuple(FemFrame(fm["t_s"], tuple(fm["currents_A"]), data[:, 0], data[:, k + 1], r_grid, th_grid, None,
                            folder / fm["png"] if fm["png"] else None)
                   for k, fm in enumerate(meta["frames"]))
    return FemResult(case, frames, float(meta["solve_seconds"]), tuple(meta["solved"]), cached=True)


def cached_runs(root: str | Path | None = None) -> list[Path]:
    """Folders of saved runs under root (default data/fem_cache), sorted by name."""
    root = Path(root if root is not None else CACHE_DIR)
    return sorted(p.parent for p in root.glob("*/meta.json")) if root.is_dir() else []


def find_cache(case: FemCase, root: str | Path | None = None) -> Path | None:
    """Saved run with exactly this case, or None."""
    for folder in cached_runs(root):
        if folder.name == cache_key(case):
            try:
                if load_cache(folder).case == case:
                    return folder
            except ValueError:
                return None
    return None
