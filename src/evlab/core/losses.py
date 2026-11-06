"""Losses and efficiency map η(T, Ω) of the identified motor under the V/f law (stage 4, tab 3).

Same circuit, same drive as tab 2. For each grid point (shaft torque T, speed Ω)
the operating point is solved: rotor frequency f_r such that the circuit gives
T_em = T + P_mec(Ω)/Ω at stator frequency f = p·Ω/(2π) + f_r and V = V(f)
(core.drive.vf_voltage). At fixed Ω, T(f_r) rises to a peak then falls (raising
f_r raises f, deeper into field weakening). All points at once: a vectorised
golden-section search finds each peak, then a vectorised bisection on
[0, peak] finds the stable solution.

Loss terms (three-phase, W):
  copper   3·R1(T_w)·I1² (tp3; 3·R1·I'2² in the terminals layout) + 3·R'2·I'2²
           R1 corrected to the winding temperature T_w by the copper law
  iron     Steinmetz P_fe ∝ f^β·B² with B ∝ E/f, i.e. 3·E²/Rf·(f/fn)^(β−2):
           equal to the circuit at fn; implemented as Rf(f) = Rf·(f/fn)^(2−β)
           inside the circuit, so currents and losses stay consistent
  mech.    P_mec(Ω) = a·Ω + b·Ω², a·Ω_0 = s·p_mec, b·Ω_0² = (1 − s)·p_mec,
           p_mec from the no-load separation of tab 1 at Ω_0 = 2π·fn/p
           (circuit.efficiency leaves it out, assumption A10)
  inverter P_inv = P_0 + k·P_motor (démo values)
η = P_out/P_in with P_out = T·Ω (shaft) and P_in = P_motor + P_inv (DC side).
NaN outside the drive envelope.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np
from numpy.typing import ArrayLike

from evlab.core import circuit, drive
from evlab.core.identification import r1_at_temperature
from evlab.core.session import MotorParams

BISECTION_STEPS = 45  # rotor-frequency bracket (≤ ~25 Hz) shrinks below 1e-12 Hz
GOLDEN_STEPS = 40  # peak location to 0,618^40 ≈ 4e-9 of the bracket
INV_PHI = (math.sqrt(5.0) - 1.0) / 2.0


@dataclass(frozen=True)
class LossSettings:
    """Loss model options.

    Attributes:
        beta: Steinmetz frequency exponent of the iron losses, in (0, 3] (A19).
        winding_temperature_k: winding temperature for R1, K (None: R1 as identified).
        mechanical: include mechanical losses (p_mec of the motor).
        friction_share: share of p_mec(Ω_0) proportional to Ω (bearings); the rest ∝ Ω² (A20).
        inverter: include inverter losses.
        inverter_fixed_w: fixed inverter loss P_0, W (démo, A21).
        inverter_fraction: inverter loss proportional to the motor input power, k (démo, A21).
    """

    beta: float = 1.5
    winding_temperature_k: float | None = None
    mechanical: bool = True
    friction_share: float = 0.5
    inverter: bool = True
    inverter_fixed_w: float = 50.0
    inverter_fraction: float = 0.02

    def __post_init__(self) -> None:
        if not math.isfinite(self.beta) or not 0 < self.beta <= 3:
            raise ValueError(f"beta must be in (0, 3], got {self.beta!r}")
        if self.winding_temperature_k is not None and (
            not math.isfinite(self.winding_temperature_k) or self.winding_temperature_k <= 0
        ):
            raise ValueError(f"winding_temperature_k must be > 0 K, got {self.winding_temperature_k!r}")
        if not math.isfinite(self.friction_share) or not 0 <= self.friction_share <= 1:
            raise ValueError(f"friction_share must be in [0, 1], got {self.friction_share!r}")
        if not math.isfinite(self.inverter_fixed_w) or self.inverter_fixed_w < 0:
            raise ValueError(f"inverter_fixed_w must be >= 0 W, got {self.inverter_fixed_w!r}")
        if not math.isfinite(self.inverter_fraction) or not 0 <= self.inverter_fraction < 1:
            raise ValueError(f"inverter_fraction must be in [0, 1), got {self.inverter_fraction!r}")


def stator_resistance(m: MotorParams, st: LossSettings) -> float:
    """R1 at the winding temperature: R1·(234,5 + T_w)/(234,5 + T_id), Ω (copper law)."""
    if st.winding_temperature_k is None or m.r1 == 0:
        return m.r1
    if m.r1_temperature_k is None:
        raise ValueError("the motor has no r1_temperature_k: R1 cannot be corrected to the winding temperature")
    return r1_at_temperature(m.r1, m.r1_temperature_k, st.winding_temperature_k)


def iron_resistance(m: MotorParams, f: ArrayLike, st: LossSettings) -> float | np.ndarray:
    """Rf(f) = Rf·(f/fn)^(2−β), Ω: makes 3·E²/Rf(f) follow the Steinmetz law f^β·B², B ∝ E/f."""
    r = m.r_fe * (np.asarray(f, dtype=float) / m.f_rated) ** (2.0 - st.beta)
    return float(r) if np.ndim(r) == 0 else r


def mechanical_loss(m: MotorParams, omega: ArrayLike, st: LossSettings) -> float | np.ndarray:
    """P_mec(Ω) = a·Ω + b·Ω², W: friction ∝ Ω, windage ∝ Ω², equal to p_mec at Ω_0 = 2π·fn/p."""
    om = np.asarray(omega, dtype=float)
    if not st.mechanical or m.p_mech == 0:
        p = np.zeros_like(om)
    else:
        w0 = 2.0 * math.pi * m.f_rated / m.pole_pairs
        a = st.friction_share * m.p_mech / w0
        b = (1.0 - st.friction_share) * m.p_mech / w0**2
        p = a * om + b * om**2
    return float(p) if p.ndim == 0 else p


def shaft_torque_limit(m: MotorParams, env: drive.Envelope, st: LossSettings) -> np.ndarray:
    """Shaft torque available along the envelope: T_em − P_mec(Ω)/Ω, N·m (T_em at Ω = 0)."""
    om = env.omega
    p = np.asarray(mechanical_loss(m, om, st))
    return env.torque - np.divide(p, om, out=np.zeros_like(om), where=om > 0)


@dataclass(frozen=True)
class EfficiencyMap:
    """η(T, Ω) and every loss term on the grid; arrays have shape (len(torque), len(speed)).

    Attributes:
        torque: shaft torque grid, N·m.
        speed: speed grid, rad/s.
        valid: True inside the envelope (all other arrays are NaN outside).
        eta: efficiency P_out/P_in.
        p_out: shaft power, W.   p_in: DC input power (motor + inverter), W.
        p_cu1, p_cu2, p_fe, p_mech, p_inv: loss terms, W.
        f: stator frequency, Hz.   v: phase voltage, V.   slip: slip.
        i1: stator current, A.
        envelope: drive envelope used for the boundary.
        settings: loss settings used.
    """

    torque: np.ndarray
    speed: np.ndarray
    valid: np.ndarray
    eta: np.ndarray
    p_out: np.ndarray
    p_in: np.ndarray
    p_cu1: np.ndarray
    p_cu2: np.ndarray
    p_fe: np.ndarray
    p_mech: np.ndarray
    p_inv: np.ndarray
    f: np.ndarray
    v: np.ndarray
    slip: np.ndarray
    i1: np.ndarray
    envelope: drive.Envelope
    settings: LossSettings


def _grid(name: str, x: ArrayLike, strict: bool) -> np.ndarray:
    a = np.asarray(x, dtype=float)
    if a.ndim != 1 or a.size == 0:
        raise ValueError(f"{name} grid must be a non-empty 1-D array, got shape {a.shape}")
    if not np.all(np.isfinite(a)) or (np.any(a <= 0) if strict else np.any(a < 0)):
        raise ValueError(f"{name} grid must be finite and {'> 0' if strict else '>= 0'}")
    return a


def efficiency_map(
    m: MotorParams,
    torque: ArrayLike,
    speed: ArrayLike,
    drive_settings: drive.DriveSettings,
    settings: LossSettings = LossSettings(),
    envelope: drive.Envelope | None = None,
) -> EfficiencyMap:
    """Efficiency and losses at every (shaft torque, speed) point under the V/f law.

    Args:
        m: motor (the Session's identified MotorParams).
        torque: shaft torque grid, N·m (≥ 0), 1-D.
        speed: speed grid, rad/s (> 0), 1-D.
        drive_settings: V/f law and limits (same as tab 2).
        settings: loss model.
        envelope: precomputed core.drive.envelope(m, drive_settings), optional.
    """
    t_grid = _grid("torque", torque, strict=False)
    w_grid = _grid("speed", speed, strict=True)
    env = envelope if envelope is not None else drive.envelope(m, drive_settings)
    mt = replace(m, r1=stator_resistance(m, settings))
    tt, ww = np.meshgrid(t_grid, w_grid, indexing="ij")
    p_mec = np.asarray(mechanical_loss(m, ww, settings))
    t_em = tt + p_mec / ww

    f_mech = m.pole_pairs * ww / (2.0 * math.pi)
    # bracket past the torque peak at this speed (from the envelope), below the frequency cap
    fr_bd = np.minimum(1.5 * np.interp(ww, env.omega, env.rotor_freq_peak),
                       np.maximum(drive_settings.f_max - f_mech, 1e-9))
    valid = (ww <= env.omega_max) & (t_em <= np.nan_to_num(env.torque_at(ww), nan=-1.0) * (1 + 1e-9))

    boost = drive_settings.boost

    def solve(fr: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        f = f_mech + fr
        return fr / f, drive.vf_voltage(m, f, boost), f, iron_resistance(m, f, settings)

    def torque_at(fr: np.ndarray) -> np.ndarray:
        g, v, f, rfe = solve(fr)
        return np.asarray(circuit.torque(mt, g, v_phase=v, f=f, r_fe=rfe))

    # peak of T(f_r) at fixed Ω: vectorised golden-section search on [0, fr_bd]
    a, b = np.zeros_like(ww), fr_bd.copy()
    c, d = b - INV_PHI * (b - a), a + INV_PHI * (b - a)
    tc, td = torque_at(c), torque_at(d)
    for _ in range(GOLDEN_STEPS):
        left = tc > td  # peak in [a, d]
        a, b = np.where(left, a, c), np.where(left, d, b)
        c_new, d_new = b - INV_PHI * (b - a), a + INV_PHI * (b - a)
        c, d = np.where(left, c_new, d), np.where(left, c, d_new)
        tc, td = np.where(left, torque_at(c), td), np.where(left, tc, torque_at(d))
    fr_peak = 0.5 * (a + b)
    valid &= torque_at(fr_peak) >= t_em
    lo = np.zeros_like(ww)
    hi = fr_peak
    for _ in range(BISECTION_STEPS):
        mid = 0.5 * (lo + hi)
        below = torque_at(mid) < t_em
        lo = np.where(below, mid, lo)
        hi = np.where(below, hi, mid)
    g, v, f, rfe = solve(0.5 * (lo + hi))
    op = circuit.operating_point(mt, g, v_phase=v, f=f, r_fe=rfe)

    p_motor = np.asarray(op.p_in)
    p_out = np.asarray(op.p_mech) - p_mec  # shaft power of the solved point: balance is exact
    p_inv = (settings.inverter_fixed_w + settings.inverter_fraction * p_motor) if settings.inverter \
        else np.zeros_like(p_motor)
    p_in = p_motor + p_inv
    valid &= (p_out > 0) & (p_in > 0)

    def mask(a) -> np.ndarray:
        return np.where(valid, np.asarray(a, dtype=float), np.nan)

    return EfficiencyMap(
        torque=t_grid, speed=w_grid, valid=valid,
        eta=mask(np.divide(p_out, p_in, out=np.zeros_like(p_in), where=p_in > 0)),
        p_out=mask(p_out), p_in=mask(p_in), p_cu1=mask(op.p_cu1), p_cu2=mask(op.p_cu2),
        p_fe=mask(op.p_fe), p_mech=mask(p_mec), p_inv=mask(p_inv),
        f=mask(f), v=mask(v), slip=mask(g), i1=mask(op.i1),
        envelope=env, settings=settings,
    )


def default_grid(m: MotorParams, env: drive.Envelope, st: LossSettings,
                 n_torque: int = 160, n_speed: int = 120) -> tuple[np.ndarray, np.ndarray]:
    """Map grid covering the envelope: shaft torque 1 %…105 % of its maximum, speed 1 %…100 % of Ω_max.

    Args:
        m: motor.  env: drive envelope.  st: loss settings (for the shaft torque limit).
        n_torque, n_speed: grid sizes (≥ 2).

    Returns:
        (torque grid in N·m, speed grid in rad/s).
    """
    if n_torque < 2 or n_speed < 2:
        raise ValueError(f"grid sizes must be >= 2, got {n_torque} × {n_speed}")
    t_max = float(np.max(shaft_torque_limit(m, env, st)))
    return (np.linspace(0.01 * t_max, 1.05 * t_max, n_torque),
            np.linspace(0.01 * env.omega_max, env.omega_max, n_speed))


def best_point(emap: "EfficiencyMap") -> tuple[float, float, float]:
    """(η max, shaft torque in N·m, speed in rad/s) of the best point of the map."""
    if not emap.valid.any():
        raise ValueError("the map has no point inside the envelope")
    k = int(np.nanargmax(emap.eta))
    i, j = np.unravel_index(k, emap.eta.shape)
    return float(emap.eta[i, j]), float(emap.torque[i]), float(emap.speed[j])
