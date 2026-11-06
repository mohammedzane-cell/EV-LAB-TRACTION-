"""Three-phase, double-layer, integral-slot lap winding (stage 7, tab 6).

Geometry: Z slots, 2p poles, m = 3 phases, coil pitch y (integer number of slots).
  q = Z/(2p·m) slots per pole and phase (integer), τ = Z/(2p) slots per pole,
  α = 2π·p/Z electrical angle between slots, 1 ≤ y ≤ τ.
Factors for the electrical harmonic ν (odd ν; even harmonics vanish by half-wave symmetry):
  kd_ν = sin(ν·q·α/2)/(q·sin(ν·α/2))   (distribution: phasor sum of the q slots of a belt)
  kp_ν = sin(ν·(y/τ)·π/2)               (pitch: the two sides of a coil are y slots apart)
  kw_ν = kd_ν·kp_ν
Slot table: phase belts A+ C− B+ A− C+ B− of q slots each in the top layer; the
bottom layer is the top layer shifted by y slots with the sign reversed (the
return side of each coil).
MMF: each slot carries its conductors at the slot centre; the phase MMF is the
staircase of Ampère's law (jump = slot current, zero mean). Its ν-th harmonic is
exactly ∝ kw_ν/ν, which the FFT checks.
Rotating field: F(θ, t) = Σ_k i_k(t)·N_k(θ) for balanced currents; its
fundamental keeps a constant amplitude 3/2·F_1,phase and turns at 2πf/p.
EMF: E = 4,44·f·N·kw1·Φ (RMS per phase).
Reference: Z = 36, 2p = 4, m = 3 → q = 3, τ = 9 slots, α = 20° el.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike

PHASES = ("A", "B", "C")
BELTS = (("A", 1), ("C", -1), ("B", 1), ("A", -1), ("C", 1), ("B", -1))  # 60° el. belts
PHASE_SHIFT = {"A": 0.0, "B": -2.0 * math.pi / 3.0, "C": -4.0 * math.pi / 3.0}  # balanced currents


def _int(name: str, x) -> int:
    if isinstance(x, bool) or not isinstance(x, (int, np.integer)) or x < 1:
        raise ValueError(f"{name} must be an integer >= 1, got {x!r}")
    return int(x)


@dataclass(frozen=True)
class Winding:
    """Winding geometry: z slots, poles = 2p, m phases (3), coil pitch y in slots."""

    z: int
    poles: int
    m: int
    y: int

    def __post_init__(self) -> None:
        _int("z", self.z)
        _int("poles", self.poles)
        if self.poles % 2:
            raise ValueError(f"poles (2p) must be even, got {self.poles}")
        _int("m", self.m)
        if self.m != 3:
            raise ValueError(f"only three-phase windings are handled (m = 3), got m = {self.m}")
        if self.z % (self.poles * self.m):
            raise ValueError(
                f"q = Z/(2p·m) = {self.z}/({self.poles}·{self.m}) = {self.z / (self.poles * self.m):g} "
                "must be an integer (integral-slot winding)"
            )
        tau = self.z // self.poles
        if isinstance(self.y, bool) or not isinstance(self.y, (int, np.integer)):
            lo, hi = math.floor(self.y), math.ceil(self.y)
            raise ValueError(
                f"coil pitch must be an integer number of slots, got y = {self.y!r}: with Z = {self.z} "
                f"and 2p = {self.poles} the pole pitch is τ = {tau} slots, so choose y = {lo} or y = {hi} "
                f"({lo}/{tau} or {hi}/{tau} pitch)"
            )
        if not 1 <= self.y <= tau:
            raise ValueError(f"coil pitch must satisfy 1 <= y <= τ = {tau} slots, got y = {self.y}")

    @property
    def pole_pairs(self) -> int:
        return self.poles // 2

    @property
    def q(self) -> int:
        """Slots per pole and phase."""
        return self.z // (self.poles * self.m)

    @property
    def tau(self) -> int:
        """Pole pitch, slots."""
        return self.z // self.poles

    @property
    def alpha(self) -> float:
        """Electrical angle between adjacent slots, rad: α = 2π·p/Z."""
        return 2.0 * math.pi * self.pole_pairs / self.z


def _nu(nu: ArrayLike) -> np.ndarray:
    n = np.asarray(nu)
    if not np.issubdtype(n.dtype, np.integer) or np.any(n < 1):
        raise ValueError(f"harmonic order ν must be an integer >= 1, got {nu!r}")
    return n


def _out(x: np.ndarray):
    return float(x) if np.ndim(x) == 0 else x


def distribution_factor(w: Winding, nu: ArrayLike = 1):
    """kd_ν = sin(ν·q·α/2)/(q·sin(ν·α/2)): the q slot EMFs of a belt add as phasors α apart."""
    n = _nu(nu)
    return _out(np.sin(n * w.q * w.alpha / 2.0) / (w.q * np.sin(n * w.alpha / 2.0)))


def pitch_factor(w: Winding, nu: ArrayLike = 1):
    """kp_ν = sin(ν·(y/τ)·π/2): a coil spanning y < τ slots links less than a full pole."""
    n = _nu(nu)
    return _out(np.sin(n * (w.y / w.tau) * math.pi / 2.0))


def winding_factor(w: Winding, nu: ArrayLike = 1):
    """kw_ν = kd_ν·kp_ν (signed: the sign is the harmonic's phase relative to the fundamental)."""
    return _out(np.asarray(distribution_factor(w, nu)) * np.asarray(pitch_factor(w, nu)))


@dataclass(frozen=True)
class Slot:
    """Top and bottom coil sides of a slot: (phase, sign ±1)."""

    top: tuple[str, int]
    bottom: tuple[str, int]

    def labels(self) -> tuple[str, str]:
        """("A+", "C−") style labels (Unicode minus)."""
        return tuple(f"{ph}{'+' if s > 0 else '−'}" for ph, s in (self.top, self.bottom))


def slot_table(w: Winding) -> list[Slot]:
    """Phase and sign of both layers of every slot: belts A+ C− B+ A− C+ B−; bottom = top shifted by y, reversed."""
    top = [BELTS[(s // w.q) % 6] for s in range(w.z)]
    bottom = [None] * w.z
    for s, (ph, sign) in enumerate(top):
        bottom[(s + w.y) % w.z] = (ph, -sign)
    return [Slot(top[s], bottom[s]) for s in range(w.z)]


def slot_conductors(w: Winding, phase: str, turns_per_coil: float = 1.0) -> np.ndarray:
    """Signed conductors of a phase in each slot (both layers), turns."""
    if phase not in PHASES:
        raise ValueError(f"phase must be one of {PHASES}, got {phase!r}")
    c = np.zeros(w.z)
    for s, slot in enumerate(slot_table(w)):
        for ph, sign in (slot.top, slot.bottom):
            if ph == phase:
                c[s] += sign * turns_per_coil
    return c


def phase_mmf(w: Winding, phase: str, n_theta: int = 36 * 64, turns_per_coil: float = 1.0,
              current: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Stepped MMF of one phase around the air gap: (θ mechanical, rad; F, A·turns), zero mean.

    Slot s sits at θ_s = 2π·s/Z; F jumps by i·(conductors of slot s) there. Samples
    are taken at mid-step positions θ_k = (k + ½)·2π/n_theta.
    """
    if not isinstance(n_theta, int) or n_theta < 2 * w.z:
        raise ValueError(f"n_theta must be an integer >= 2·Z = {2 * w.z}, got {n_theta!r}")
    theta = (np.arange(n_theta) + 0.5) * 2.0 * math.pi / n_theta
    c = slot_conductors(w, phase, turns_per_coil) * current
    slot_pos = 2.0 * math.pi * np.arange(w.z) / w.z
    passed = theta[:, None] > slot_pos[None, :]  # slots already crossed at θ
    f = passed.astype(float) @ c
    return theta, f - f.mean()


def mmf_spectrum(w: Winding, mmf: ArrayLike, nu_max: int = 25, normalise: bool = True) -> dict[int, float]:
    """Amplitude of each electrical harmonic ν = 1…nu_max of an MMF sampled over 2π mechanical (FFT bin p·ν).

    normalise=True divides by the fundamental.
    """
    f = np.asarray(mmf, dtype=float)
    if f.ndim != 1 or f.size < 2 * w.pole_pairs * nu_max + 2:
        raise ValueError("the MMF needs more samples than 2·p·nu_max")
    c = np.fft.rfft(f) * 2.0 / f.size
    amp = {nu: float(abs(c[w.pole_pairs * nu])) for nu in range(1, nu_max + 1)}
    if normalise:
        a1 = amp[1]
        if a1 == 0:
            raise ValueError("the MMF has no fundamental")
        amp = {nu: a / a1 for nu, a in amp.items()}
    return amp


def analytical_spectrum(w: Winding, nu_max: int = 25) -> dict[int, float]:
    """|kw_ν|/ν normalised to |kw_1| for odd ν, 0 for even ν: expected relative MMF harmonics of one phase.

    The A+ and A− belts are one pole pitch apart with opposite signs, so the phase
    MMF has half-wave symmetry F(θ + π/p) = −F(θ): every even harmonic is zero.
    The kd·kp formula holds for the odd harmonics only.
    """
    kw1 = abs(winding_factor(w, 1))
    return {nu: (abs(winding_factor(w, nu)) / nu / kw1 if nu % 2 else 0.0) for nu in range(1, nu_max + 1)}


@dataclass(frozen=True)
class RotatingField:
    """Air-gap MMF over one electrical period.

    Attributes:
        theta: mechanical angle, rad (n_theta).  t: time, s (n_t, period end excluded).
        currents: (3, n_t) phase currents A, B, C, A.  mmf: (n_t, n_theta), A·turns.
        fundamental: (n_t, n_theta) fundamental wave of mmf, A·turns.
        fundamental_amplitude: (n_t,), A·turns.  fundamental_position: (n_t,) angle of its
        positive peak, mechanical rad.
    """

    theta: np.ndarray
    t: np.ndarray
    currents: np.ndarray
    mmf: np.ndarray
    fundamental: np.ndarray
    fundamental_amplitude: np.ndarray
    fundamental_position: np.ndarray


def rotating_field(w: Winding, f: float = 50.0, current: float = 1.0, n_theta: int = 36 * 32,
                   n_t: int = 72, turns_per_coil: float = 1.0) -> RotatingField:
    """F(θ, t) = Σ_k i_k(t)·N_k(θ) for i_k = I·cos(ωt − 2πk/3), sampled over one electrical period.

    Args:
        w: winding.  f: frequency, Hz.  current: peak phase current, A.
        n_theta: angular samples.  n_t: time samples.  turns_per_coil: turns.
    """
    for name, x in (("f", f), ("current", current)):
        if not math.isfinite(x) or x <= 0:
            raise ValueError(f"{name} must be a finite number > 0, got {x!r}")
    if not isinstance(n_t, int) or n_t < 4:
        raise ValueError(f"n_t must be an integer >= 4, got {n_t!r}")
    t = np.arange(n_t) / (n_t * f)
    wt = 2.0 * math.pi * f * t
    currents = np.vstack([current * np.cos(wt + PHASE_SHIFT[ph]) for ph in PHASES])
    shapes = []
    for ph in PHASES:
        theta, n_k = phase_mmf(w, ph, n_theta, turns_per_coil, 1.0)
        shapes.append(n_k)
    mmf = currents.T @ np.vstack(shapes)
    c = np.fft.rfft(mmf, axis=1)[:, w.pole_pairs] * 2.0 / n_theta
    amp = np.abs(c)
    pos = np.mod(-np.angle(c) / w.pole_pairs, 2.0 * math.pi / w.pole_pairs)
    fund = amp[:, None] * np.cos(w.pole_pairs * theta[None, :] + np.angle(c)[:, None])
    return RotatingField(theta, t, currents, mmf, fund, amp, pos)


def emf(f: float, turns_per_phase: float, kw1: float, flux: float) -> float:
    """E = 4,44·f·N·kw1·Φ, V RMS per phase (4,44 = 2π/√2: sinusoidal flux Φ per pole, N series turns)."""
    for name, x in (("f", f), ("turns_per_phase", turns_per_phase), ("flux", flux)):
        if not math.isfinite(x) or x <= 0:
            raise ValueError(f"{name} must be a finite number > 0, got {x!r}")
    if not math.isfinite(kw1) or not 0 < abs(kw1) <= 1:
        raise ValueError(f"kw1 must be in (0, 1], got {kw1!r}")
    return 4.44 * f * turns_per_phase * abs(kw1) * flux


def turns_per_phase(w: Winding, turns_per_coil: float, parallel_paths: int = 1) -> float:
    """Series turns per phase of a double-layer winding: (Z/m coils)·N_c/a."""
    if not math.isfinite(turns_per_coil) or turns_per_coil <= 0:
        raise ValueError(f"turns_per_coil must be > 0, got {turns_per_coil!r}")
    a = _int("parallel_paths", parallel_paths)
    n = (w.z / w.m) * turns_per_coil / a
    return int(n) if float(n).is_integer() else n


def turns_from_conductors(total_conductors: int, m: int = 3) -> float:
    """Turns per phase from the total number of active conductors: Z_c/(2m) (2 conductors per turn)."""
    _int("total_conductors", total_conductors)
    _int("m", m)
    n = total_conductors / (2 * m)
    return int(n) if float(n).is_integer() else n


def pole_pairs_from_speed(f: float, omega_mech: float, tol: float = 1e-6) -> int:
    """p = 2πf/Ω for a synchronous speed Ω (rad/s); raises if the ratio is not an integer."""
    for name, x in (("f", f), ("omega_mech", omega_mech)):
        if not math.isfinite(x) or x <= 0:
            raise ValueError(f"{name} must be a finite number > 0, got {x!r}")
    p = 2.0 * math.pi * f / omega_mech
    if abs(p - round(p)) > tol * max(1.0, p):
        raise ValueError(f"2πf/Ω = {p:.4f} is not an integer: Ω is not a synchronous speed")
    return int(round(p))


MU_0 = 4.0e-7 * math.pi  # H/m


def carter_factor(slot_pitch: float, slot_opening: float, gap: float) -> float:
    """Carter's factor k_c = τ_s/(τ_s − γ·g): slot openings lengthen the effective air gap to k_c·g.

    γ = (4/π)·[(b/2g)·atan(b/2g) − ln √(1 + (b/2g)²)], b = slot opening (conformal mapping of a slot).

    Args:
        slot_pitch: slot pitch at the bore τ_s, m (> 0).
        slot_opening: slot opening b0, m (0 ≤ b0 < τ_s).
        gap: mechanical air gap g, m (> 0).
    """
    for name, x in (("slot_pitch", slot_pitch), ("gap", gap)):
        if not math.isfinite(x) or x <= 0:
            raise ValueError(f"{name} must be a finite number > 0 m, got {x!r}")
    if not math.isfinite(slot_opening) or not 0 <= slot_opening < slot_pitch:
        raise ValueError(f"slot_opening must be in [0, slot_pitch), got {slot_opening!r}")
    u = slot_opening / (2.0 * gap)
    gamma = (4.0 / math.pi) * (u * math.atan(u) - math.log(math.sqrt(1.0 + u * u)))
    return slot_pitch / (slot_pitch - gamma * gap)


def gap_flux_density(mmf: float, gap: float, carter: float = 1.0) -> float:
    """B = μ0·F/(k_c·g): air-gap flux density of an MMF across an effective gap, T (iron MMF neglected).

    Args:
        mmf: MMF amplitude across the gap, A·turns.  gap: air gap g, m (> 0).
        carter: Carter's factor k_c (≥ 1).
    """
    if not math.isfinite(gap) or gap <= 0:
        raise ValueError(f"gap must be a finite number > 0 m, got {gap!r}")
    if not math.isfinite(carter) or carter < 1:
        raise ValueError(f"carter must be >= 1, got {carter!r}")
    return MU_0 * mmf / (carter * gap)
