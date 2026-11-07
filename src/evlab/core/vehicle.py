"""Vehicle sized to the identified motor, driven on a cycle (stage 5, tab 4).

The vehicle fits the motor, not the other way round: the motor (Session),
its envelope (tab 2) and its efficiency map (tab 3) are given; the helper
proposes the gear ratio and reads the WLTC class from the power-to-mass ratio.

Per 1 s interval k (midpoint speed v̄ = (v_k + v_k+1)/2, a = (v_k+1 − v_k)/Δt,
so that Σ m·a·v̄·Δt = Δ(½·m·v²) exactly):
  F   = m·a + ½·ρ·Cx·S·v̄² + Crr·m·g·cosθ + m·g·sinθ      (F = 0 when held at rest)
  ωm  = G·v̄/r
  T   = F·r/(G·ηg) in traction, F·r·ηg/G in braking (regenerative, capped by the
        envelope; the rest goes to the friction brakes; T = 0 when regen is off)
  P_batt = T·ωm + P_losses(|T|, ωm) + P_aux
with P_losses the motor + inverter losses of the efficiency map (P_in − P_out),
interpolated bilinearly (A24). Energy balance:
  ∫P_batt = ΔE_kin + E_aero + E_roll + E_grade + E_gear + E_friction + E_losses + E_aux
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import ArrayLike
from scipy.interpolate import RegularGridInterpolator

from evlab.core import drive, losses
from evlab.core.session import MotorParams

G_EARTH = 9.81  # m/s²
RHO_AIR = 1.2  # kg/m³ (A22)
SPEED_MARGIN = 0.95  # top speed of the cycle at ≤ 95 % of the envelope's maximum speed (A23)
# proposes the ratio and reads the WLTC class from the power-to-mass ratio
WLTC_LIMITS = (22.0, 34.0)  # W/kg: class 1 ≤ 22, class 2 ≤ 34, class 3 above


def _pos(name: str, x: float) -> None:
    if not math.isfinite(x) or x <= 0:
        raise ValueError(f"{name} must be a finite number > 0, got {x!r}")


@dataclass(frozen=True)
class Cycle:
    """Drive cycle: time t (s) and speed v (m/s), equal-length 1-D arrays."""

    t: np.ndarray
    v: np.ndarray
    name: str
    is_demo: bool

    def __post_init__(self) -> None:
        t, v = np.asarray(self.t, dtype=float), np.asarray(self.v, dtype=float)
        if t.ndim != 1 or t.shape != v.shape or t.size < 2:
            raise ValueError("cycle t and v must be 1-D arrays of the same length (>= 2)")
        if not (np.all(np.isfinite(t)) and np.all(np.isfinite(v))):
            raise ValueError("cycle t and v must be finite")
        if np.any(np.diff(t) <= 0):
            raise ValueError("cycle time must be strictly increasing")
        if np.any(v < 0):
            raise ValueError("cycle speed must be >= 0")


@dataclass(frozen=True)
class CycleStats:
    """duration (s), distance (m, trapezoidal), v_max (m/s)."""

    duration: float
    distance: float
    v_max: float


def cycle_stats(c: Cycle) -> CycleStats:
    """Duration t_end − t_0, distance ∫v dt (trapezoids), maximum speed of a cycle."""
    return CycleStats(float(c.t[-1] - c.t[0]), float(np.trapezoid(c.v, c.t)), float(np.max(c.v)))


@dataclass(frozen=True)
class Vehicle:
    """Vehicle parameters (SI).

    Attributes:
        mass: test mass, kg.  cx_s: drag area Cx·S, m².  crr: rolling coefficient.
        wheel_radius: dynamic wheel radius r, m.  gear_ratio: G = ωm/ωwheel.
        gear_efficiency: ηg, in (0, 1].  aux_power: auxiliaries, W (≥ 0).
        regen: regenerative braking on/off.  grade: road slope θ, rad.
        name: label.  is_demo: demo values (labelled "démo").
    """

    mass: float
    cx_s: float
    crr: float
    wheel_radius: float
    gear_ratio: float
    gear_efficiency: float = 0.95
    aux_power: float = 200.0
    regen: bool = True
    grade: float = 0.0
    name: str = "véhicule"
    is_demo: bool = False

    def __post_init__(self) -> None:
        for n in ("mass", "cx_s", "wheel_radius", "gear_ratio"):
            _pos(n, getattr(self, n))
        if not math.isfinite(self.crr) or self.crr < 0:
            raise ValueError(f"crr must be >= 0, got {self.crr!r}")
        if not math.isfinite(self.gear_efficiency) or not 0 < self.gear_efficiency <= 1:
            raise ValueError(f"gear_efficiency must be in (0, 1], got {self.gear_efficiency!r}")
        if not math.isfinite(self.aux_power) or self.aux_power < 0:
            raise ValueError(f"aux_power must be >= 0 W, got {self.aux_power!r}")
        if not math.isfinite(self.grade) or abs(self.grade) >= math.pi / 4:
            raise ValueError(f"grade must be a slope in (−45°, 45°), got {self.grade!r} rad")


def demo_quadricycle(gear_ratio: float = 4.0, regen: bool = True) -> Vehicle:
    """Light electric quadricycle (L7e class), démo values of docs/assumptions.md A22."""
    return Vehicle(mass=600.0, cx_s=0.60, crr=0.012, wheel_radius=0.27, gear_ratio=gear_ratio,
                   gear_efficiency=0.95, aux_power=200.0, regen=regen,
                   name="quadricycle léger (démo)", is_demo=True)


def road_force(veh: Vehicle, v: ArrayLike, a: ArrayLike, grade: float | None = None) -> float | np.ndarray:
    """F = m·a + ½·ρ·Cx·S·v² + Crr·m·g·cosθ + m·g·sinθ, N (0 when the vehicle is held at rest)."""
    th = veh.grade if grade is None else grade
    v, a = np.asarray(v, dtype=float), np.asarray(a, dtype=float)
    f = (veh.mass * a + 0.5 * RHO_AIR * veh.cx_s * v**2
         + veh.crr * veh.mass * G_EARTH * math.cos(th) + veh.mass * G_EARTH * math.sin(th))
    f = np.where((v == 0) & (a == 0), 0.0, f)
    return float(f) if f.ndim == 0 else f


def motor_speed(veh: Vehicle, v: ArrayLike) -> float | np.ndarray:
    """ωm = G·v/r, rad/s."""
    w = veh.gear_ratio * np.asarray(v, dtype=float) / veh.wheel_radius
    return float(w) if w.ndim == 0 else w


def motor_torque(veh: Vehicle, force: ArrayLike) -> float | np.ndarray:
    """Shaft torque for a wheel force: F·r/(G·ηg) in traction, F·r·ηg/G in braking, N·m."""
    f = np.asarray(force, dtype=float)
    k = veh.wheel_radius / veh.gear_ratio
    t = np.where(f >= 0, f * k / veh.gear_efficiency, f * k * veh.gear_efficiency)
    return float(t) if t.ndim == 0 else t


def wltc_class(pmr: float) -> int:
    """WLTC class from the power-to-mass ratio (W/kg): ≤ 22 → 1, ≤ 34 → 2, else 3."""
    if not math.isfinite(pmr) or pmr <= 0:
        raise ValueError(f"pmr must be a finite number > 0 W/kg, got {pmr!r}")
    return 1 if pmr <= WLTC_LIMITS[0] else 2 if pmr <= WLTC_LIMITS[1] else 3


def rated_power(m: MotorParams, env: drive.Envelope, st: losses.LossSettings) -> float:
    """Rated power of the motor for the PMR: maximum shaft power along its envelope, W (A23)."""
    return float(np.max(losses.shaft_torque_limit(m, env, st) * env.omega))


@dataclass(frozen=True)
class Sizing:
    """Result of size_vehicle.

    Attributes:
        rated_power: W.  mass: kg.  pmr: W/kg.  wltc_class: 1, 2 or 3.
        gear_ratio: proposed G.  gear_ratio_max: G that puts the cycle's top speed at
            SPEED_MARGIN·Ω_max.  v_max: top speed of the cycle, m/s.
        min_margin: smallest T_limit/T_demand over the traction points with the proposed G.
        feasible: True if every point of the cycle is inside the envelope (min_margin ≥ 1).
    """

    rated_power: float
    mass: float
    pmr: float
    wltc_class: int
    gear_ratio: float
    gear_ratio_max: float
    v_max: float
    min_margin: float
    feasible: bool


GEAR_SCAN = np.linspace(0.25, 1.0, 301)  # × gear_ratio_max


def torque_margin(cycle: Cycle, veh: Vehicle, m: MotorParams, env: drive.Envelope,
                  st: losses.LossSettings, gear_ratios: ArrayLike) -> np.ndarray:
    """Smallest T_limit(ωm)/T_demand over the traction points, for each gear ratio (0 beyond Ω_max)."""
    v = 0.5 * (cycle.v[1:] + cycle.v[:-1])
    a = np.diff(cycle.v) / np.diff(cycle.t)
    f = np.asarray(road_force(veh, v, a))
    trac = f > 0
    if not trac.any():
        return np.full(np.shape(gear_ratios), np.inf)
    g = np.asarray(gear_ratios, dtype=float)[:, None]
    omega = g * v[trac] / veh.wheel_radius
    t_dem = f[trac] * veh.wheel_radius / (g * veh.gear_efficiency)
    t_lim = np.interp(omega, env.omega, losses.shaft_torque_limit(m, env, st), right=0.0)
    ratio = np.where(omega > env.omega_max, 0.0, t_lim / t_dem)
    return ratio.min(axis=1)


def size_vehicle(m: MotorParams, env: drive.Envelope, st: losses.LossSettings, veh: Vehicle,
                 cycle: Cycle) -> Sizing:
    """PMR = P_rated/m → WLTC class; G that keeps the whole cycle inside the envelope.

    G_max = margin·r·Ω_max/v_max puts the top speed inside the envelope. Below it,
    G is scanned and the value with the largest worst-case torque margin
    min(T_limit/T_demand) is proposed: a longer ratio lacks torque at launch, a
    shorter one pushes the motor into field weakening where torque falls faster
    than 1/G (A23).
    """
    p = rated_power(m, env, st)
    pmr = p / veh.mass
    v_max = cycle_stats(cycle).v_max
    _pos("cycle v_max", v_max)
    g_max = SPEED_MARGIN * veh.wheel_radius * env.omega_max / v_max
    scan = g_max * GEAR_SCAN
    margin = torque_margin(cycle, veh, m, env, st, scan)
    k = int(np.argmax(margin))
    return Sizing(p, veh.mass, pmr, wltc_class(pmr), float(scan[k]), g_max, v_max,
                  float(margin[k]), bool(margin[k] >= 1.0))


class LossTable:
    """A loss term of an efficiency map, interpolated at any (|T|, ω); default: total P_in − P_out.

    Above the envelope (NaN in the map) each speed column keeps its last valid
    value; queries outside the grid are clamped to it (A24).
    """

    def __init__(self, emap: losses.EfficiencyMap, term: str = "total") -> None:
        if term == "total":
            loss = emap.p_in - emap.p_out
        elif term in ("p_cu1", "p_cu2", "p_fe", "p_mech", "p_inv", "i1"):
            loss = getattr(emap, term)
        else:
            raise ValueError(f"unknown loss term {term!r}")
        if not emap.valid.any():
            raise ValueError("the efficiency map has no point inside the envelope")
        filled = loss.copy()
        for j in range(filled.shape[1]):
            col = filled[:, j]
            ok = np.nonzero(np.isfinite(col))[0]
            if ok.size == 0:
                continue
            col[: ok[0]] = col[ok[0]]
            col[ok[-1] + 1:] = col[ok[-1]]
            col[ok[0]: ok[-1] + 1] = np.interp(np.arange(ok[0], ok[-1] + 1), ok, col[ok])
        empty = ~np.isfinite(filled).any(axis=0)
        if empty.any():  # columns beyond the envelope: copy the nearest filled column
            good = np.nonzero(~empty)[0]
            for j in np.nonzero(empty)[0]:
                filled[:, j] = filled[:, good[np.argmin(np.abs(good - j))]]
        self.torque, self.speed = emap.torque, emap.speed
        self._f = RegularGridInterpolator((emap.torque, emap.speed), filled, method="linear")

    def __call__(self, torque, omega) -> np.ndarray:
        t = np.clip(np.abs(np.asarray(torque, dtype=float)), self.torque[0], self.torque[-1])
        w = np.clip(np.asarray(omega, dtype=float), self.speed[0], self.speed[-1])
        return self._f(np.stack([t, w], axis=-1))


def acceleration_time(veh: Vehicle, m: MotorParams, env: drive.Envelope, st: losses.LossSettings,
                      v_target: float, n: int = 400) -> float:
    """Time from standstill to v_target at full torque on a flat road, s (inf if unreachable).

    t = ∫₀^v m·dv / (F_max(v) − F_res(v)), with F_max = T_shaft,max(ωm)·G·ηg/r from the
    envelope and F_res = ½ρCxS·v² + Crr·m·g·cosθ + m·g·sinθ; midpoint rule on n speed steps.
    Rotating inertia is not included (A30).

    Args:
        veh: vehicle.  m: motor.  env: drive envelope.  st: loss settings (shaft limit).
        v_target: target speed, m/s (> 0).  n: integration steps.
    """
    _pos("v_target", v_target)
    v = (np.arange(n) + 0.5) * v_target / n
    omega = veh.gear_ratio * v / veh.wheel_radius
    t_lim = np.interp(omega, env.omega, losses.shaft_torque_limit(m, env, st), right=0.0)
    t_lim = np.where(omega > env.omega_max, 0.0, t_lim)
    f_max = t_lim * veh.gear_ratio * veh.gear_efficiency / veh.wheel_radius
    f_res = (0.5 * RHO_AIR * veh.cx_s * v**2 + veh.crr * veh.mass * G_EARTH * math.cos(veh.grade)
             + veh.mass * G_EARTH * math.sin(veh.grade))
    surplus = f_max - f_res
    if np.any(surplus <= 0):
        return math.inf
    return float(np.sum(veh.mass / surplus) * v_target / n)


@dataclass(frozen=True)
class DriveSummary:
    """Cycle totals: distance (m), duration (s), battery energy net / drawn / returned (J), Wh/km, regen %."""

    distance_m: float
    duration_s: float
    energy_j: float
    energy_traction_j: float
    energy_regen_j: float
    wh_per_km: float
    regen_percent: float
    n_outside: int


@dataclass(frozen=True)
class DriveResult:
    """Per-interval arrays (length N − 1) and totals of a cycle simulation (SI)."""

    t: np.ndarray  # interval midpoints, s
    v: np.ndarray  # midpoint speed, m/s
    a: np.ndarray  # acceleration, m/s²
    force: np.ndarray  # wheel force F, N
    omega: np.ndarray  # motor speed, rad/s
    torque: np.ndarray  # motor shaft torque, N·m (< 0 regenerating)
    p_shaft: np.ndarray  # motor shaft power, W
    p_losses: np.ndarray  # motor + inverter losses, W
    p_battery: np.ndarray  # battery power, W (< 0 charging)
    outside: np.ndarray  # traction demand beyond the envelope
    summary: DriveSummary
    balance: dict[str, float] = field(default_factory=dict)  # energy terms, J


def simulate(cycle: Cycle, veh: Vehicle, m: MotorParams, env: drive.Envelope, emap: losses.EfficiencyMap,
             st: losses.LossSettings) -> DriveResult:
    """Battery power and energy of the vehicle on the cycle (see module docstring)."""
    dt = np.diff(cycle.t)
    v = 0.5 * (cycle.v[1:] + cycle.v[:-1])
    a = np.diff(cycle.v) / dt
    f_aero = 0.5 * RHO_AIR * veh.cx_s * v**2
    moving = ~((v == 0) & (a == 0))
    f_roll = np.where(moving, veh.crr * veh.mass * G_EARTH * math.cos(veh.grade), 0.0)
    f_grade = np.where(moving, veh.mass * G_EARTH * math.sin(veh.grade), 0.0)
    f_inert = veh.mass * a
    force = f_inert + f_aero + f_roll + f_grade
    omega = np.asarray(motor_speed(veh, v))
    t_limit = np.interp(omega, env.omega, losses.shaft_torque_limit(m, env, st), right=0.0)

    t_demand = np.asarray(motor_torque(veh, force))
    traction = force >= 0
    outside = traction & ((omega > env.omega_max) | (t_demand > t_limit * (1 + 1e-9)))
    if veh.regen:
        t_motor = np.where(traction, t_demand, np.maximum(t_demand, -t_limit))
    else:
        t_motor = np.where(traction, t_demand, 0.0)
    # wheel force delivered by the motor in braking, and what the friction brakes take
    k = veh.wheel_radius / veh.gear_ratio
    f_motor = np.where(traction, force, t_motor / (k * veh.gear_efficiency))
    p_shaft = t_motor * omega
    p_wheel_motor = f_motor * v
    p_gear = np.where(traction, p_shaft - force * v, -p_wheel_motor * (1.0 - veh.gear_efficiency))
    p_friction = -(force - f_motor) * v  # >= 0 in braking, 0 in traction
    table = LossTable(emap)
    p_loss = np.where(omega > 0, table(t_motor, omega), 0.0)
    p_batt = p_shaft + p_loss + veh.aux_power

    e = p_batt * dt
    e_trac = float(np.sum(np.where(e > 0, e, 0.0)))
    e_regen = float(np.sum(np.where(e < 0, -e, 0.0)))
    energy = float(np.sum(e))
    distance = float(np.sum(v * dt))
    balance = {
        "battery": energy,
        "kinetic": float(np.sum(f_inert * v * dt)),
        "aero": float(np.sum(f_aero * v * dt)),
        "rolling": float(np.sum(f_roll * v * dt)),
        "grade": float(np.sum(f_grade * v * dt)),
        "gear": float(np.sum(p_gear * dt)),
        "friction_brake": float(np.sum(p_friction * dt)),
        "motor_inverter": float(np.sum(p_loss * dt)),
        "auxiliaries": float(np.sum(veh.aux_power * dt)),
    }
    summary = DriveSummary(
        distance_m=distance,
        duration_s=float(cycle.t[-1] - cycle.t[0]),
        energy_j=energy,
        energy_traction_j=e_trac,
        energy_regen_j=e_regen,
        wh_per_km=energy / 3600.0 / (distance / 1000.0) if distance > 0 else math.nan,
        regen_percent=100.0 * e_regen / e_trac if e_trac > 0 else 0.0,
        n_outside=int(outside.sum()),
    )
    return DriveResult(t=0.5 * (cycle.t[1:] + cycle.t[:-1]), v=v, a=a, force=force, omega=omega,
                       torque=t_motor, p_shaft=p_shaft, p_losses=p_loss, p_battery=p_batt,
                       outside=outside, summary=summary, balance=balance)
