"""3D scenes of the motor and of the powertrain, and the playback of a simulated cycle on them. No Qt.

Two different kinds of content live here and are kept apart:

1. Geometry — ILLUSTRATIVE. The meshes are procedural. What comes from the models: the slot count Z, the
   pole count 2p, the coil pitch y and the phase and layer of every coil side (core.winding.slot_table, tab 6);
   the wheel radius and the overall gear ratio (core.vehicle, tab 4). Every length in metres (bore, stack,
   yoke, housing, bearings, chassis…) is a typical proportion of a ≈ 5 kW four-pole motor and of a light
   quadricycle (docs/assumptions.md A37), NOT the dimensions of the identified motor: the Γ circuit carries no
   geometry. The air gap is drawn enlarged, the rotor bar count is a usual combination for Z (A37).
2. Playback — CALCULATED. What the scene shows while a cycle plays is read from the simulations:
   rotor angle θm = ∫ωm dt and wheel angle θw = ∫v/r dt of the vehicle result (θm = G·θw), the power of each
   link of the chain (battery, drive DC input, shaft, wheels, friction brakes), the battery SOC (core.battery)
   and the winding and iron/frame temperatures of the lumped two-node model (core.thermal) — one average value
   per node, never a spatial temperature field.

Meshes are indexed triangle lists: positions (N, 3) in m, unit normals (N, 3), indices (M, 3); faces are
counter-clockwise seen from outside, normals outward. Angles in rad, powers in W, temperatures in K.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import ArrayLike

from evlab.core import battery as battery_mod
from evlab.core import losses as losses_mod
from evlab.core import thermal as thermal_mod
from evlab.core import vehicle as vehicle_mod
from evlab.core import winding as winding_mod

TWO_PI = 2.0 * math.pi
PHASE_INDEX = {"A": 0, "B": 1, "C": 2}


def _pos(name: str, x: float) -> None:
    if not isinstance(x, (int, float, np.floating, np.integer)) or not math.isfinite(x) or x <= 0:
        raise ValueError(f"{name} must be a finite number > 0, got {x!r}")


# --- meshes -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Mesh:
    """Indexed triangle mesh (SI: m)."""

    positions: np.ndarray
    normals: np.ndarray
    indices: np.ndarray

    def __post_init__(self) -> None:
        p, n, i = self.positions, self.normals, self.indices
        if p.ndim != 2 or p.shape[1] != 3 or n.shape != p.shape:
            raise ValueError("positions and normals must be (N, 3) arrays of the same shape")
        if i.ndim != 2 or i.shape[1] != 3 or (i.size and (i.min() < 0 or i.max() >= len(p))):
            raise ValueError("indices must be an (M, 3) array of vertex numbers")

    @property
    def n_triangles(self) -> int:
        return len(self.indices)

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        """(min, max) corners of the bounding box, m."""
        return self.positions.min(axis=0), self.positions.max(axis=0)

    def volume(self) -> float:
        """Enclosed volume by the divergence theorem, Σ a·(b × c)/6, m³ (> 0 for outward faces)."""
        a, b, c = (self.positions[self.indices[:, k]] for k in range(3))
        return float(np.sum(np.einsum("ij,ij->i", a, np.cross(b, c)))) / 6.0

    def transformed(self, rotation: np.ndarray | None = None, translation: ArrayLike = (0.0, 0.0, 0.0)) -> "Mesh":
        """Rotated (3×3 matrix, about the origin) then translated copy."""
        r = np.eye(3) if rotation is None else np.asarray(rotation, dtype=float)
        return Mesh(self.positions @ r.T + np.asarray(translation, dtype=float), self.normals @ r.T,
                    self.indices.copy())


def merge(meshes: list[Mesh]) -> Mesh:
    """One mesh made of several (vertex numbers renumbered)."""
    if not meshes:
        raise ValueError("nothing to merge")
    offsets = np.cumsum([0] + [len(m.positions) for m in meshes[:-1]])
    return Mesh(np.vstack([m.positions for m in meshes]), np.vstack([m.normals for m in meshes]),
                np.vstack([m.indices + o for m, o in zip(meshes, offsets)]))


def rotation(axis: str, angle: float) -> np.ndarray:
    """Rotation matrix about x, y or z by angle (rad, right-hand rule)."""
    c, s = math.cos(angle), math.sin(angle)
    if axis == "x":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=float)
    if axis == "y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=float)
    if axis == "z":
        return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=float)
    raise ValueError(f"axis must be 'x', 'y' or 'z', got {axis!r}")


def rotation_from_z(direction: ArrayLike) -> np.ndarray:
    """Rotation that maps the z axis onto a direction (Rodrigues formula)."""
    d = np.asarray(direction, dtype=float)
    norm = float(np.linalg.norm(d))
    if not math.isfinite(norm) or norm == 0:
        raise ValueError("direction must be a finite non-zero vector")
    d = d / norm
    z = np.array([0.0, 0.0, 1.0])
    v, c = np.cross(z, d), float(np.dot(z, d))
    if np.linalg.norm(v) < 1e-12:
        return np.eye(3) if c > 0 else rotation("x", math.pi)
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + k + k @ k / (1.0 + c)


class _Builder:
    """Accumulates flat or smooth quads and triangles into one mesh."""

    def __init__(self) -> None:
        self.p: list[np.ndarray] = []
        self.n: list[np.ndarray] = []
        self.i: list[np.ndarray] = []
        self.count = 0

    def add(self, pos: np.ndarray, nrm: np.ndarray, tri: np.ndarray) -> None:
        self.p.append(pos)
        self.n.append(nrm)
        self.i.append(tri + self.count)
        self.count += len(pos)

    def mesh(self) -> Mesh:
        return Mesh(np.vstack(self.p), np.vstack(self.n), np.vstack(self.i).astype(np.int64))


def _strip(a: np.ndarray, b: np.ndarray, na: np.ndarray, nb: np.ndarray) -> tuple:
    """Quads between two vertex rows a[k], b[k] (k = 0…n): triangles (a_k, a_k+1, b_k+1), (a_k, b_k+1, b_k)."""
    n = len(a) - 1
    pos = np.vstack([a, b])
    nrm = np.vstack([na, nb])
    k = np.arange(n)
    tri = np.concatenate([np.stack([k, k + 1, n + 1 + k + 1], 1), np.stack([k, n + 1 + k + 1, n + 1 + k], 1)])
    return pos, nrm, tri


def annular_sector(r_in: float, r_out: float, z0: float, z1: float, theta0: float = 0.0,
                   span: float = TWO_PI, n_seg: int | None = None) -> Mesh:
    """Closed solid between radii r_in < r_out (r_in = 0: a full cylinder sector), z0 < z1 and angles
    θ0 … θ0 + span (0 < span ≤ 2π), axis z; curved faces with smooth normals, flat caps."""
    if not (math.isfinite(r_in) and r_in >= 0):
        raise ValueError(f"r_in must be >= 0, got {r_in!r}")
    _pos("r_out - r_in", r_out - r_in)
    _pos("z1 - z0", z1 - z0)
    if not (math.isfinite(span) and 0 < span <= TWO_PI + 1e-12):
        raise ValueError(f"span must be in (0, 2π], got {span!r}")
    if n_seg is None:
        n_seg = max(1, math.ceil(span / (TWO_PI / 96)))
    full = span >= TWO_PI - 1e-12
    th = theta0 + np.linspace(0.0, span, n_seg + 1)
    c, s = np.cos(th), np.sin(th)
    radial = np.stack([c, s, np.zeros_like(c)], 1)
    b = _Builder()

    def ring(r: float, z: float) -> np.ndarray:
        return np.stack([r * c, r * s, np.full_like(c, z)], 1)

    # outer face (normal +radial): rows z0 then z1
    b.add(*_strip(ring(r_out, z0), ring(r_out, z1), radial, radial))
    if r_in > 0:  # inner face (normal −radial): rows z1 then z0 reverse the winding
        b.add(*_strip(ring(r_in, z1), ring(r_in, z0), -radial, -radial))
    down, up = np.tile([0.0, 0.0, -1.0], (n_seg + 1, 1)), np.tile([0.0, 0.0, 1.0], (n_seg + 1, 1))
    if r_in > 0:
        b.add(*_strip(ring(r_in, z0), ring(r_out, z0), down, down))  # cap z0, normal −z
        b.add(*_strip(ring(r_out, z1), ring(r_in, z1), up, up))  # cap z1, normal +z
    else:  # fans around the axis
        k = np.arange(n_seg)
        for z, nz, order in ((z0, down, (0, 2, 1)), (z1, up, (0, 1, 2))):
            pos = np.vstack([[0.0, 0.0, z], ring(r_out, z)])
            nrm = np.vstack([nz[:1], nz])
            tri = np.stack([np.zeros(n_seg, int), 1 + k, 2 + k], 1)[:, order]
            b.add(pos, nrm, tri)
    if not full:  # flat radial faces at both ends of the angular span
        for ang, sign in ((th[0], -1.0), (th[-1], 1.0)):
            ca, sa = math.cos(ang), math.sin(ang)
            nrm = sign * np.array([-sa, ca, 0.0])
            pts = np.array([[r_in * ca, r_in * sa, z0], [r_out * ca, r_out * sa, z0],
                            [r_out * ca, r_out * sa, z1], [r_in * ca, r_in * sa, z1]])
            tri = np.array([[0, 1, 2], [0, 2, 3]]) if sign < 0 else np.array([[0, 2, 1], [0, 3, 2]])
            b.add(pts, np.tile(nrm, (4, 1)), tri)
    return b.mesh()


def sector_volume(r_in: float, r_out: float, length: float, span: float, n_seg: int) -> float:
    """Exact volume of the polygonal annular sector built by annular_sector, m³."""
    dth = span / n_seg
    return n_seg * 0.5 * math.sin(dth) * (r_out**2 - r_in**2) * length


def box(center: ArrayLike, size: ArrayLike) -> Mesh:
    """Axis-aligned box (flat faces), m."""
    c, h = np.asarray(center, dtype=float), 0.5 * np.asarray(size, dtype=float)
    if c.shape != (3,) or h.shape != (3,) or np.any(h <= 0) or not np.all(np.isfinite(h)):
        raise ValueError("box needs a 3-D centre and a size > 0 in every direction")
    b = _Builder()
    for axis in range(3):
        for sign in (-1.0, 1.0):
            u, v = [a for a in range(3) if a != axis]
            if sign < 0:
                u, v = v, u
            corners = []
            for du, dv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                p = c.copy()
                p[axis] += sign * h[axis]
                p[u] += du * h[u]
                p[v] += dv * h[v]
                corners.append(p)
            nrm = np.zeros(3)
            nrm[axis] = sign
            pts = np.array(corners)
            tri = np.array([[0, 1, 2], [0, 2, 3]])
            # orientation from the geometry: keep outward
            if np.dot(np.cross(pts[1] - pts[0], pts[2] - pts[0]), nrm) < 0:
                tri = tri[:, [0, 2, 1]]
            b.add(pts, np.tile(nrm, (4, 1)), tri)
    return b.mesh()


def cylinder_between(p0: ArrayLike, p1: ArrayLike, radius: float, n_seg: int = 20) -> Mesh:
    """Solid cylinder of a radius (m) from point p0 to point p1."""
    a, b = np.asarray(p0, dtype=float), np.asarray(p1, dtype=float)
    length = float(np.linalg.norm(b - a))
    _pos("cylinder length", length)
    return annular_sector(0.0, radius, 0.0, length, 0.0, TWO_PI, n_seg).transformed(rotation_from_z(b - a), a)


def sphere(center: ArrayLike, radius: float, n_lat: int = 8, n_lon: int = 12) -> Mesh:
    """UV sphere (smooth normals), m."""
    _pos("radius", radius)
    c = np.asarray(center, dtype=float)
    lat = np.linspace(0.0, math.pi, n_lat + 1)
    lon = np.linspace(0.0, TWO_PI, n_lon + 1)
    la, lo = np.meshgrid(lat, lon, indexing="ij")
    nrm = np.stack([np.sin(la) * np.cos(lo), np.sin(la) * np.sin(lo), np.cos(la)], -1).reshape(-1, 3)
    pos = c + radius * nrm
    tris = []
    w = n_lon + 1
    for i in range(n_lat):
        for j in range(n_lon):
            a, b_, cc, d = i * w + j, (i + 1) * w + j, (i + 1) * w + j + 1, i * w + j + 1
            if i > 0:
                tris.append((a, d, b_))
            if i < n_lat - 1:
                tris.append((d, cc, b_))
    tri = np.array(tris, dtype=np.int64)
    # outward orientation (checked against the normals)
    p = pos[tri]
    face = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    flip = np.einsum("ij,ij->i", face, nrm[tri].mean(axis=1)) < 0
    tri[flip] = tri[flip][:, [0, 2, 1]]
    return Mesh(pos, nrm, tri)


def _subtract(theta0: float, span: float, cut: tuple[float, float] | None) -> list[tuple[float, float]]:
    """Angular pieces (start, span) of [θ0, θ0 + span] outside the cut [c0, c0 + width] (angles mod 2π)."""
    if cut is None:
        return [(theta0, span)]
    c0, width = cut
    pieces = [(theta0, theta0 + span)]
    for k in range(-2, 3):
        a, b = c0 + k * TWO_PI, c0 + width + k * TWO_PI
        nxt = []
        for lo, hi in pieces:
            if b <= lo or a >= hi:
                nxt.append((lo, hi))
                continue
            if a > lo:
                nxt.append((lo, a))
            if b < hi:
                nxt.append((b, hi))
        pieces = nxt
    return [(lo, hi - lo) for lo, hi in pieces if hi - lo > 1e-9]


def _sectors(r_in: float, r_out: float, z0: float, z1: float, theta0: float, span: float,
             cut: tuple[float, float] | None, n_seg: int | None = None) -> list[Mesh]:
    out = []
    for a, w in _subtract(theta0, span, cut):
        n = None if n_seg is None else max(1, round(n_seg * w / span))
        out.append(annular_sector(r_in, r_out, z0, z1, a, w, n))
    return out


# --- motor ------------------------------------------------------------------------------------


def rotor_bar_count(n_slots: int, pole_pairs: int) -> int:
    """Illustrative rotor bar count: the even number nearest 0.8·Z that avoids the usual forbidden
    stator/rotor slot combinations (A37): N_r ≠ Z and |Z − N_r| ∉ {1, 2, p, 2p, 2p ± 1, 2p ± 2}
    (synchronous cusps at standstill, vibration and noise). 36 slots, 4 poles → 28."""
    if not isinstance(n_slots, int) or n_slots < 6 or not isinstance(pole_pairs, int) or pole_pairs < 1:
        raise ValueError(f"need an integer slot count >= 6 and pole pairs >= 1, got {n_slots!r}, {pole_pairs!r}")
    p = pole_pairs
    forbidden = {0, 1, 2, p, 2 * p, 2 * p - 1, 2 * p + 1, 2 * p - 2, 2 * p + 2}
    start = 2 * round(0.4 * n_slots)
    for d in range(0, n_slots):
        for n in (start - 2 * d, start + 2 * d):
            if n >= 8 and abs(n_slots - n) not in forbidden:
                return n
    raise ValueError(f"no rotor bar count found for Z = {n_slots}, p = {p}")  # pragma: no cover


@dataclass(frozen=True)
class MotorGeometry:
    """Illustrative motor dimensions (A37), m. Z, 2p and y come from the winding; N_r from rotor_bar_count."""

    n_slots: int
    poles: int
    coil_pitch: int
    n_bars: int
    r_out: float = 0.105  # stator outer radius
    r_bore: float = 0.068  # stator bore radius
    slot_depth: float = 0.020
    tooth_fraction: float = 0.45  # tooth body / slot pitch
    tip_depth: float = 0.0015
    opening_fraction: float = 0.25  # slot opening / slot pitch
    gap: float = 0.0015  # air gap as drawn (a real ≈ 5 kW motor: ≈ 0,4 mm)
    stack: float = 0.140  # core length
    r_shaft: float = 0.019
    bar_depth: float = 0.014
    bar_fraction: float = 0.55  # bar / rotor slot pitch
    ring_axial: float = 0.012  # end-ring thickness
    overhang: float = 0.045  # end-winding room beyond the core
    housing: float = 0.008  # housing wall
    fin_height: float = 0.014
    n_fins: int = 20
    is_illustrative: bool = True

    def __post_init__(self) -> None:
        for name in ("r_out", "r_bore", "slot_depth", "tip_depth", "gap", "stack", "r_shaft", "bar_depth",
                     "ring_axial", "overhang", "housing", "fin_height"):
            _pos(name, getattr(self, name))
        if self.r_bore + self.slot_depth >= self.r_out:
            raise ValueError("the slots must leave a stator yoke: r_bore + slot_depth < r_out")
        if self.r_shaft >= self.r_rotor - self.bar_depth:
            raise ValueError("the rotor bars must leave room for the shaft")
        for name in ("tooth_fraction", "opening_fraction", "bar_fraction"):
            if not 0 < getattr(self, name) < 1:
                raise ValueError(f"{name} must be in (0, 1)")

    @property
    def r_rotor(self) -> float:
        return self.r_bore - self.gap

    @property
    def r_yoke(self) -> float:
        return self.r_bore + self.slot_depth

    @property
    def r_housing(self) -> float:
        return self.r_out + self.housing

    @property
    def half_length(self) -> float:
        """Half length of the housing, m."""
        return 0.5 * self.stack + self.overhang + 0.004

    @property
    def slot_pitch(self) -> float:
        return TWO_PI / self.n_slots

    def slot_angle(self, s: int) -> float:
        """Centre angle of slot s (rad); slot 0 centred on the x axis."""
        return s * self.slot_pitch


def illustrative_geometry(w: winding_mod.Winding) -> MotorGeometry:
    """Illustrative motor for a winding: Z, 2p, y from it, N_r from rotor_bar_count, the rest A37."""
    return MotorGeometry(n_slots=w.z, poles=w.poles, coil_pitch=w.y, n_bars=rotor_bar_count(w.z, w.pole_pairs))


def layer_radii(g: MotorGeometry) -> dict[str, tuple[float, float]]:
    """Radial extent (m) of the two coil-side layers in a slot: "top" (towards the air gap) and "bottom"."""
    r_lo, r_hi = g.r_bore + g.tip_depth + 0.0008, g.r_yoke - 0.0008
    r_mid = 0.5 * (r_lo + r_hi)
    return {"top": (r_lo, r_mid - 0.0004), "bottom": (r_mid + 0.0004, r_hi)}


# angular sector removed by the cutaway view (stationary parts only; the rotor stays whole)
CUT_START = math.radians(-45.0)
CUT_WIDTH = math.radians(90.0)


@dataclass(frozen=True)
class Part:
    """One selectable component of a scene.

    key: identifier (the GUI names it).  group: visibility group.  material: colour role.
    mesh: geometry relative to origin, m.  origin: position of the part's pivot, m.
    axis: rotation axis through the origin ("x" or "z").  spin: which simulated angle turns it
    ("motor", "intermediate", "wheel" or None).  explode: displacement at full explosion, m.
    anchor: label anchor relative to origin, m.  facts: numbers attached to the part (SI).
    """

    key: str
    group: str
    material: str
    mesh: Mesh
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    axis: str = "z"
    spin: str | None = None
    explode: tuple[float, float, float] = (0.0, 0.0, 0.0)
    anchor: tuple[float, float, float] = (0.0, 0.0, 0.0)
    facts: dict[str, float] = field(default_factory=dict)


def motor_parts(g: MotorGeometry, w: winding_mod.Winding, cutaway: bool = False) -> list[Part]:
    """Components of the motor (axis z, drive end towards +z).

    Stationary parts lose the sector [CUT_START, CUT_START + CUT_WIDTH] in the cutaway view; the rotor,
    the cage and the shaft stay whole (they turn).
    """
    if (w.z, w.poles, w.y) != (g.n_slots, g.poles, g.coil_pitch):
        raise ValueError("the geometry and the winding disagree on Z, 2p or y")
    cut = (CUT_START, CUT_WIDTH) if cutaway else None
    half = 0.5 * g.stack
    pitch = g.slot_pitch
    parts: list[Part] = []

    # housing with fins, feet and the terminal box; end shields
    hz = g.half_length
    housing = _sectors(g.r_out, g.r_housing, -hz, hz, 0.0, TWO_PI, cut)
    fin_span = 0.004 / g.r_housing
    for k in range(g.n_fins):
        a = (k + 0.5) * TWO_PI / g.n_fins
        if abs(((a - math.pi / 2) + math.pi) % TWO_PI - math.pi) < math.radians(24):
            continue  # room for the terminal box
        housing += _sectors(g.r_housing - 1e-4, g.r_housing + g.fin_height, -hz + 0.01, hz - 0.01,
                            a - fin_span / 2, fin_span, cut, 1)
    foot_y = -(g.r_housing + g.fin_height)
    for x in (-0.07, 0.07):
        housing.append(box((x, foot_y - 0.006, 0.0), (0.04, 0.012, 2 * hz - 0.04)))
    parts.append(Part("housing", "housing", "housing", merge(housing),
                      anchor=(0.0, -g.r_housing * 0.7, hz * 0.6), explode=(0.0, 0.0, -0.26),
                      facts={"r_out": g.r_housing, "length": 2 * hz}))
    tb_y = g.r_housing + 0.024
    parts.append(Part("terminal_box", "housing", "housing_dark",
                      merge([box((0.0, tb_y, 0.02), (0.09, 0.05, 0.10)),
                             box((0.0, tb_y + 0.028, 0.02), (0.095, 0.006, 0.105))]),
                      anchor=(0.0, tb_y + 0.035, 0.02), explode=(0.0, 0.10, -0.26)))
    r_hub = 0.036
    for name, sign, ex in (("shield_front", 1.0, 0.45), ("shield_back", -1.0, -0.40)):
        z_a, z_b = sorted((sign * hz, sign * (hz + 0.012)))
        hub_a, hub_b = sorted((sign * (hz - 0.004), sign * (hz + 0.016)))
        m = _sectors(r_hub, g.r_housing, z_a, z_b, 0.0, TWO_PI, cut)
        m += _sectors(r_hub, r_hub + 0.010, hub_a, hub_b, 0.0, TWO_PI, cut)
        parts.append(Part(name, "housing", "housing", merge(m), explode=(0.0, 0.0, ex),
                          anchor=(0.0, g.r_housing * 0.75, sign * (hz + 0.012))))

    # stator core: yoke, teeth and tooth tips
    tooth = g.tooth_fraction * pitch
    tip = (1.0 - g.opening_fraction) * pitch
    core = _sectors(g.r_yoke, g.r_out, -half, half, 0.0, TWO_PI, cut)
    for s in range(g.n_slots):
        a = g.slot_angle(s) + 0.5 * pitch  # tooth between slots s and s + 1
        core += _sectors(g.r_bore + g.tip_depth - 1e-4, g.r_yoke + 1e-4, -half, half, a - tooth / 2, tooth, cut, 2)
        core += _sectors(g.r_bore, g.r_bore + g.tip_depth, -half, half, a - tip / 2, tip, cut, 2)
    parts.append(Part("stator_core", "stator", "steel", merge(core),
                      anchor=(0.0, g.r_out * 0.95, half * 0.2),
                      facts={"n_slots": g.n_slots, "r_bore": g.r_bore, "stack": g.stack}))

    # winding: coil sides (two layers) and end turns, one part per phase
    table = winding_mod.slot_table(w)
    side_span = 0.82 * (pitch - tooth)
    layers = layer_radii(g)
    r_lo, r_hi = layers["top"][0], layers["bottom"][1]
    r_mid = 0.5 * (r_lo + r_hi)
    ext = 0.006
    plane = {ph: half + ext + 0.004 + 0.009 * i for ph, i in PHASE_INDEX.items()}  # end-turn planes per phase
    thick = 0.007
    pieces: dict[str, list[Mesh]] = {ph: [] for ph in PHASE_INDEX}
    counts = {ph: 0 for ph in PHASE_INDEX}
    for s, slot in enumerate(table):
        a = g.slot_angle(s)
        for layer, (ph, _sign) in (("top", slot.top), ("bottom", slot.bottom)):
            r0, r1 = layers[layer]
            zl = plane[ph] + thick
            pieces[ph] += _sectors(r0, r1, -zl, zl, a - side_span / 2, side_span, cut, 2)
            counts[ph] += 1
    for c in range(g.n_slots):  # coil c: top layer of slot c → bottom layer of slot c + y
        ph = table[c].top[0]
        a0 = g.slot_angle(c) - side_span / 2
        span = g.coil_pitch * pitch + side_span
        for sign in (1.0, -1.0):
            z_a, z_b = sorted((sign * plane[ph], sign * (plane[ph] + thick)))
            pieces[ph] += _sectors(r_lo, r_hi, z_a, z_b, a0, span, cut)
    for ph in PHASE_INDEX:
        a_mid = g.slot_angle(PHASE_INDEX[ph] * 2 * w.q)  # roughly the first belt of the phase
        parts.append(Part(f"winding_{ph}", "winding", f"phase_{ph}", merge(pieces[ph]),
                          anchor=(r_mid * math.cos(a_mid), r_mid * math.sin(a_mid), plane[ph] + thick),
                          facts={"coil_sides": counts[ph], "coils": counts[ph] // 2, "q": w.q, "y": w.y,
                                 "kw1": float(winding_mod.winding_factor(w, 1))}))

    # air gap (stationary, drawn enlarged)
    parts.append(Part("air_gap", "air_gap", "air_gap", merge(_sectors(g.r_rotor, g.r_bore, -half, half, 0.0,
                                                                         TWO_PI, cut)),
                      anchor=(-g.r_bore * 0.7, g.r_bore * 0.7, half), facts={"gap_drawn": g.gap}))

    # rotor (turns with θm; never cut)
    bar_pitch = TWO_PI / g.n_bars
    bar = g.bar_fraction * bar_pitch
    r_bar_in = g.r_rotor - g.bar_depth
    rotor = [annular_sector(g.r_shaft, r_bar_in + 1e-4, -half, half)]
    bars, rings = [], []
    for k in range(g.n_bars):
        a = k * bar_pitch
        rotor.append(annular_sector(r_bar_in, g.r_rotor, -half, half, a + bar / 2, bar_pitch - bar, 2))
        bars.append(annular_sector(r_bar_in + 1e-4, g.r_rotor - 0.0002, -half - 1e-3, half + 1e-3,
                                   a - bar / 2, bar, 2))
    for sign in (1.0, -1.0):
        z_a, z_b = sorted((sign * half, sign * (half + g.ring_axial)))
        rings.append(annular_sector(r_bar_in - 0.002, g.r_rotor - 0.0005, z_a, z_b))
    rot_ex = (0.0, 0.0, 0.30)
    parts.append(Part("rotor_core", "rotor", "steel_rotor", merge(rotor), spin="motor", explode=rot_ex,
                      anchor=(0.0, g.r_rotor * 0.6, half), facts={"r_rotor": g.r_rotor}))
    parts.append(Part("rotor_bars", "cage", "aluminium", merge(bars), spin="motor", explode=rot_ex,
                      anchor=(g.r_rotor * 0.9, 0.0, 0.0), facts={"n_bars": g.n_bars}))
    parts.append(Part("end_rings", "cage", "aluminium", merge(rings), spin="motor", explode=rot_ex,
                      anchor=(0.0, -g.r_rotor * 0.8, half + g.ring_axial)))
    shaft_back, shaft_front = -(hz + 0.03), hz + 0.095
    parts.append(Part("shaft", "shaft", "shaft", annular_sector(0.0, g.r_shaft, shaft_back, shaft_front, 0.0,
                                                                TWO_PI, 48),
                      spin="motor", explode=rot_ex, anchor=(0.0, g.r_shaft, shaft_front),
                      facts={"r_shaft": g.r_shaft}))

    # bearings: outer race, inner race and balls
    z_b = hz + 0.008
    for name, sign, ex in (("bearing_front", 1.0, 0.36), ("bearing_back", -1.0, -0.37)):
        zc = sign * z_b
        m = _sectors(0.031, r_hub, zc - 0.008, zc + 0.008, 0.0, TWO_PI, cut)
        m += _sectors(g.r_shaft, 0.024, zc - 0.008, zc + 0.008, 0.0, TWO_PI, cut)
        for k in range(9):
            a = k * TWO_PI / 9
            if not _subtract(a - 0.01, 0.02, cut) == [(a - 0.01, 0.02)]:
                continue
            m.append(sphere((0.0275 * math.cos(a), 0.0275 * math.sin(a), zc), 0.0034, 6, 10))
        parts.append(Part(name, "bearings", "bearing", merge(m), explode=(0.0, 0.0, ex),
                          anchor=(0.0, r_hub, zc)))
    return parts


# --- powertrain -------------------------------------------------------------------------------


@dataclass(frozen=True)
class PowertrainLayout:
    """Illustrative vehicle layout (A37), m; the wheel radius and the ratio come from the vehicle (tab 4)."""

    wheel_radius: float
    gear_ratio: float
    track: float = 1.30
    wheelbase: float = 2.00
    tyre_width: float = 0.145
    pinion_1: float = 0.022  # first-stage pinion radius
    pinion_2: float = 0.028  # second-stage pinion radius
    gearbox_x: float = -0.16  # plane of the gears
    is_illustrative: bool = True

    def __post_init__(self) -> None:
        for name in ("wheel_radius", "gear_ratio", "track", "wheelbase", "tyre_width", "pinion_1", "pinion_2"):
            _pos(name, getattr(self, name))
        if self.gear_ratio < 1:
            raise ValueError(f"the reduction ratio must be >= 1, got {self.gear_ratio!r}")

    @property
    def stage_ratio(self) -> float:
        """Each of the two stages takes √G (illustrative split, A37)."""
        return math.sqrt(self.gear_ratio)

    @property
    def gear_1(self) -> float:
        return self.pinion_1 * self.stage_ratio

    @property
    def gear_2(self) -> float:
        return self.pinion_2 * self.stage_ratio

    @property
    def axle(self) -> np.ndarray:
        """Centre of the driven (front) axle, m."""
        return np.array([0.0, self.wheel_radius, 0.5 * self.wheelbase])

    @property
    def intermediate(self) -> np.ndarray:
        return self.axle - np.array([0.0, 0.0, self.pinion_2 + self.gear_2])

    @property
    def motor_axis(self) -> np.ndarray:
        return self.intermediate - np.array([0.0, 0.0, self.pinion_1 + self.gear_1])


def demo_layout(veh: vehicle_mod.Vehicle) -> PowertrainLayout:
    """Layout for a vehicle: its wheel radius and overall ratio, the other lengths A37."""
    return PowertrainLayout(wheel_radius=veh.wheel_radius, gear_ratio=veh.gear_ratio)


def _gear(radius: float, width: float, n_teeth: int) -> Mesh:
    """Spur gear about x (illustrative teeth), centred on the origin."""
    tooth = 0.006
    m = [annular_sector(0.0, radius - tooth / 2, -width / 2, width / 2, 0.0, TWO_PI, 48)]
    span = 0.5 * TWO_PI / n_teeth
    for k in range(n_teeth):
        m.append(annular_sector(radius - tooth / 2 - 1e-4, radius + tooth / 2, -width / 2, width / 2,
                                k * TWO_PI / n_teeth, span, 1))
    return merge(m).transformed(rotation("y", math.pi / 2))


def _wheel(lay: PowertrainLayout) -> Mesh:
    """Wheel about x centred on the origin: tyre, rim, spokes, hub."""
    r, w = lay.wheel_radius, lay.tyre_width
    rim = 0.62 * r
    return annular_sector(rim, r, -w / 2, w / 2, 0.0, TWO_PI, 64).transformed(rotation("y", math.pi / 2))


def _rim(lay: PowertrainLayout) -> Mesh:
    r, w = lay.wheel_radius, lay.tyre_width
    rim = 0.62 * r
    m = [annular_sector(rim - 0.012, rim + 1e-4, -w / 2 + 0.01, w / 2 - 0.01, 0.0, TWO_PI, 64),
         annular_sector(0.0, 0.05, -0.03, 0.03, 0.0, TWO_PI, 24)]
    for k in range(5):
        a = k * TWO_PI / 5
        m.append(box((0.0, 0.0, 0.0), (0.03, 2 * rim - 0.02, 0.018)).transformed(rotation("z", a)))
    return merge(m).transformed(rotation("y", math.pi / 2))


def powertrain_parts(lay: PowertrainLayout, g: MotorGeometry, pack: battery_mod.PackParams) -> list[Part]:
    """Components of the powertrain: battery, inverter, cables, motor, two-stage reduction, differential,
    half-shafts, wheels and chassis. x lateral, y up, z forward; the motor axis is along x."""
    parts: list[Part] = []
    ax, inter, mot = lay.axle, lay.intermediate, lay.motor_axis
    gx = lay.gearbox_x
    half_track = 0.5 * lay.track
    r = lay.wheel_radius
    # chassis frame (illustrative)
    rails = [box((x, 0.20, 0.0), (0.06, 0.06, lay.wheelbase + 0.6)) for x in (-0.45, 0.45)]
    rails += [box((0.0, 0.20, z), (0.96, 0.05, 0.05)) for z in (-0.5 * lay.wheelbase, 0.15, 0.5 * lay.wheelbase - 0.45)]
    parts.append(Part("chassis", "chassis", "chassis", merge(rails), anchor=(0.45, 0.24, -0.5 * lay.wheelbase)))
    # battery pack under the floor: 12 modules (drawn), and the SOC gauge (height scaled by the SOC)
    pc = np.array([0.0, 0.30, -0.35])
    size = np.array([0.80, 0.11, 0.90])
    modules = []
    for i in range(2):
        for j in range(6):
            modules.append(box(pc + [(-0.2 + 0.4 * i), 0.0, -0.375 + 0.15 * j], (0.36, 0.09, 0.13)))
    parts.append(Part("battery", "battery", "battery", merge(modules + [box(pc - [0, 0.052, 0], (0.82, 0.008, 0.92))]),
                      anchor=tuple(pc + [0.40, 0.06, 0.0]),
                      facts={"n_series": pack.n_series, "n_parallel": pack.n_parallel,
                             "energy_wh": pack.energy_wh(), "v_nominal": float(battery_mod.ocv(pack, 0.5))}))
    gauge_base = pc + np.array([0.33, 0.06, 0.38])  # SOC column on a corner of the pack (height ∝ SOC in the GUI)
    parts.append(Part("battery_soc", "battery", "soc", box((0.0, 0.11, 0.0), (0.05, 0.22, 0.05)),
                      origin=tuple(gauge_base), anchor=(0.0, 0.24, 0.0)))
    parts.append(Part("battery_soc_case", "battery", "soc_case", box((0.0, 0.11, 0.0), (0.06, 0.222, 0.06)),
                      origin=tuple(gauge_base)))
    # inverter with a heat sink, near the motor
    ic = mot + np.array([0.12, 0.30, -0.10])
    inv = [box(ic, (0.26, 0.09, 0.20))]
    inv += [box(ic + [-0.11 + 0.022 * k, -0.065, 0.0], (0.006, 0.04, 0.19)) for k in range(11)]
    parts.append(Part("inverter", "inverter", "inverter", merge(inv), anchor=tuple(ic + [0.0, 0.05, 0.0])))
    # motor: housing (static) and shaft (turns) — the same illustrative motor, its axis along x
    to_x = rotation("y", math.pi / 2)
    mc = mot + np.array([gx + 0.05 + g.half_length + 0.02, 0.0, 0.0])
    full = {p.key: p for p in motor_parts(g, winding_mod.Winding(g.n_slots, g.poles, 3, g.coil_pitch))}
    body = merge([full[k].mesh for k in ("housing", "terminal_box", "shield_front", "shield_back")])
    flip = rotation("y", -math.pi / 2)  # drive end (+z of the motor) towards −x, the gearbox
    parts.append(Part("motor", "motor", "housing", body.transformed(flip), origin=tuple(mc), axis="x",
                      anchor=(0.0, g.r_housing + 0.06, 0.0)))
    parts.append(Part("motor_shaft", "motor", "shaft",
                      cylinder_between((gx - 0.02 - mot[0], 0, 0), (mc[0] - mot[0], 0, 0), g.r_shaft, 24),
                      origin=tuple(mot), axis="x", spin="motor"))
    # two-stage reduction
    t1 = max(10, round(lay.pinion_1 * 500))
    parts.append(Part("pinion_1", "gearbox", "gear", _gear(lay.pinion_1, 0.03, t1), origin=(gx, mot[1], mot[2]),
                      axis="x", spin="motor", anchor=(0.0, lay.pinion_1 + 0.02, 0.0),
                      facts={"radius": lay.pinion_1}))
    parts.append(Part("gear_1", "gearbox", "gear", _gear(lay.gear_1, 0.03, round(t1 * lay.stage_ratio)),
                      origin=(gx, inter[1], inter[2]), axis="x", spin="intermediate",
                      anchor=(0.0, lay.gear_1 + 0.02, 0.0), facts={"radius": lay.gear_1, "ratio": lay.stage_ratio}))
    t2 = max(10, round(lay.pinion_2 * 500))
    parts.append(Part("pinion_2", "gearbox", "gear", _gear(lay.pinion_2, 0.03, t2),
                      origin=(gx + 0.04, inter[1], inter[2]), axis="x", spin="intermediate",
                      facts={"radius": lay.pinion_2}))
    parts.append(Part("gear_2", "gearbox", "gear_final", _gear(lay.gear_2, 0.03, round(t2 * lay.stage_ratio)),
                      origin=(gx + 0.04, ax[1], ax[2]), axis="x", spin="wheel",
                      anchor=(0.0, lay.gear_2 + 0.02, 0.0), facts={"radius": lay.gear_2, "ratio": lay.stage_ratio}))
    inter_shaft = cylinder_between((-0.02, 0, 0), (0.06, 0, 0), 0.012, 16)
    parts.append(Part("intermediate_shaft", "gearbox", "shaft", inter_shaft, origin=(gx, inter[1], inter[2]),
                      axis="x", spin="intermediate"))
    # differential on the axle and the half-shafts
    diff = annular_sector(0.0, 0.07, -0.05, 0.05, 0.0, TWO_PI, 32).transformed(to_x)
    parts.append(Part("differential", "gearbox", "differential", diff, origin=(gx + 0.11, ax[1], ax[2]),
                      axis="x", spin="wheel", anchor=(0.0, 0.10, 0.0)))
    shafts = merge([cylinder_between((-half_track + lay.tyre_width / 2, 0, 0), (gx + 0.06, 0, 0), 0.016, 16),
                    cylinder_between((gx + 0.16, 0, 0), (half_track - lay.tyre_width / 2, 0, 0), 0.016, 16)])
    parts.append(Part("half_shafts", "gearbox", "shaft", shafts, origin=tuple(ax), axis="x", spin="wheel",
                      anchor=(0.35, 0.03, 0.0)))
    # wheels: driven (front) and rolling (rear); all turn at v/r
    for key, z, driven in (("wheel_fl", ax[2], True), ("wheel_fr", ax[2], True),
                           ("wheel_rl", ax[2] - lay.wheelbase, False), ("wheel_rr", ax[2] - lay.wheelbase, False)):
        x = -half_track if key.endswith("l") else half_track
        origin = (x, r, z)
        parts.append(Part(key, "wheels", "tyre", _wheel(lay), origin=origin, axis="x", spin="wheel",
                          anchor=(0.0, r + 0.05, 0.0),
                          facts={"wheel_radius": r, "driven": float(driven)}))
        parts.append(Part(key + "_rim", "wheels", "rim", _rim(lay), origin=origin, axis="x", spin="wheel"))
    # cables: DC (battery → inverter) and AC (inverter → terminal box); their paths are the flow paths
    for key, pts, radius in _cable_paths(lay, g, pc, ic, mc):
        tubes = [cylinder_between(a, b, radius, 12) for a, b in zip(pts[:-1], pts[1:])]
        parts.append(Part(key, "cables", "cable_dc" if key.startswith("dc") else "cable_ac", merge(tubes)))
    return parts


def _cable_paths(lay: PowertrainLayout, g: MotorGeometry, pc: np.ndarray, ic: np.ndarray, mc: np.ndarray):
    tb = mc + np.array([0.0, g.r_housing + 0.05, 0.0])
    out = []
    for k, dx in enumerate((-0.05, 0.05)):
        a = pc + np.array([dx, 0.06, 0.45])
        b = np.array([a[0], ic[1], a[2]])
        c = ic + np.array([dx, 0.0, -0.10])
        out.append((f"dc_{'+-'[k]}", np.array([a, b, c]), 0.009))
    for k, dx in enumerate((-0.04, 0.0, 0.04)):
        a = ic + np.array([dx - 0.13, 0.0, 0.0])
        b = np.array([tb[0] + dx, ic[1], tb[2]])
        c = tb + np.array([dx, 0.0, 0.0])
        out.append((f"ac_{'UVW'[k]}", np.array([a, b, c]), 0.007))
    return out


def flow_paths(lay: PowertrainLayout, g: MotorGeometry) -> dict[str, np.ndarray]:
    """Polylines (m) along which the power of each link is drawn: battery → inverter (dc), inverter →
    motor (ac), motor shaft → gears (shaft), differential → driven wheels (wheel)."""
    pc = np.array([0.0, 0.30, -0.35])
    mot = lay.motor_axis
    ic = mot + np.array([0.12, 0.30, -0.10])
    mc = mot + np.array([lay.gearbox_x + 0.05 + g.half_length + 0.02, 0.0, 0.0])
    paths = {key: pts for key, pts, _ in _cable_paths(lay, g, pc, ic, mc)}
    ax = lay.axle
    return {
        "dc": paths["dc_+"],
        "ac": paths["ac_V"],
        "shaft": np.array([[mc[0], mot[1], mot[2]], [lay.gearbox_x, mot[1], mot[2]],
                           [lay.gearbox_x, lay.intermediate[1], lay.intermediate[2]],
                           [lay.gearbox_x + 0.06, ax[1], ax[2]]]),
        "wheel": np.array([[lay.gearbox_x + 0.06, ax[1], ax[2]], [0.5 * lay.track - lay.tyre_width, ax[1], ax[2]]]),
    }


def points_along(polyline: ArrayLike, fractions: ArrayLike) -> np.ndarray:
    """Points at fractions (0…1, wrapped) of the length of a polyline, m."""
    pts = np.asarray(polyline, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 3 or len(pts) < 2:
        raise ValueError("a polyline needs at least two 3-D points")
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    if cum[-1] <= 0:
        raise ValueError("the polyline has zero length")
    s = (np.asarray(fractions, dtype=float) % 1.0) * cum[-1]
    return np.stack([np.interp(s, cum, pts[:, k]) for k in range(3)], -1)


# --- playback of a simulated cycle ------------------------------------------------------------


@dataclass(frozen=True)
class Playback:
    """A simulated cycle prepared for the scene.

    t: cycle instants (n + 1), s.  Interval values (n, piecewise constant as in the simulation): v (m/s),
    omega_motor and omega_wheel (rad/s), torque (N·m), p_battery, p_dc (drive DC input = battery − auxiliaries),
    p_ac (inverter output = p_dc − inverter losses of the map, None without the map), p_shaft,
    p_wheel (motor path at the wheels), p_friction (friction brakes), W.
    Boundary values (n + 1): angle_motor and angle_wheel (rad, ∫ω dt), soc, t_winding and t_frame (K) when
    the battery or the thermal result is given (None otherwise).
    """

    t: np.ndarray
    v: np.ndarray
    omega_motor: np.ndarray
    omega_wheel: np.ndarray
    torque: np.ndarray
    p_battery: np.ndarray
    p_dc: np.ndarray
    p_shaft: np.ndarray
    p_wheel: np.ndarray
    p_friction: np.ndarray
    angle_motor: np.ndarray
    angle_wheel: np.ndarray
    gear_ratio: float
    p_ac: np.ndarray | None = None  # inverter output (motor input), W, when the efficiency map is given
    stage_ratio: float = 1.0
    soc: np.ndarray | None = None
    t_winding: np.ndarray | None = None
    t_frame: np.ndarray | None = None
    thermal_cycle: tuple[int, int] | None = None  # (shown cycle, cycles simulated), 1-based
    is_demo: bool = False

    @property
    def duration(self) -> float:
        return float(self.t[-1] - self.t[0])

    @property
    def p_max(self) -> float:
        """Largest |power| of the links, W (scale of the power-flow display)."""
        return float(max(np.max(np.abs(a)) for a in (self.p_battery, self.p_dc, self.p_shaft, self.p_wheel)))


def playback(res: vehicle_mod.DriveResult, cycle: vehicle_mod.Cycle, veh: vehicle_mod.Vehicle,
             battery: battery_mod.BatteryResult | None = None,
             thermal: thermal_mod.ThermalResult | None = None,
             emap: losses_mod.EfficiencyMap | None = None) -> Playback:
    """Prepare a vehicle result (tab 4), and optionally its battery and thermal results, for the scene.

    The thermal model may cover several identical cycles back to back: the last one is shown (the one its
    summary uses). Raises ValueError when the series do not belong to the same cycle.
    """
    t = np.asarray(cycle.t, dtype=float)
    n = len(t) - 1
    if len(res.v) != n:
        raise ValueError(f"the vehicle result has {len(res.v)} intervals, the cycle {n}")
    dt = np.diff(t)
    om = np.asarray(res.omega, dtype=float)
    ow = np.asarray(res.v, dtype=float) / veh.wheel_radius
    angle_m = np.concatenate([[0.0], np.cumsum(om * dt)])
    angle_w = np.concatenate([[0.0], np.cumsum(ow * dt)])
    p_wheel, p_friction = vehicle_mod.wheel_powers(res, veh)
    p_dc = np.asarray(res.p_battery, dtype=float) - veh.aux_power
    p_ac = None
    if emap is not None:  # the same interpolation of the map as the vehicle's losses (LossTable, A24)
        p_inv = np.where(om > 0, vehicle_mod.LossTable(emap, "p_inv")(res.torque, om), 0.0)
        p_ac = p_dc - p_inv
    soc = None
    if battery is not None:
        if len(battery.soc) != n + 1:
            raise ValueError(f"the battery result has {len(battery.soc) - 1} steps, the cycle {n}")
        soc = np.asarray(battery.soc, dtype=float)
    tw = tf = shown = None
    if thermal is not None:
        m = len(thermal.t_w) - 1
        if m % n != 0 or m == 0:
            raise ValueError(f"the thermal result has {m} steps, not a whole number of {n}-step cycles")
        k = m // n
        tw, tf = thermal.t_w[m - n:].copy(), thermal.t_s[m - n:].copy()
        shown = (k, k)
    return Playback(t=t, v=np.asarray(res.v, dtype=float), omega_motor=om, omega_wheel=ow,
                    torque=np.asarray(res.torque, dtype=float), p_battery=np.asarray(res.p_battery, dtype=float),
                    p_dc=p_dc, p_ac=p_ac,
                    p_shaft=np.asarray(res.p_shaft, dtype=float), p_wheel=p_wheel, p_friction=p_friction,
                    angle_motor=angle_m, angle_wheel=angle_w, gear_ratio=veh.gear_ratio,
                    stage_ratio=math.sqrt(veh.gear_ratio), soc=soc, t_winding=tw, t_frame=tf,
                    thermal_cycle=shown, is_demo=bool(cycle.is_demo or veh.is_demo))


@dataclass(frozen=True)
class Frame:
    """State of the scene at one instant (SI). Angles in rad: motor, intermediate shaft (turns the other
    way, θm/√G), differential and wheels (θm/G)."""

    t: float
    v: float
    omega_motor: float
    omega_wheel: float
    torque: float
    p_battery: float
    p_dc: float
    p_ac: float | None
    p_shaft: float
    p_wheel: float
    p_friction: float
    angle_motor: float
    angle_intermediate: float
    angle_wheel: float
    soc: float | None
    t_winding: float | None
    t_frame: float | None


def frame_at(pb: Playback, t: float) -> Frame:
    """The scene at time t (s, within the cycle): interval values held, angles exact for the constant
    speed of the interval, SOC and temperatures interpolated between the step boundaries."""
    if not math.isfinite(t) or t < pb.t[0] - 1e-9 or t > pb.t[-1] + 1e-9:
        raise ValueError(f"t must be within the cycle [{pb.t[0]:g}, {pb.t[-1]:g}] s, got {t!r}")
    n = len(pb.v)
    k = int(min(max(np.searchsorted(pb.t, t, side="right") - 1, 0), n - 1))
    tau = t - pb.t[k]
    am = pb.angle_motor[k] + pb.omega_motor[k] * tau
    aw = pb.angle_wheel[k] + pb.omega_wheel[k] * tau

    def interp(a: np.ndarray | None) -> float | None:
        return None if a is None else float(np.interp(t, pb.t, a))

    return Frame(t=float(t), v=float(pb.v[k]), omega_motor=float(pb.omega_motor[k]),
                 omega_wheel=float(pb.omega_wheel[k]), torque=float(pb.torque[k]),
                 p_battery=float(pb.p_battery[k]), p_dc=float(pb.p_dc[k]),
                 p_ac=None if pb.p_ac is None else float(pb.p_ac[k]), p_shaft=float(pb.p_shaft[k]),
                 p_wheel=float(pb.p_wheel[k]), p_friction=float(pb.p_friction[k]),
                 angle_motor=float(am), angle_intermediate=float(-am / pb.stage_ratio),
                 angle_wheel=float(aw), soc=interp(pb.soc), t_winding=interp(pb.t_winding),
                 t_frame=interp(pb.t_frame))


MAX_DISPLAY_SPEED = math.pi  # rad/s on screen: half a turn per second


def display_slowdown(pb: Playback, rate: float) -> float:
    """Factor k ≥ 1 by which the drawn rotations are slowed so that the fastest part (the rotor) turns at
    most MAX_DISPLAY_SPEED on screen when the cycle plays rate times faster than real time. All parts
    use the same k, so their speed ratios stay exact."""
    _pos("rate", rate)
    return max(1.0, float(np.max(np.abs(pb.omega_motor))) * rate / MAX_DISPLAY_SPEED)


def flow_direction(power: float, threshold: float = 1.0) -> int:
    """+1 power towards the wheels, −1 towards the battery (regeneration), 0 below the threshold (W)."""
    return 0 if abs(power) < threshold else (1 if power > 0 else -1)


def advance_flow_phase(phase: float, power: float, p_ref: float, dt_screen: float) -> float:
    """Position (0…1) of the power-flow markers after dt_screen seconds on screen: they move towards the
    wheels when power > 0 and back to the battery when < 0, faster with |power|/p_ref (display rule)."""
    _pos("p_ref", p_ref)
    if not math.isfinite(dt_screen) or dt_screen < 0:
        raise ValueError(f"dt_screen must be >= 0 s, got {dt_screen!r}")
    d = flow_direction(power)
    speed = 0.0 if d == 0 else 0.15 + 0.6 * min(1.0, abs(power) / p_ref)
    return (phase + d * speed * dt_screen) % 1.0


def temperature_fraction(t_k: float, t_low: float, t_high: float) -> float:
    """Position of a temperature on a colour scale [t_low, t_high] (K), saturated at both ends (display)."""
    _pos("t_high - t_low", t_high - t_low)
    return float(min(1.0, max(0.0, (t_k - t_low) / (t_high - t_low))))
