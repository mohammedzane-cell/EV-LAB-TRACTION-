"""V/f + field-weakening torque–speed envelope of the identified motor (stage 3, tab 2).

The motor is the Session's MotorParams (identified in tab 1); nothing here
invents a machine. For each stator frequency f:
  V(f) = V0 + (Vn − V0)·f/fn  for f ≤ fn   (V/f law, V0 = low-speed boost)
  V(f) = Vn                    for f > fn   (field weakening)
and every reactance scales with f (core.circuit).

The envelope is computed per speed Ω. At fixed Ω the drive chooses the rotor
frequency f_r (stator frequency f = p·Ω/2π + f_r, slip g = f_r/f). On the
stable side of T(f_r) the torque, the current and the use of the breakdown
torque all increase with f_r, so the available torque is T at the smallest of
  f_r,peak     maximum of T(f_r) at this speed (the speed's own breakdown)
  f_r,I        current reaches i_max
  f_r,M        T reaches margin·T_bd(f), the breakdown torque at the stator frequency
  f_max − pΩ/2π  frequency cap
i.e. T_avail = min(current-limited torque, margin·breakdown torque), the
torques being taken at the same speed. Solved for all speeds at once by a
vectorised golden-section search (peak) and bisections. The envelope ends where
the frequency cap starts to bind (stator frequency = f_max).

The torques are electromagnetic (mechanical losses are handled by core.losses).
Zone boundaries are read from the computed curve, not imposed. The log–log
slope n = d ln T / d ln Ω is ≈ 0 at constant torque, ≈ −1 at constant power
(current limit, field weakening) and steeper when the breakdown limits:
  base speed            last speed before n drops below −0,5 (between the 0 and −1 laws)
  end of constant power first speed above base where the breakdown limit binds
                        (margin·T_bd or the speed's own torque peak)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from evlab.core import circuit
from evlab.core.session import MotorParams

BISECTION_STEPS = 60  # bracket shrinks by 2^-60: below float resolution
GOLDEN_STEPS = 60  # 0,618^60 ≈ 3e-13 of the bracket
INV_PHI = (math.sqrt(5.0) - 1.0) / 2.0
BINDING = ("current", "margin", "peak", "frequency")
SLOPE_KNEE = -0.5  # d ln T / d ln Ω halfway between constant torque (0) and constant power (−1)
F_MIN_RATIO = 0.01  # lowest stator frequency used by the drive, × fn (A17)


@dataclass(frozen=True)
class DriveSettings:
    """Inverter limits and V/f law.

    Attributes:
        i_max: stator current limit, A (RMS, phase).
        boost: voltage at f → 0, V (phase); the law reaches Vn at fn.
        margin: usable fraction of the breakdown torque, in (0, 1].
        f_max: maximum stator frequency, Hz.
        n_points: speeds computed, from 0 to the synchronous speed at f_max.
    """

    i_max: float
    boost: float = 0.0
    margin: float = 0.8
    f_max: float = 100.0
    n_points: int = 400

    def __post_init__(self) -> None:
        for name in ("i_max", "f_max"):
            v = getattr(self, name)
            if not math.isfinite(v) or v <= 0:
                raise ValueError(f"{name} must be a finite number > 0, got {v!r}")
        if not math.isfinite(self.boost) or self.boost < 0:
            raise ValueError(f"boost must be a finite number >= 0 V, got {self.boost!r}")
        if not math.isfinite(self.margin) or not 0 < self.margin <= 1:
            raise ValueError(f"margin must be in (0, 1], got {self.margin!r}")
        if not isinstance(self.n_points, int) or self.n_points < 10:
            raise ValueError(f"n_points must be an integer >= 10, got {self.n_points!r}")


DEMO_SETTINGS = {"i_max": 20.0, "boost": 0.0, "margin": 0.8, "f_max": 100.0}  # docs/assumptions.md A16


def demo_settings(n_points: int = 400) -> DriveSettings:
    """Démo drive settings of A16 (i_max 20 A, boost 0 V, margin 0,8, f_max 100 Hz): TD5/TP3 give no inverter rating.

    Args:
        n_points: speeds computed by the envelope (resolution, not a démo value).
    """
    return DriveSettings(n_points=n_points, **DEMO_SETTINGS)


def demo_fields(s: DriveSettings) -> tuple[str, ...]:
    """Fields of s still at their A16 démo value (one flag per field; n_points is not a setting)."""
    return tuple(name for name, value in DEMO_SETTINGS.items() if getattr(s, name) == value)


def vf_voltage(m: MotorParams, f: ArrayLike, boost: float = 0.0) -> float | NDArray[np.float64]:
    """V(f) = V0 + (Vn − V0)·f/fn up to fn, then Vn: constant flux, then field weakening, V.

    Args:
        m: motor (Vn = m.v_phase, fn = m.f_rated).
        f: stator frequency, Hz (> 0), scalar or array.
        boost: V0, voltage at f → 0, V, in [0, Vn).
    """
    ff = np.asarray(f, dtype=float)
    if not np.all(np.isfinite(ff)) or np.any(ff <= 0):
        raise ValueError(f"f must be finite and > 0 Hz, got {f!r}")
    if not math.isfinite(boost) or not 0 <= boost < m.v_phase:
        raise ValueError(f"boost must be in [0, Vn = {m.v_phase} V), got {boost!r}")
    v = np.where(ff < m.f_rated, boost + (m.v_phase - boost) * ff / m.f_rated, m.v_phase)
    return float(v) if v.ndim == 0 else v


def rated_emf(m: MotorParams) -> float:
    """E_n = |E| at the rated no-load point (g = 0, V = Vn, f = fn): the rated air-gap EMF, V.

    E is the voltage across the magnetising branch (V − R1·I1 in the tp3 layout, V in the
    terminals layout); E/f measures the air-gap flux.
    """
    return float(circuit.operating_point(m, 0.0).e)


def flux_ratio(m: MotorParams, e: ArrayLike, f: ArrayLike) -> float | NDArray[np.float64]:
    """Air-gap flux relative to rated, (E/f)/(E_n/fn) (dimensionless; 1 = rated flux).

    Args:
        m: motor.  e: air-gap EMF |E|, V (≥ 0).  f: stator frequency, Hz (> 0).
    """
    ee, ff = np.asarray(e, dtype=float), np.asarray(f, dtype=float)
    if not np.all(np.isfinite(ee)) or np.any(ee < 0):
        raise ValueError(f"e must be finite and >= 0 V, got {e!r}")
    if not np.all(np.isfinite(ff)) or np.any(ff <= 0):
        raise ValueError(f"f must be finite and > 0 Hz, got {f!r}")
    r = (ee / ff) / (rated_emf(m) / m.f_rated)
    return float(r) if r.ndim == 0 else r


def breakdown_torque(m: MotorParams, f: ArrayLike, boost: float = 0.0) -> float | NDArray[np.float64]:
    """Breakdown torque T_bd at (V(f), f), N·m: circuit.max_torque on the V/f law.

    Args:
        m: motor.
        f: stator frequency, Hz, scalar or array.
        boost: V/f boost, V.
    """
    return circuit.max_torque(m, v_phase=vf_voltage(m, f, boost), f=f)


def _bisect(fun, target: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """Vectorised bisection for fun(x) = target on [lo, hi], fun increasing, fun(lo) < target."""
    lo, hi = lo.copy(), hi.copy()
    for _ in range(BISECTION_STEPS):
        mid = 0.5 * (lo + hi)
        below = fun(mid) < target
        lo = np.where(below, mid, lo)
        hi = np.where(below, hi, mid)
    return 0.5 * (lo + hi)


def _golden_max(fun, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """Vectorised golden-section search for the maximum of a unimodal fun on [lo, hi]."""
    a, b = lo.copy(), hi.copy()
    c, d = b - INV_PHI * (b - a), a + INV_PHI * (b - a)
    fc, fd = fun(c), fun(d)
    for _ in range(GOLDEN_STEPS):
        left = fc > fd
        a, b = np.where(left, a, c), np.where(left, d, b)
        c_new, d_new = b - INV_PHI * (b - a), a + INV_PHI * (b - a)
        c, d = np.where(left, c_new, d), np.where(left, c, d_new)
        fc, fd = np.where(left, fun(c), fd), np.where(left, fc, fun(d))
    return 0.5 * (a + b)


@dataclass(frozen=True)
class Envelope:
    """Torque–speed envelope, sorted by speed (arrays of equal length; SI).

    Attributes:
        omega: rotor speed, rad/s.
        torque: available electromagnetic torque, N·m.
        power: torque·omega, W.
        f: stator frequency, Hz.
        v: stator phase voltage, V.
        slip: operating slip at the available torque.
        i1: stator current at the available torque, A.
        torque_current: current-limited torque T_I at this speed, N·m (NaN where i_max is never reached).
        torque_breakdown: breakdown torque T_bd at the operating stator frequency (no margin), N·m.
        slip_breakdown: breakdown slip g_c at the operating stator frequency.
        rotor_freq_peak: rotor frequency of the torque maximum at this speed, Hz.
        binding: limit that sets the torque: "current", "margin", "peak" or "frequency".
        breakdown_binds: True where the breakdown limits ("margin" or "peak").
        slope: log–log slope d ln T / d ln Ω (≈ 0, −1, −2 in zones 1, 2, 3; NaN at Ω = 0).
        emf: air-gap EMF |E| at the available torque, V.
        flux: air-gap flux (E/f)/(E_n/fn), the worse of the full-torque point and the no-load
            point (g = 0) at the same V and f: a boost over-fluxes most at light load (A33).
        base_speed: end of the constant-torque zone, rad/s.
        end_constant_power: start of the breakdown-limited zone, rad/s
            (= omega[-1] if the breakdown limit never binds).
        settings: the drive settings used.
    """

    omega: np.ndarray
    torque: np.ndarray
    power: np.ndarray
    f: np.ndarray
    v: np.ndarray
    slip: np.ndarray
    i1: np.ndarray
    torque_current: np.ndarray
    torque_breakdown: np.ndarray
    slip_breakdown: np.ndarray
    rotor_freq_peak: np.ndarray
    binding: np.ndarray
    breakdown_binds: np.ndarray
    slope: np.ndarray
    emf: np.ndarray
    flux: np.ndarray
    base_speed: float
    end_constant_power: float
    settings: DriveSettings

    @property
    def omega_max(self) -> float:
        """Highest speed of the envelope, rad/s."""
        return float(self.omega[-1])

    @property
    def p_max(self) -> float:
        """Maximum power on the envelope, W."""
        return float(self.power.max())

    @property
    def max_flux_ratio(self) -> float:
        """Highest air-gap flux ratio (E/f)/(E_n/fn) along the envelope (dimensionless)."""
        return float(np.max(self.flux))

    @property
    def speed_of_max_flux(self) -> float:
        """Speed where the flux ratio is highest, rad/s."""
        return float(self.omega[int(np.argmax(self.flux))])

    @property
    def torque_at_max_speed(self) -> float:
        """Available torque at the highest speed, N·m."""
        return float(self.torque[-1])

    def zone(self) -> np.ndarray:
        """Zone of each point: 1 constant torque, 2 constant power, 3 breakdown-limited."""
        z = np.full(self.omega.shape, 2)
        z[self.omega <= self.base_speed] = 1
        z[(self.omega > self.base_speed) & (self.omega >= self.end_constant_power) & self.breakdown_binds] = 3
        if z.size > 1 and self.binding[-1] == "frequency":
            z[-1] = z[-2]  # the end point (frequency cap) belongs to the zone it ends
        return z

    def torque_at(self, omega: ArrayLike) -> np.ndarray:
        """Available torque at given speeds (linear interpolation), N·m; NaN beyond the envelope."""
        om = np.asarray(omega, dtype=float)
        return np.interp(om, self.omega, self.torque, left=np.nan, right=np.nan)


def envelope(m: MotorParams, settings: DriveSettings) -> Envelope:
    """Torque–speed envelope T(Ω), P(Ω) of the motor under the V/f law and the drive limits.

    Args:
        m: motor (the Session's identified MotorParams).
        settings: current limit, boost, margin, maximum frequency.
    """
    s = settings
    p = m.pole_pairs
    omega_sync_max = 2.0 * math.pi * s.f_max / p
    om = np.linspace(0.0, omega_sync_max, s.n_points + 1)[:-1]
    f_mech = p * om / (2.0 * math.pi)

    # rotor-frequency bracket: past the torque peak at every speed, below the frequency cap
    f_scan = np.linspace(s.f_max / 200.0, s.f_max, 200)
    fr_scan = float(np.max(np.minimum(np.asarray(circuit.breakdown_slip(m, f=f_scan)), 1.0) * f_scan))
    cap = s.f_max - f_mech
    hi = np.minimum(1.5 * fr_scan, cap)
    lo = np.maximum(F_MIN_RATIO * m.f_rated - f_mech, 1e-9 * fr_scan)  # stator frequency >= f_min

    def state(fr: np.ndarray):
        f = f_mech + fr
        return fr / f, vf_voltage(m, f, s.boost), f

    def torque(fr: np.ndarray) -> np.ndarray:
        g, v, f = state(fr)
        return np.asarray(circuit.torque(m, g, v_phase=v, f=f))

    def current(fr: np.ndarray) -> np.ndarray:
        g, v, f = state(fr)
        return np.asarray(circuit.stator_current(m, g, v_phase=v, f=f))

    def margin_use(fr: np.ndarray) -> np.ndarray:
        g, v, f = state(fr)
        return torque(fr) - s.margin * np.asarray(circuit.max_torque(m, v_phase=v, f=f))

    _, v0, f0 = state(lo)
    i0 = np.asarray(circuit.stator_current(m, 0.0 * om, v_phase=v0, f=np.maximum(f0, 1e-9)))
    if np.any(i0 >= s.i_max):
        k = int(np.argmax(i0 >= s.i_max))
        raise ValueError(
            f"no-load current {i0[k]:.2f} A at f = {f0[k]:.2f} Hz reaches i_max = {s.i_max} A: "
            "raise the current limit or lower the boost"
        )

    fr_peak = _golden_max(torque, lo, hi)
    i_peak = current(fr_peak)
    fr_i = np.where(i_peak <= s.i_max, fr_peak, _bisect(current, np.full_like(om, s.i_max), lo, fr_peak))
    m_peak = margin_use(fr_peak)
    fr_m = np.where(m_peak <= 0, fr_peak, _bisect(margin_use, np.zeros_like(om), lo, fr_peak))
    candidates = np.vstack([fr_i, fr_m, fr_peak, cap])
    fr_op = candidates.min(axis=0)
    binding = np.array(BINDING)[np.argmin(np.vstack([fr_i, fr_m, fr_peak + 1e-12 * fr_scan, cap]), axis=0)]
    # a limit that coincides with the peak is reported as the peak
    binding = np.where((binding != "frequency") & np.isclose(fr_op, fr_peak, rtol=1e-9), "peak", binding)
    binding = np.where(np.isclose(fr_op, cap, rtol=1e-12), "frequency", binding)

    # the envelope ends where the stator frequency reaches f_max
    capped = np.nonzero(binding == "frequency")[0]
    end = int(capped[0]) + 1 if capped.size else om.size
    sl = slice(0, end)
    g_op, v_op, f_op = (a[sl] for a in state(fr_op))
    t_op = torque(fr_op)[sl]
    om = om[sl]
    t_i = np.where(i_peak[sl] <= s.i_max, np.nan, torque(fr_i)[sl])
    t_bd = np.asarray(circuit.max_torque(m, v_phase=v_op, f=f_op))
    g_c = np.asarray(circuit.breakdown_slip(m, f=f_op))
    binding = binding[sl]
    breakdown_binds = (binding == "margin") | (binding == "peak")

    slope = np.full(om.shape, np.nan)
    pos = om > 0
    if pos.sum() >= 3:
        slope[pos] = np.gradient(np.log(np.maximum(t_op[pos], 1e-300)), np.log(om[pos]))
    knee = np.nonzero(pos & (slope < SLOPE_KNEE) & (binding != "frequency"))[0]
    base = float(om[knee[0] - 1]) if knee.size and knee[0] > 0 else float(om[-1])
    above = (om > base) & breakdown_binds
    end_cp = float(om[np.argmax(above)]) if above.any() else float(om[-1])
    emf = np.asarray(circuit.operating_point(m, g_op, v_phase=v_op, f=f_op).e)
    emf_0 = np.asarray(circuit.operating_point(m, np.zeros_like(g_op), v_phase=v_op, f=f_op).e)
    flux = np.maximum(np.asarray(flux_ratio(m, emf, f_op)), np.asarray(flux_ratio(m, emf_0, f_op)))
    return Envelope(
        omega=om, torque=t_op, power=t_op * om, f=f_op, v=v_op, slip=g_op,
        i1=np.asarray(circuit.stator_current(m, g_op, v_phase=v_op, f=f_op)),
        torque_current=t_i, torque_breakdown=t_bd, slip_breakdown=g_c,
        rotor_freq_peak=fr_peak[sl], binding=binding, breakdown_binds=breakdown_binds,
        slope=slope, emf=emf, flux=flux, base_speed=base, end_constant_power=end_cp, settings=s,
    )
