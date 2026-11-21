"""Characteristic points of the induction motor and parameter sensitivity. Pure physics, no Qt.

Builds on core.circuit (same Γ circuit, same layouts); nothing here changes the circuit itself.

- characteristics(m): synchronous speed, starting point (g = 1), breakdown point.
- point_at_speed(m, n): operating point at a shaft speed (slip from the speed).
- rotor_at_temperature(m, ...): R'2 corrected for the rotor temperature (option; the baseline keeps
  R'2 at its identification temperature). Linear law R(T) = R_ref·(k + T)/(k + T_ref), k = 234,5 °C
  for copper, 225 °C for aluminium (inferred zero-resistance temperatures, IEC 60034-1 / standard
  practice for cast aluminium cages).
- sensitivity(m): normalised sensitivities S = (∂y/∂p)·(p/y) of the breakdown torque and slip, the
  starting torque and current, and the efficiency at a reference slip, to R1, R'2, X, Xm, Rf, by
  central differences (relative step 1e-4).

SI units: Ω, rad/s, N·m, A, W, K.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from evlab.core import circuit
from evlab.core.session import MotorParams

PARAMS = ("r1", "r2p", "x_leak", "x_m", "r_fe")
OUTPUTS = ("breakdown_torque", "breakdown_slip", "start_torque", "start_current", "efficiency")
ZERO_RESISTANCE_C = {"cuivre": 234.5, "aluminium": 225.0}  # °C, R(T) ∝ (k + T)
T_ZERO_C = 273.15
STEP = 1e-4


@dataclass(frozen=True)
class Characteristics:
    """Characteristic points at rated voltage and frequency.

    Attributes:
        omega_sync: synchronous speed 2πf/p, rad/s.
        start_torque: electromagnetic torque at standstill (g = 1), N·m.
        start_current: stator current at standstill, A (RMS, per phase).
        start_power_factor: cos φ at standstill.
        breakdown_slip: slip of maximum torque.
        breakdown_torque: maximum electromagnetic torque, N·m.
        breakdown_speed: rotor speed at maximum torque, rad/s.
        no_load_current: stator current at g = 0, A.
    """

    omega_sync: float
    start_torque: float
    start_current: float
    start_power_factor: float
    breakdown_slip: float
    breakdown_torque: float
    breakdown_speed: float
    no_load_current: float


def characteristics(m: MotorParams) -> Characteristics:
    """Synchronous speed, starting point (g = 1), breakdown point and no-load current of a motor (SI)."""
    if not isinstance(m, MotorParams):
        raise ValueError(f"m must be a MotorParams, got {type(m).__name__}")
    start = circuit.operating_point(m, 1.0)
    g_c, t_max = circuit.breakdown(m, method="closed")  # exact Thévenin form: smooth for the sensitivities
    return Characteristics(
        omega_sync=2.0 * math.pi * m.f_rated / m.pole_pairs,
        start_torque=float(start.torque),
        start_current=float(start.i1),
        start_power_factor=float(start.power_factor),
        breakdown_slip=float(g_c),
        breakdown_torque=float(t_max),
        breakdown_speed=float(circuit.mechanical_speed(m, g_c)),
        no_load_current=float(circuit.operating_point(m, 0.0).i1),
    )


def point_at_speed(m: MotorParams, omega_mech: float) -> circuit.OperatingPoint:
    """Operating point at rated voltage and frequency for a rotor speed (rad/s, motoring: 0 < Ω ≤ Ω_s)."""
    if not math.isfinite(omega_mech) or omega_mech <= 0:
        raise ValueError(f"omega_mech must be a finite speed > 0 rad/s, got {omega_mech!r}")
    g = float(circuit.slip_from_speed(m, omega_mech))
    if not 0.0 <= g <= 1.0:
        raise ValueError(f"speed {omega_mech:.4g} rad/s gives g = {g:.4g}: outside motoring (0 ≤ g ≤ 1)")
    return circuit.operating_point(m, g)


def rotor_at_temperature(m: MotorParams, temperature_k: float, reference_k: float,
                         material: str = "aluminium") -> MotorParams:
    """Motor with R'2 corrected from reference_k (temperature of its identification) to temperature_k (K)."""
    if material not in ZERO_RESISTANCE_C:
        raise ValueError(f"material must be one of {tuple(ZERO_RESISTANCE_C)}, got {material!r}")
    for name, t in (("temperature_k", temperature_k), ("reference_k", reference_k)):
        if not math.isfinite(t) or t <= 0:
            raise ValueError(f"{name} must be a finite temperature > 0 K, got {t!r}")
    k = ZERO_RESISTANCE_C[material]
    ratio = (k + temperature_k - T_ZERO_C) / (k + reference_k - T_ZERO_C)
    if ratio <= 0:
        raise ValueError(f"temperature {temperature_k} K is below the validity of the linear law ({-k} °C)")
    return replace(m, r2p=m.r2p * ratio)


def _outputs(m: MotorParams, slip_ref: float) -> dict[str, float]:
    ch = characteristics(m)
    op = circuit.operating_point(m, slip_ref)
    return {
        "breakdown_torque": ch.breakdown_torque,
        "breakdown_slip": ch.breakdown_slip,
        "start_torque": ch.start_torque,
        "start_current": ch.start_current,
        "efficiency": float(circuit.efficiency(m, slip_ref)) if op.p_in > 0 else math.nan,
    }


def sensitivity(m: MotorParams, slip_ref: float = 0.05, step: float = STEP) -> dict[str, dict[str, float]]:
    """Normalised sensitivities S[output][param] = (∂y/∂p)·(p/y), central differences.

    A parameter equal to 0 (e.g. R1 of TD5 Ex 1) has S = 0 by definition (no relative change exists).
    slip_ref: slip at which the efficiency is evaluated (0 < g < 1).
    """
    if not 0.0 < slip_ref < 1.0:
        raise ValueError(f"slip_ref must be in (0, 1), got {slip_ref!r}")
    if not 0.0 < step < 0.1:
        raise ValueError(f"step must be in (0, 0.1), got {step!r}")
    base = _outputs(m, slip_ref)
    out: dict[str, dict[str, float]] = {o: {} for o in OUTPUTS}
    for p in PARAMS:
        value = getattr(m, p)
        if value == 0:
            for o in OUTPUTS:
                out[o][p] = 0.0
            continue
        up = _outputs(replace(m, **{p: value * (1 + step)}), slip_ref)
        down = _outputs(replace(m, **{p: value * (1 - step)}), slip_ref)
        for o in OUTPUTS:
            y = base[o]
            out[o][p] = (up[o] - down[o]) / (2 * step) / y if y and math.isfinite(y) else math.nan
    return out
