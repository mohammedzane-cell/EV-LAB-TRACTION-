"""V/f + field-weakening torque–speed envelope of the identified motor (stage 3, tab 2).

The motor is the Session's MotorParams (identified in tab 1); nothing here
invents a machine. For each stator frequency f:
  V(f) = V0 + (Vn − V0)·f/fn  for f ≤ fn   (V/f law, V0 = low-speed boost)
  V(f) = Vn                    for f > fn   (field weakening)
every reactance scales with f (core.circuit), and the drive may use
  T_avail(f) = min(T_I(f), margin·T_bd(f))
where T_I is the torque at which the stator current reaches i_max on the
stable branch (0 < g ≤ min(g_c, 1)), and T_bd is the breakdown torque at (V(f), f).
The operating slip at T_avail gives the speed Ω = Ω_s(f)·(1 − g). At very low
f the breakdown slip exceeds 1 (R1 dominates): the slip is then capped at 1
(standstill) and only the strongest standstill point is kept, so the envelope
starts at Ω = 0 with the starting torque.

The torques are electromagnetic (mechanical losses are handled by core.losses).
Zone boundaries are read from the computed curve, not imposed. The log–log
slope n = d ln T / d ln Ω is ≈ 0 at constant torque, ≈ −1 at constant power
(current limit, field weakening) and ≈ −2 when the breakdown torque limits:
  base speed            last speed before n drops below −0,5 (between the 0 and −1 laws)
  end of constant power first speed where margin·T_bd < T_I (the breakdown limit binds)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from evlab.core import circuit
from evlab.core.session import MotorParams

BISECTION_STEPS = 60  # slip bracket shrinks by 2^-60: below float resolution
SLOPE_KNEE = -0.5  # d ln T / d ln Ω halfway between constant torque (0) and constant power (−1)
F_MIN_RATIO = 0.01  # lowest stator frequency computed, × fn


@dataclass(frozen=True)
class DriveSettings:
    """Inverter limits and V/f law.

    Attributes:
        i_max: stator current limit, A (RMS, phase).
        boost: voltage at f → 0, V (phase); the law reaches Vn at fn.
        margin: usable fraction of the breakdown torque, in (0, 1].
        f_max: maximum stator frequency, Hz.
        n_points: frequencies computed (geometric below fn, linear above).
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


def breakdown_torque(m: MotorParams, f: ArrayLike, boost: float = 0.0) -> float | NDArray[np.float64]:
    """Breakdown torque T_bd at (V(f), f), N·m: circuit.max_torque on the V/f law.

    Args:
        m: motor.
        f: stator frequency, Hz, scalar or array.
        boost: V/f boost, V.
    """
    return circuit.max_torque(m, v_phase=vf_voltage(m, f, boost), f=f)


def _bisect_slip(fun, target: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """Vectorised bisection for fun(g) = target on [lo, hi], fun increasing."""
    lo, hi = lo.copy(), hi.copy()
    for _ in range(BISECTION_STEPS):
        mid = 0.5 * (lo + hi)
        below = fun(mid) < target
        lo = np.where(below, mid, lo)
        hi = np.where(below, hi, mid)
    return 0.5 * (lo + hi)


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
        torque_current: current-limited torque T_I, N·m.
        torque_breakdown: breakdown torque T_bd (without margin), N·m.
        slip_breakdown: breakdown slip g_c at (V, f).
        breakdown_binds: True where margin·T_bd < T_I (breakdown-limited).
        slope: log–log slope d ln T / d ln Ω (≈ 0, −1, −2 in zones 1, 2, 3; NaN at Ω = 0).
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
    breakdown_binds: np.ndarray
    slope: np.ndarray
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
    def torque_at_max_speed(self) -> float:
        """Available torque at the highest speed, N·m."""
        return float(self.torque[-1])

    def zone(self) -> np.ndarray:
        """Zone of each point: 1 constant torque, 2 constant power, 3 breakdown-limited."""
        z = np.full(self.omega.shape, 2)
        z[self.omega <= self.base_speed] = 1
        z[(self.omega > self.base_speed) & (self.omega >= self.end_constant_power) & self.breakdown_binds] = 3
        return z

    def torque_at(self, omega: ArrayLike) -> np.ndarray:
        """Available torque at given speeds (linear interpolation), N·m; NaN beyond the envelope."""
        om = np.asarray(omega, dtype=float)
        t = np.interp(om, self.omega, self.torque, left=np.nan, right=np.nan)
        return np.where((om >= 0) & (om < self.omega[0]), self.torque[0], t)


def envelope(m: MotorParams, settings: DriveSettings) -> Envelope:
    """Torque–speed envelope T(Ω), P(Ω) of the motor under the V/f law and the drive limits.

    Args:
        m: motor (the Session's identified MotorParams).
        settings: current limit, boost, margin, maximum frequency.
    """
    s = settings
    f_knee = min(m.f_rated, s.f_max)
    f = np.geomspace(F_MIN_RATIO * f_knee, f_knee, s.n_points // 2)
    if s.f_max > m.f_rated:
        f = np.concatenate([f, np.linspace(m.f_rated, s.f_max, s.n_points - s.n_points // 2)])
    f = np.unique(f)
    v = vf_voltage(m, f, s.boost)
    g_c = np.asarray(circuit.breakdown_slip(m, f=f))
    t_bd = np.asarray(circuit.max_torque(m, v_phase=v, f=f))

    i0 = np.asarray(circuit.stator_current(m, 0.0 * f, v_phase=v, f=f))
    if np.any(i0 >= s.i_max):
        k = int(np.argmax(i0 >= s.i_max))
        raise ValueError(
            f"no-load current {i0[k]:.2f} A at f = {f[k]:.2f} Hz reaches i_max = {s.i_max} A: "
            "raise the current limit or lower the boost"
        )

    def current(g: np.ndarray) -> np.ndarray:
        return np.asarray(circuit.stator_current(m, g, v_phase=v, f=f))

    def torque(g: np.ndarray) -> np.ndarray:
        return np.asarray(circuit.torque(m, g, v_phase=v, f=f))

    zero = np.zeros_like(f)
    g_hi = np.minimum(g_c, 1.0)  # stable branch, speed >= 0
    i_hi = current(g_hi)
    g_i = np.where(i_hi <= s.i_max, g_hi, _bisect_slip(current, np.full_like(f, s.i_max), zero, g_hi))
    t_i = torque(g_i)
    t_avail = np.minimum(t_i, s.margin * t_bd)
    breakdown_binds = s.margin * t_bd < t_i
    g_op = _bisect_slip(torque, t_avail, zero, g_hi)
    omega = np.asarray(circuit.mechanical_speed(m, g_op, f=f))
    # standstill (g = 1) can be reached at several low frequencies: keep the strongest
    standstill = g_op >= 1.0 - 1e-9
    keep = ~standstill
    if standstill.any():
        keep[np.nonzero(standstill)[0][np.argmax(torque(g_op)[standstill])]] = True
        omega = np.where(standstill, 0.0, omega)
    order = np.nonzero(keep)[0][np.argsort(omega[keep])]
    arr = {k: a[order] for k, a in dict(
        omega=omega, torque=torque(g_op), f=f, v=v, slip=g_op, i1=current(g_op),
        torque_current=t_i, torque_breakdown=t_bd, slip_breakdown=g_c, breakdown_binds=breakdown_binds,
    ).items()}
    t, om = arr["torque"], arr["omega"]
    slope = np.full(om.shape, np.nan)
    pos = om > 0
    if pos.sum() >= 3:
        slope[pos] = np.gradient(np.log(t[pos]), np.log(om[pos]))
    knee = np.nonzero(pos & (slope < SLOPE_KNEE))[0]
    base = float(om[knee[0] - 1]) if knee.size and knee[0] > 0 else float(om[-1])
    above = (om > base) & arr["breakdown_binds"]
    end_cp = float(om[np.argmax(above)]) if above.any() else float(om[-1])
    return Envelope(power=t * om, slope=slope, base_speed=base, end_constant_power=end_cp, settings=s, **arr)
