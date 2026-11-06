"""Γ equivalent circuit of the induction motor (TP3 layout): currents, torque, power balance.

TP3, Figure 1:  V1 → R1 (series, carries I1) → Rf ∥ jXm → jX + R'2/g.

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


def _supply(m: MotorParams, v_phase: float | None, f: float | None) -> tuple[float, float, float, float]:
    """Return (V, ω, x_leak at f, x_m at f), validating overrides."""
    v = m.v_phase if v_phase is None else float(v_phase)
    freq = m.f_rated if f is None else float(f)
    if not math.isfinite(v) or v <= 0:
        raise ValueError(f"v_phase must be a finite number > 0 V, got {v_phase!r}")
    if not math.isfinite(freq) or freq <= 0:
        raise ValueError(f"f must be a finite number > 0 Hz, got {f!r}")
    k = freq / m.f_rated
    return v, 2.0 * math.pi * freq, m.x_leak * k, m.x_m * k


def _slip(g: ArrayLike) -> NDArray[np.float64]:
    arr = np.asarray(g, dtype=float)
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"slip g must be finite, got {g!r}")
    return arr


def _out(arr: NDArray[np.float64]) -> FloatOrArray:
    return float(arr) if arr.ndim == 0 else arr


def magnetising_impedance(m: MotorParams, f: float | None = None) -> complex:
    """Magnetising branch Z_m = Rf ∥ j·Xm at frequency f, Ω (complex).

    Args:
        m: motor circuit.
        f: supply frequency override, Hz (Xm scales with f, Rf constant).
    """
    _, _, _, x_m = _supply(m, None, f)
    return 1.0 / (1.0 / m.r_fe + 1.0 / complex(0.0, x_m))


def thevenin(
    m: MotorParams, v_phase: float | None = None, f: float | None = None
) -> tuple[complex, complex]:
    """Thévenin equivalent of R1 + magnetising branch seen by the rotor branch.

    V_th = V·Z_m / (R1 + Z_m),  Z_th = R1·Z_m / (R1 + Z_m).
    With R1 = 0: V_th = V, Z_th = 0.

    Args:
        m: motor circuit.
        v_phase: phase voltage override, V.
        f: supply frequency override, Hz.

    Returns:
        (V_th in V, Z_th in Ω), both complex, V taken as the phase reference.
    """
    v, _, _, _ = _supply(m, v_phase, f)
    z_m = magnetising_impedance(m, f)
    return v * z_m / (m.r1 + z_m), m.r1 * z_m / (m.r1 + z_m)


def _rotor_current_phasor(
    m: MotorParams, gg: NDArray[np.float64], v_phase: float | None, f: float | None
) -> NDArray[np.complex128]:
    """I'2 = V_th·g / (Z_th·g + R'2 + j·X·g): no singularity at g = 0."""
    _, _, x, _ = _supply(m, v_phase, f)
    v_th, z_th = thevenin(m, v_phase, f)
    return v_th * gg / (z_th * gg + m.r2p + 1j * x * gg)


def rotor_current(
    m: MotorParams, g: ArrayLike, v_phase: float | None = None, f: float | None = None
) -> FloatOrArray:
    """RMS rotor current referred to the stator, I'2 (A).

    TP3 circuit: V → R1 (carries I1) → (Rf ∥ jXm) ∥ (jX + R'2/g).
    Computed from the Thévenin equivalent of R1 + magnetising branch.

    Args:
        m: motor circuit.
        g: slip (dimensionless), scalar or array; negative = generating.
        v_phase: phase voltage override, V. Defaults to m.v_phase.
        f: supply frequency override, Hz. Defaults to m.f_rated.
    """
    return _out(np.abs(_rotor_current_phasor(m, _slip(g), v_phase, f)))


def torque(
    m: MotorParams, g: ArrayLike, v_phase: float | None = None, f: float | None = None
) -> FloatOrArray:
    """Electromagnetic torque T = (3p/ω)·(R'2/g)·I'2², N·m.

    Written as (3p/ω)·R'2·g·|V_th|² / |Z_th·g + R'2 + jXg|² (finite at g = 0).

    Args:
        m: motor circuit.
        g: slip (dimensionless), scalar or array.
        v_phase: phase voltage override, V.
        f: supply frequency override, Hz.
    """
    _, w, x, _ = _supply(m, v_phase, f)
    gg = _slip(g)
    v_th, z_th = thevenin(m, v_phase, f)
    den = np.abs(z_th * gg + m.r2p + 1j * x * gg) ** 2
    return _out((3.0 * m.pole_pairs / w) * m.r2p * gg * abs(v_th) ** 2 / den)


def breakdown_slip(m: MotorParams, f: float | None = None) -> float:
    """Slip at maximum motoring torque, g_c = R'2 / sqrt(R_th² + (X_th + X)²).

    With R1 = 0 this is the course value g_c = R'2 / X (dimensionless).

    Args:
        m: motor circuit.
        f: supply frequency override, Hz.
    """
    _, _, x, _ = _supply(m, None, f)
    _, z_th = thevenin(m, None, f)
    return m.r2p / math.hypot(z_th.real, z_th.imag + x)


def max_torque(m: MotorParams, v_phase: float | None = None, f: float | None = None) -> float:
    """Maximum motoring torque, N·m.

    T_max = 3p·|V_th|² / (2ω·(R_th + sqrt(R_th² + (X_th + X)²))).
    With R1 = 0 this is the course formula 3p·V² / (2·X·ω).

    Args:
        m: motor circuit.
        v_phase: phase voltage override, V.
        f: supply frequency override, Hz.
    """
    _, w, x, _ = _supply(m, v_phase, f)
    v_th, z_th = thevenin(m, v_phase, f)
    r_th, x_tot = z_th.real, z_th.imag + x
    return 3.0 * m.pole_pairs * abs(v_th) ** 2 / (2.0 * w * (r_th + math.hypot(r_th, x_tot)))


def slip_from_speed(m: MotorParams, omega_mech: ArrayLike, f: float | None = None) -> FloatOrArray:
    """Slip g = (Ω_s − Ω) / Ω_s from the mechanical speed Ω (rad/s).

    Args:
        m: motor circuit.
        omega_mech: rotor mechanical speed, rad/s.
        f: supply frequency override, Hz.
    """
    _, w, _, _ = _supply(m, None, f)
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
    _, w, _, _ = _supply(m, None, f)
    return _out((w / m.pole_pairs) * (1.0 - _slip(g)))


@dataclass(frozen=True)
class OperatingPoint:
    """Steady-state operating point of the TP3 circuit (all SI, 3-phase powers).

    Attributes:
        slip: g (dimensionless).
        omega_mech: rotor speed, rad/s.
        e: magnitude of the magnetising-branch voltage E = V − R1·I1, V.
        i1: stator line (= phase) current, A.
        i2: rotor current referred to stator, A.
        i_fe: iron-loss branch current E/Rf, A.
        i_mu: magnetising current E/Xm, A.
        power_factor: cos φ1 (signed: < 0 when generating).
        p_in: electrical input power, W.
        q_in: reactive input power, var.
        p_cu1: stator copper loss 3·R1·I1², W.
        p_fe: iron loss 3·E²/Rf, W.
        p_gap: air-gap power 3·(R'2/g)·I'2², W.
        p_cu2: rotor copper loss g·P_gap, W.
        p_mech: internal mechanical power (1 − g)·P_gap, W (before mechanical losses).
        torque: electromagnetic torque, N·m.
    """

    slip: float
    omega_mech: float
    e: float
    i1: float
    i2: float
    i_fe: float
    i_mu: float
    power_factor: float
    p_in: float
    q_in: float
    p_cu1: float
    p_fe: float
    p_gap: float
    p_cu2: float
    p_mech: float
    torque: float


def operating_point(
    m: MotorParams, g: float, v_phase: float | None = None, f: float | None = None
) -> OperatingPoint:
    """Full operating point of the TP3 circuit at slip g (g = 0: ideal no-load).

    Circuit: V → R1 → node E; at E: Rf ∥ jXm ∥ (jX + R'2/g).
    Rf is constant; Xm and X scale with f.

    Args:
        m: motor circuit.
        g: slip (dimensionless), scalar.
        v_phase: phase voltage override, V.
        f: supply frequency override, Hz.
    """
    v, w, x, x_m = _supply(m, v_phase, f)
    gf = float(np.asarray(g, dtype=float))
    if not math.isfinite(gf):
        raise ValueError(f"slip g must be finite, got {g!r}")

    y2 = gf / complex(m.r2p, x * gf)  # rotor-branch admittance, 0 at g = 0
    y_par = 1.0 / m.r_fe + 1.0 / complex(0.0, x_m) + y2
    i1_ph = v / (m.r1 + 1.0 / y_par)
    e_ph = v - m.r1 * i1_ph
    i2_ph = e_ph * y2

    i1 = abs(i1_ph)
    e = abs(e_ph)
    s_in = 3.0 * v * i1_ph.conjugate()
    # R'2/g·|I'2|² = R'2·g·|E|²/|R'2 + jXg|², finite at g = 0
    p_gap = 3.0 * m.r2p * gf * e**2 / abs(complex(m.r2p, x * gf)) ** 2
    ws = w / m.pole_pairs
    return OperatingPoint(
        slip=gf,
        omega_mech=ws * (1.0 - gf),
        e=e,
        i1=i1,
        i2=abs(i2_ph),
        i_fe=e / m.r_fe,
        i_mu=e / x_m,
        power_factor=i1_ph.real / i1,
        p_in=s_in.real,
        q_in=s_in.imag,
        p_cu1=3.0 * m.r1 * i1**2,
        p_fe=3.0 * e**2 / m.r_fe,
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
