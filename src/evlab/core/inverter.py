"""Three-phase two-level voltage-source inverter: DC-link limit, average-value losses, SVPWM. Pure physics, no Qt.

Average-value model over one fundamental period (the switching ripple is not resolved):

- Output limit. With a DC link V_dc the largest fundamental phase voltage (RMS) in the linear range is
  V_dc/(2√2) for sine-triangle PWM (m ≤ 1) and V_dc/√6 for SVPWM (m ≤ 2/√3); m = Û_ph/(V_dc/2).
- Conduction losses of one IGBT and one diode for a sinusoidal current Î·sin(θ − φ) and duty
  d = (1 + m·sin θ)/2 (standard closed forms, e.g. Semikron Application Manual, § 5.1):
    P_T = V_CE0·Î·(1/2π + m·cos φ/8) + r_CE·Î²·(1/8 + m·cos φ/3π)
    P_D = V_F0·Î·(1/2π − m·cos φ/8) + r_F·Î²·(1/8 − m·cos φ/3π)
- Switching losses, linear in current and voltage around the datasheet point (V_ref, I_ref):
    P_sw,T = f_sw·(E_on + E_off)·(Î/(π·I_ref))·(V_dc/V_ref),   P_sw,D = f_sw·E_rr·(Î/(π·I_ref))·(V_dc/V_ref)
- Whole inverter: 6 × (P_T + P_D + P_sw,T + P_sw,D).
  The same closed forms are used for SVPWM (their zero-sequence term changes the split between
  IGBT and diode by a few percent; neglected, see docs/assumptions.md A36).
- SVPWM: sector and dwell times of the two active vectors and of the zero vectors for a reference
  (v_α, v_β); a reference outside the linear hexagon (|v| > V_dc/√3) is refused, never clipped.

Parameters are those of an IGBT module datasheet; the démo values are typical orders of magnitude of
a 1200 V / 50 A module (A35), not a specific part. SI units: V, A, Ω, J, Hz, W, s.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import ArrayLike

Modulation = Literal["svpwm", "spwm"]
SQRT3 = math.sqrt(3.0)


@dataclass(frozen=True)
class InverterParams:
    """Inverter datasheet parameters (SI).

    Attributes:
        v_dc: DC-link voltage, V.
        f_sw: switching frequency, Hz.
        v_ce0, r_ce: IGBT on-state threshold voltage (V) and slope resistance (Ω).
        v_f0, r_f: diode forward threshold voltage (V) and slope resistance (Ω).
        e_on_off: IGBT turn-on + turn-off energy at (v_ref, i_ref), J.
        e_rr: diode reverse-recovery energy at (v_ref, i_ref), J.
        v_ref, i_ref: datasheet test voltage (V) and current (A) of the switching energies.
        modulation: "svpwm" (default) or "spwm".
        is_demo: True for assumed values (labelled « démo »).
    """

    v_dc: float
    f_sw: float
    v_ce0: float
    r_ce: float
    v_f0: float
    r_f: float
    e_on_off: float
    e_rr: float
    v_ref: float
    i_ref: float
    modulation: Modulation = "svpwm"
    is_demo: bool = False

    def __post_init__(self) -> None:
        for name in ("v_dc", "f_sw", "v_ref", "i_ref"):
            x = getattr(self, name)
            if not math.isfinite(x) or x <= 0:
                raise ValueError(f"{name} must be a finite number > 0, got {x!r}")
        for name in ("v_ce0", "r_ce", "v_f0", "r_f", "e_on_off", "e_rr"):
            x = getattr(self, name)
            if not math.isfinite(x) or x < 0:
                raise ValueError(f"{name} must be a finite number >= 0, got {x!r}")
        if self.modulation not in ("svpwm", "spwm"):
            raise ValueError(f"modulation must be 'svpwm' or 'spwm', got {self.modulation!r}")


DEMO_A35 = dict(v_dc=600.0, f_sw=10e3, v_ce0=0.8, r_ce=0.018, v_f0=0.9, r_f=0.015,
                e_on_off=8e-3, e_rr=3.5e-3, v_ref=600.0, i_ref=50.0)


def demo_inverter(v_dc: float = DEMO_A35["v_dc"], f_sw: float = DEMO_A35["f_sw"]) -> InverterParams:
    """Démo inverter (A35): typical 1200 V / 50 A IGBT module orders of magnitude, SVPWM."""
    return InverterParams(**{**DEMO_A35, "v_dc": v_dc, "f_sw": f_sw}, modulation="svpwm", is_demo=True)


def max_modulation(modulation: Modulation) -> float:
    """Largest modulation index of the linear range: 1 (SPWM) or 2/√3 (SVPWM)."""
    return 2.0 / SQRT3 if modulation == "svpwm" else 1.0


def max_phase_voltage(p: InverterParams) -> float:
    """Largest fundamental phase voltage (RMS, V) in the linear range: V_dc/√6 (SVPWM) or V_dc/(2√2) (SPWM)."""
    return max_modulation(p.modulation) * p.v_dc / (2.0 * math.sqrt(2.0))


def required_dc_voltage(v_phase: ArrayLike, modulation: Modulation = "svpwm") -> np.ndarray | float:
    """Smallest DC-link voltage (V) whose linear range reaches a phase voltage (RMS, V): the inverse of
    max_phase_voltage, √6·V_ph for SVPWM and 2√2·V_ph for SPWM."""
    if modulation not in ("svpwm", "spwm"):
        raise ValueError(f"modulation must be 'svpwm' or 'spwm', got {modulation!r}")
    v = np.asarray(v_phase, dtype=float)
    if np.any(~np.isfinite(v)) or np.any(v < 0):
        raise ValueError("phase voltage must be finite and >= 0 V")
    out = 2.0 * math.sqrt(2.0) * v / max_modulation(modulation)
    return float(out) if out.ndim == 0 else out


def modulation_index(p: InverterParams, v_phase: ArrayLike) -> np.ndarray | float:
    """m = Û_ph/(V_dc/2) for a phase voltage (RMS, V). Refuses a voltage beyond the linear range."""
    v = np.asarray(v_phase, dtype=float)
    if np.any(~np.isfinite(v)) or np.any(v < 0):
        raise ValueError("phase voltage must be finite and >= 0 V")
    m = 2.0 * math.sqrt(2.0) * v / p.v_dc
    if np.any(m > max_modulation(p.modulation) * (1 + 1e-9)):
        raise ValueError(f"phase voltage above the linear range of the inverter: max "
                         f"{max_phase_voltage(p):.4g} V RMS for V_dc = {p.v_dc:.4g} V ({p.modulation})")
    return float(m) if m.ndim == 0 else m


@dataclass(frozen=True)
class InverterLosses:
    """Losses of the whole three-phase inverter, W (arrays when the inputs are arrays)."""

    conduction_igbt: np.ndarray | float
    conduction_diode: np.ndarray | float
    switching_igbt: np.ndarray | float
    switching_diode: np.ndarray | float
    total: np.ndarray | float


def losses(p: InverterParams, i_rms: ArrayLike, v_phase: ArrayLike, cos_phi: ArrayLike) -> InverterLosses:
    """Average-value losses of the inverter for a sinusoidal phase current (RMS, A), phase voltage (RMS, V)
    and displacement factor cos φ (motoring > 0, generating < 0). Vectorised."""
    i = np.asarray(i_rms, dtype=float)
    c = np.asarray(cos_phi, dtype=float)
    if np.any(~np.isfinite(i)) or np.any(i < 0):
        raise ValueError("i_rms must be finite and >= 0 A")
    if np.any(~np.isfinite(c)) or np.any(np.abs(c) > 1 + 1e-12):
        raise ValueError("cos_phi must be in [-1, 1]")
    m = np.asarray(modulation_index(p, v_phase), dtype=float)
    i_pk = math.sqrt(2.0) * i
    mc = m * c
    pt = p.v_ce0 * i_pk * (1 / (2 * math.pi) + mc / 8) + p.r_ce * i_pk**2 * (1 / 8 + mc / (3 * math.pi))
    pd = p.v_f0 * i_pk * (1 / (2 * math.pi) - mc / 8) + p.r_f * i_pk**2 * (1 / 8 - mc / (3 * math.pi))
    scale = p.f_sw * (i_pk / (math.pi * p.i_ref)) * (p.v_dc / p.v_ref)
    st, sd = p.e_on_off * scale, p.e_rr * scale
    tot = 6.0 * (pt + pd + st + sd)
    out = [6.0 * pt, 6.0 * pd, 6.0 * st, 6.0 * sd, tot]
    if np.ndim(tot) == 0:
        out = [float(x) for x in out]
    return InverterLosses(*out)


# --- SVPWM -------------------------------------------------------------------------------------

def svpwm(v_alpha: float, v_beta: float, v_dc: float, t_s: float) -> tuple[int, float, float, float]:
    """Sector (1–6) and dwell times (t1, t2, t0) in s of the two adjacent active vectors and of the zero
    vectors over one switching period t_s, for the reference (v_α, v_β) in V (amplitude-invariant Clarke).

    Active vector k has length 2·V_dc/3 at angle (k − 1)·60°; t1 belongs to vector k, t2 to vector k + 1.
    Refuses a reference outside the linear range |v| ≤ V_dc/√3.
    """
    for name, x in (("v_dc", v_dc), ("t_s", t_s)):
        if not math.isfinite(x) or x <= 0:
            raise ValueError(f"{name} must be a finite number > 0, got {x!r}")
    if not (math.isfinite(v_alpha) and math.isfinite(v_beta)):
        raise ValueError("v_alpha and v_beta must be finite")
    mag = math.hypot(v_alpha, v_beta)
    if mag > v_dc / SQRT3 * (1 + 1e-12):
        raise ValueError(f"|v_ref| = {mag:.4g} V outside the linear range (max V_dc/√3 = {v_dc / SQRT3:.4g} V)")
    angle = math.atan2(v_beta, v_alpha) % (2 * math.pi)
    sector = min(int(angle // (math.pi / 3)), 5) + 1
    theta = angle - (sector - 1) * math.pi / 3  # angle inside the sector, [0, 60°)
    k = SQRT3 * t_s * mag / v_dc
    t1 = k * math.sin(math.pi / 3 - theta)
    t2 = k * math.sin(theta)
    t0 = t_s - t1 - t2
    return sector, t1, t2, max(t0, 0.0)


def active_vector(k: int, v_dc: float) -> tuple[float, float]:
    """(v_α, v_β) of active vector k = 1…6, V: length 2·V_dc/3 at (k − 1)·60°."""
    if k not in range(1, 7):
        raise ValueError(f"active vector index must be 1…6, got {k!r}")
    a = (k - 1) * math.pi / 3
    return 2 * v_dc / 3 * math.cos(a), 2 * v_dc / 3 * math.sin(a)
