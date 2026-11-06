"""Γ equivalent circuit of the induction motor: currents, torque, power balance.

All quantities are per phase (star connection) and in SI units. The supply
can be overridden (v_phase, f) for V/f operation; reactances then scale with
f / f_rated, resistances stay constant.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from evlab.core.session import MotorParams

FloatOrArray = float | NDArray[np.float64]

T_ZERO_C = 273.15  # K
COPPER_T0 = 234.5  # °C, inferred zero-resistance temperature of copper


def _supply(m: MotorParams, v_phase: float | None, f: float | None) -> tuple[float, float, float]:
    """Return (V, ω, x_leak at f), validating overrides."""
    v = m.v_phase if v_phase is None else float(v_phase)
    freq = m.f_rated if f is None else float(f)
    if not math.isfinite(v) or v <= 0:
        raise ValueError(f"v_phase must be a finite number > 0 V, got {v_phase!r}")
    if not math.isfinite(freq) or freq <= 0:
        raise ValueError(f"f must be a finite number > 0 Hz, got {f!r}")
    return v, 2.0 * math.pi * freq, m.x_leak * freq / m.f_rated


def _slip(g: ArrayLike) -> NDArray[np.float64]:
    arr = np.asarray(g, dtype=float)
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"slip g must be finite, got {g!r}")
    return arr


def _out(arr: NDArray[np.float64]) -> FloatOrArray:
    return float(arr) if arr.ndim == 0 else arr


def rotor_current(
    m: MotorParams, g: ArrayLike, v_phase: float | None = None, f: float | None = None
) -> FloatOrArray:
    """RMS rotor current referred to the stator, I'2 (A).

    I'2 = V / |r1 + r2p/g + j·X|, written as V·|g| / |r1·g + r2p + j·X·g|
    so that g = 0 gives I'2 = 0 without a singularity.

    Args:
        m: motor circuit.
        g: slip (dimensionless), scalar or array; negative = generating.
        v_phase: phase voltage override, V. Defaults to m.v_phase.
        f: supply frequency override, Hz. Defaults to m.f_rated.
    """
    v, _, x = _supply(m, v_phase, f)
    gg = _slip(g)
    i2 = v * np.abs(gg) / np.hypot(m.r1 * gg + m.r2p, x * gg)
    return _out(i2)


def torque(
    m: MotorParams, g: ArrayLike, v_phase: float | None = None, f: float | None = None
) -> FloatOrArray:
    """Electromagnetic torque T = (3p/ω)·(R'2/g)·I'2², N·m.

    Args:
        m: motor circuit.
        g: slip (dimensionless), scalar or array.
        v_phase: phase voltage override, V.
        f: supply frequency override, Hz.
    """
    v, w, x = _supply(m, v_phase, f)
    gg = _slip(g)
    t = (3.0 * m.pole_pairs / w) * m.r2p * gg * v**2 / ((m.r1 * gg + m.r2p) ** 2 + (x * gg) ** 2)
    return _out(t)


def breakdown_slip(m: MotorParams, f: float | None = None) -> float:
    """Slip at maximum (breakdown) torque, g_c = R'2 / sqrt(R1² + X²) (dimensionless).

    Args:
        m: motor circuit.
        f: supply frequency override, Hz (X scales with f).
    """
    _, _, x = _supply(m, None, f)
    return m.r2p / math.hypot(m.r1, x)


def max_torque(m: MotorParams, v_phase: float | None = None, f: float | None = None) -> float:
    """Maximum motoring torque T_max = 3p·V² / (2ω·(R1 + sqrt(R1² + X²))), N·m.

    With R1 = 0 this is the course formula 3p·V² / (2·X·ω).

    Args:
        m: motor circuit.
        v_phase: phase voltage override, V.
        f: supply frequency override, Hz.
    """
    v, w, x = _supply(m, v_phase, f)
    return 3.0 * m.pole_pairs * v**2 / (2.0 * w * (m.r1 + math.hypot(m.r1, x)))


def slip_from_speed(m: MotorParams, omega_mech: ArrayLike, f: float | None = None) -> FloatOrArray:
    """Slip g = (Ω_s − Ω) / Ω_s from the mechanical speed Ω (rad/s).

    Args:
        m: motor circuit.
        omega_mech: rotor mechanical speed, rad/s.
        f: supply frequency override, Hz.
    """
    _, w, _ = _supply(m, None, f)
    om = np.asarray(omega_mech, dtype=float)
    if not np.all(np.isfinite(om)):
        raise ValueError(f"omega_mech must be finite, got {omega_mech!r}")
    ws = w / m.pole_pairs
    return _out((ws - om) / ws)


def speed_from_slip(m: MotorParams, g: ArrayLike, f: float | None = None) -> FloatOrArray:
    """Mechanical speed Ω = Ω_s·(1 − g), rad/s.

    Args:
        m: motor circuit.
        g: slip (dimensionless).
        f: supply frequency override, Hz.
    """
    _, w, _ = _supply(m, None, f)
    return _out((w / m.pole_pairs) * (1.0 - _slip(g)))


@dataclass(frozen=True)
class OperatingPoint:
    """Steady-state operating point of the Γ circuit (all SI, 3-phase powers).

    Attributes:
        slip: g (dimensionless).
        omega_mech: rotor speed, rad/s.
        i2: rotor current referred to stator, A.
        i_fe: iron-loss branch current, A.
        i_mu: magnetising current, A.
        i1: stator line (= phase) current, A.
        power_factor: cos φ1 (signed: < 0 when generating).
        p_in: electrical input power, W.
        p_fe: iron loss 3·V²/Rf, W.
        p_cu1: stator copper loss 3·R1·I'2², W.
        p_gap: air-gap power 3·(R'2/g)·I'2², W.
        p_cu2: rotor copper loss g·P_gap, W.
        p_mech: internal mechanical power (1 − g)·P_gap, W (before mechanical losses).
        torque: electromagnetic torque, N·m.
    """

    slip: float
    omega_mech: float
    i2: float
    i_fe: float
    i_mu: float
    i1: float
    power_factor: float
    p_in: float
    p_fe: float
    p_cu1: float
    p_gap: float
    p_cu2: float
    p_mech: float
    torque: float


def operating_point(
    m: MotorParams, g: float, v_phase: float | None = None, f: float | None = None
) -> OperatingPoint:
    """Full operating point of the Γ circuit at slip g.

    Iron-loss resistance Rf is taken constant; x_m and x_leak scale with f.

    Args:
        m: motor circuit.
        g: slip (dimensionless), scalar, non-zero.
        v_phase: phase voltage override, V.
        f: supply frequency override, Hz.
    """
    v, w, x = _supply(m, v_phase, f)
    gf = float(np.asarray(g, dtype=float))
    if not math.isfinite(gf) or gf == 0.0:
        raise ValueError(f"slip g must be finite and non-zero for an operating point, got {g!r}")
    x_m = m.x_m * (w / m.omega_rated)

    i2_ph = v / complex(m.r1 + m.r2p / gf, x)
    i_fe = v / m.r_fe
    i_mu_ph = v / complex(0.0, x_m)
    i1_ph = i_fe + i_mu_ph + i2_ph

    i2 = abs(i2_ph)
    p_in = 3.0 * v * i1_ph.real
    p_fe = 3.0 * v**2 / m.r_fe
    p_cu1 = 3.0 * m.r1 * i2**2
    p_gap = 3.0 * (m.r2p / gf) * i2**2
    ws = w / m.pole_pairs
    return OperatingPoint(
        slip=gf,
        omega_mech=ws * (1.0 - gf),
        i2=i2,
        i_fe=i_fe,
        i_mu=abs(i_mu_ph),
        i1=abs(i1_ph),
        power_factor=i1_ph.real / abs(i1_ph),
        p_in=p_in,
        p_fe=p_fe,
        p_cu1=p_cu1,
        p_gap=p_gap,
        p_cu2=gf * p_gap,
        p_mech=(1.0 - gf) * p_gap,
        torque=p_gap / ws,
    )


def copper_resistance(r_20c: float, temperature_k: float) -> float:
    """Copper resistance at temperature T: R(T) = R20·(234.5 + T°C) / 254.5, Ω.

    Args:
        r_20c: resistance measured at 20 °C, Ω (> 0).
        temperature_k: winding temperature, K (> 0).
    """
    if not math.isfinite(r_20c) or r_20c <= 0:
        raise ValueError(f"r_20c must be a finite number > 0 Ω, got {r_20c!r}")
    if not math.isfinite(temperature_k) or temperature_k <= 0:
        raise ValueError(f"temperature_k must be a finite number > 0 K, got {temperature_k!r}")
    t_c = temperature_k - T_ZERO_C
    return r_20c * (COPPER_T0 + t_c) / (COPPER_T0 + 20.0)
