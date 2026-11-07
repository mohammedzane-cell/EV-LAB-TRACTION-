"""Per-phase Γ equivalent circuit of a three-phase induction motor.

Two layouts (MotorParams.layout), identical when R1 = 0:
  "tp3" (default, TP3 Figure 1): V → R1 (carries I1) → Rf ∥ jXm → jX + R'2/g
  "terminals":                   V → Rf ∥ jXm at the terminals, and in parallel
                                 R1 + jX + R'2/g (R1 carries I'2 only)

Seen from the rotor branch, both reduce to a Thévenin source (V_th, Z_th):
  tp3:       V_th = V·Zm/(R1 + Zm),  Z_th = R1 ∥ Zm
  terminals: V_th = V,               Z_th = R1
so I'2, torque and breakdown share one set of formulas.

Division-free in g: the rotor branch is handled through g·Z2 = Z_th·g + R'2 + jX·g,
which is never zero, so g = 0 (no-load) and g < 0 (generator) need no special case.

All quantities are per phase (star connection), SI units, three-phase powers.
The supply can be overridden (v_phase, f) for V/f operation: reactances scale
with f / f_rated, resistances stay constant (docs/assumptions.md A2).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, NamedTuple

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy.optimize import minimize_scalar

from evlab.core.session import MotorParams

FloatOrArray = float | NDArray[np.float64]
ComplexOrArray = complex | NDArray[np.complex128]

T_ZERO_C = 273.15  # K
COPPER_T0 = 234.5  # °C, inferred zero-resistance temperature of copper


# --- internal helpers ---------------------------------------------------------------

class _Supply(NamedTuple):
    v: float | np.ndarray  # phase voltage, V
    w: float | np.ndarray  # electrical angular frequency, rad/s
    x: float | np.ndarray  # leakage reactance at f, Ω
    x_m: float | np.ndarray  # magnetising reactance at f, Ω
    r_fe: float | np.ndarray  # iron-loss resistance, Ω


def _positive(name: str, value: ArrayLike, unit: str) -> float | np.ndarray:
    arr = np.asarray(value, dtype=float)
    if not np.all(np.isfinite(arr)) or np.any(arr <= 0):
        raise ValueError(f"{name} must be finite and > 0 {unit}, got {value!r}")
    return float(arr) if arr.ndim == 0 else arr


def _supply(
    m: MotorParams, v_phase: ArrayLike | None, f: ArrayLike | None, r_fe: ArrayLike | None = None
) -> _Supply:
    """Supply at (v_phase, f), scalars or arrays that broadcast with the slip."""
    v = m.v_phase if v_phase is None else _positive("v_phase", v_phase, "V")
    freq = m.f_rated if f is None else _positive("f", f, "Hz")
    rfe = m.r_fe if r_fe is None else _positive("r_fe", r_fe, "Ω")
    k = freq / m.f_rated
    return _Supply(v, 2.0 * math.pi * freq, m.x_leak * k, m.x_m * k, rfe)


def _slip(g: ArrayLike) -> NDArray[np.float64]:
    arr = np.asarray(g, dtype=float)
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"slip g must be finite, got {g!r}")
    return arr


def _out(arr: np.ndarray) -> float | complex | np.ndarray:
    if arr.ndim:
        return arr
    return complex(arr) if np.iscomplexobj(arr) else float(arr)


class _Solution(NamedTuple):
    g: NDArray[np.float64]
    s: _Supply
    i1: NDArray[np.complex128]  # stator current phasor, A
    i2: NDArray[np.complex128]  # rotor current referred to the stator, A
    e: NDArray[np.complex128]  # voltage across the magnetising branch, V
    p_gap: NDArray[np.float64]  # air-gap power (3 phases), W


def _solve(
    m: MotorParams, g: ArrayLike, v_phase: ArrayLike | None, f: ArrayLike | None, r_fe: ArrayLike | None = None
) -> _Solution:
    """Solve the circuit for every slip in g (vectorised, broadcast with v_phase, f, r_fe)."""
    s = _supply(m, v_phase, f, r_fe)
    gg = _slip(g)
    v_th, z_th = thevenin(m, v_phase, f, r_fe=r_fe)
    y_m = 1.0 / s.r_fe + 1.0 / (1j * s.x_m)
    d = z_th * gg + m.r2p + 1j * s.x * gg  # g·(Z_th + R'2/g + jX), never 0
    i2 = v_th * gg / d
    if m.layout == "tp3":
        y2 = gg / (m.r2p + 1j * s.x * gg)  # rotor-branch admittance, 0 at g = 0
        i1 = s.v / (m.r1 + 1.0 / (y_m + y2))  # Re(y_m) > 0 and Im(y_m + y2) < 0: never singular
        e = s.v - m.r1 * i1
    else:
        i1 = s.v * y_m + i2
        e = np.broadcast_to(s.v, i2.shape) + 0j
    p_gap = 3.0 * m.r2p * gg * np.abs(v_th) ** 2 / np.abs(d) ** 2
    return _Solution(gg, s, i1, i2, e, p_gap)


# --- circuit building blocks --------------------------------------------------------

def magnetising_impedance(
    m: MotorParams, f: ArrayLike | None = None, r_fe: ArrayLike | None = None
) -> ComplexOrArray:
    """Z_m = Rf ∥ jXm: iron-loss resistance in parallel with the magnetising reactance, Ω.

    Args:
        m: motor circuit.
        f: supply frequency override, Hz (Xm scales with f), scalar or array.
        r_fe: iron-loss resistance override, Ω (default m.r_fe), scalar or array.
    """
    s = _supply(m, None, f, r_fe)
    return _out(np.asarray(1.0 / (1.0 / s.r_fe + 1.0 / (1j * s.x_m))))


def magnetising_current(m: MotorParams) -> float:
    """No-load magnetising current I_µ = V/Xm at rated voltage and frequency, A (RMS, per phase).

    The R1 drop and the iron-loss current are neglected (E ≈ V); TD5 Ex 1: 230/46 = 5 A.
    """
    return m.v_phase / m.x_m

def thevenin(
    m: MotorParams, v_phase: ArrayLike | None = None, f: ArrayLike | None = None,
    r_fe: ArrayLike | None = None,
) -> tuple[ComplexOrArray, ComplexOrArray]:
    """Thévenin source seen by the rotor branch: tp3 V_th = V·Zm/(R1+Zm), Z_th = R1∥Zm; terminals V_th = V, Z_th = R1.

    Args:
        m: motor circuit.
        v_phase: phase voltage override, V.
        f: supply frequency override, Hz.
        r_fe: iron-loss resistance override, Ω.

    Returns:
        (V_th in V, Z_th in Ω), complex, with V as the phase reference.
    """
    s = _supply(m, v_phase, f, r_fe)
    if m.layout == "terminals":
        return _out(np.asarray(s.v + 0j)), _out(np.asarray(m.r1 + 0j) + 0 * np.asarray(s.w))
    z_m = magnetising_impedance(m, f, r_fe)
    return s.v * z_m / (m.r1 + z_m), m.r1 * z_m / (m.r1 + z_m)


# --- per-slip quantities (vectorised over g) ----------------------------------------

def impedance(
    m: MotorParams, g: ArrayLike, v_phase: float | None = None, f: float | None = None
) -> ComplexOrArray:
    """Input impedance per phase Z = V / I1, Ω (complex): what the supply sees at slip g.

    Args:
        m: motor circuit.
        g: slip (dimensionless), scalar or array; g < 0 = generator.
        v_phase: phase voltage override, V.
        f: supply frequency override, Hz.
    """
    sol = _solve(m, g, v_phase, f)
    return _out(sol.s.v / sol.i1)


def stator_current(
    m: MotorParams, g: ArrayLike, v_phase: float | None = None, f: float | None = None
) -> FloatOrArray:
    """Stator current |I1| = |V / Z|, A (RMS, line = phase in star).

    Args:
        m: motor circuit.
        g: slip (dimensionless), scalar or array.
        v_phase: phase voltage override, V.
        f: supply frequency override, Hz.
    """
    return _out(np.abs(_solve(m, g, v_phase, f).i1))


def rotor_current(
    m: MotorParams, g: ArrayLike, v_phase: float | None = None, f: float | None = None
) -> FloatOrArray:
    """Rotor current referred to the stator |I'2| = |V_th·g / (Z_th·g + R'2 + jX·g)|, A.

    Same as V_th / (Z_th + R'2/g + jX), multiplied top and bottom by g so g = 0 gives 0.

    Args:
        m: motor circuit.
        g: slip (dimensionless), scalar or array.
        v_phase: phase voltage override, V.
        f: supply frequency override, Hz.
    """
    return _out(np.abs(_solve(m, g, v_phase, f).i2))


def power_factor(
    m: MotorParams, g: ArrayLike, v_phase: float | None = None, f: float | None = None
) -> FloatOrArray:
    """cos φ1 = Re(I1)/|I1| with V as reference: signed, < 0 when the machine generates.

    Args:
        m: motor circuit.
        g: slip (dimensionless), scalar or array.
        v_phase: phase voltage override, V.
        f: supply frequency override, Hz.
    """
    i1 = _solve(m, g, v_phase, f).i1
    return _out(i1.real / np.abs(i1))


def torque(
    m: MotorParams, g: ArrayLike, v_phase: ArrayLike | None = None, f: ArrayLike | None = None,
    r_fe: ArrayLike | None = None,
) -> FloatOrArray:
    """T = (3p/ω)·(R'2/g)·|I'2|²: air-gap power divided by the synchronous speed Ω_s = ω/p, N·m.

    Computed as (3p/ω)·R'2·g·|V_th|²/|Z_th·g + R'2 + jX·g|², finite at g = 0, negative for g < 0.

    Args:
        m: motor circuit.
        g: slip (dimensionless), scalar or array.
        v_phase: phase voltage override, V.
        f: supply frequency override, Hz.
        r_fe: iron-loss resistance override, Ω.
    """
    sol = _solve(m, g, v_phase, f, r_fe)
    return _out(sol.p_gap * m.pole_pairs / sol.s.w)


def mechanical_speed(m: MotorParams, g: ArrayLike, f: float | None = None) -> FloatOrArray:
    """Ω = Ω_s·(1 − g) with Ω_s = 2πf/p: the rotor lags the field by the slip, rad/s.

    Args:
        m: motor circuit.
        g: slip (dimensionless), scalar or array.
        f: supply frequency override, Hz.
    """
    s = _supply(m, None, f)
    return _out((s.w / m.pole_pairs) * (1.0 - _slip(g)))


def slip_from_speed(m: MotorParams, omega_mech: ArrayLike, f: float | None = None) -> FloatOrArray:
    """g = (Ω_s − Ω)/Ω_s: relative speed of the field with respect to the rotor (dimensionless).

    Args:
        m: motor circuit.
        omega_mech: rotor mechanical speed, rad/s.
        f: supply frequency override, Hz.
    """
    s = _supply(m, None, f)
    om = np.asarray(omega_mech, dtype=float)
    if not np.all(np.isfinite(om)):
        raise ValueError(f"omega_mech must be finite, got {omega_mech!r}")
    ws = s.w / m.pole_pairs
    return _out((ws - om) / ws)


def input_power(
    m: MotorParams, g: ArrayLike, v_phase: float | None = None, f: float | None = None
) -> FloatOrArray:
    """P_in = 3·Re(V·I1*) = 3·V·I1·cos φ1, W (three phases; < 0 = power sent back to the supply).

    Args:
        m: motor circuit.
        g: slip (dimensionless), scalar or array.
        v_phase: phase voltage override, V.
        f: supply frequency override, Hz.
    """
    sol = _solve(m, g, v_phase, f)
    return _out(3.0 * sol.s.v * sol.i1.real)


def efficiency(
    m: MotorParams, g: ArrayLike, v_phase: float | None = None, f: float | None = None
) -> FloatOrArray:
    """η = useful power out / power in: motor P_mec/P_in, generator P_in/P_mec (both < 0), else 0.

    P_mec = (1 − g)·P_gap is the internal mechanical power: mechanical losses are
    not in the circuit (TD5: negligible; added later by core.losses). At no-load,
    locked rotor and plugging there is no useful output, so η = 0.

    Args:
        m: motor circuit.
        g: slip (dimensionless), scalar or array.
        v_phase: phase voltage override, V.
        f: supply frequency override, Hz.
    """
    sol = _solve(m, g, v_phase, f)
    p_in = 3.0 * sol.s.v * sol.i1.real
    p_mec = (1.0 - sol.g) * sol.p_gap
    motoring = (p_in > 0) & (p_mec > 0)
    generating = (p_in < 0) & (p_mec < 0)
    num = np.where(motoring, p_mec, np.where(generating, p_in, 0.0))
    den = np.where(motoring, p_in, np.where(generating, p_mec, 1.0))
    eta = np.divide(num, den, out=np.zeros_like(num), where=motoring | generating)
    return _out(eta)


# --- breakdown ------------------------------------------------------------------

def breakdown_slip(m: MotorParams, f: ArrayLike | None = None) -> FloatOrArray:
    """Closed form g_c = R'2 / sqrt(R_th² + (X_th + X)²): rotor resistance matched to the source impedance.

    With R1 = 0 (Z_th = 0) this is the course value g_c = R'2 / X.

    Args:
        m: motor circuit.
        f: supply frequency override, Hz.
    """
    s = _supply(m, None, f)
    _, z_th = thevenin(m, None, f)
    z_th = np.asarray(z_th)
    return _out(m.r2p / np.hypot(z_th.real, z_th.imag + s.x))


def max_torque(
    m: MotorParams, v_phase: ArrayLike | None = None, f: ArrayLike | None = None,
    r_fe: ArrayLike | None = None,
) -> FloatOrArray:
    """Closed form T_max = 3p·|V_th|² / (2ω·(R_th + sqrt(R_th² + (X_th + X)²))), N·m (maximum power transfer).

    With R1 = 0 this is the course formula 3p·V² / (2·X·ω).

    Args:
        m: motor circuit.
        v_phase: phase voltage override, V.
        f: supply frequency override, Hz.
        r_fe: iron-loss resistance override, Ω (e.g. Rf(f) of core.losses).
    """
    s = _supply(m, v_phase, f, r_fe)
    v_th, z_th = thevenin(m, v_phase, f, r_fe=r_fe)
    z_th = np.asarray(z_th)
    r_th, x_tot = z_th.real, z_th.imag + s.x
    return _out(3.0 * m.pole_pairs * np.abs(v_th) ** 2 / (2.0 * s.w * (r_th + np.hypot(r_th, x_tot))))


_LOG_G_BOUNDS = (-6.0, 3.0)  # search g in [1e-6, 1e3]


def breakdown(
    m: MotorParams,
    v_phase: float | None = None,
    f: float | None = None,
    method: Literal["numeric", "closed"] = "numeric",
) -> tuple[float, float]:
    """Breakdown point (g_c, T_max): the slip where dT/dg = 0 in motoring, and the torque there.

    "numeric": bounded Brent maximisation of torque(g) over log10(g) ∈ [−6, 3]
    (torque(g) is unimodal for g > 0). "closed": breakdown_slip and max_torque.

    Args:
        m: motor circuit.
        v_phase: phase voltage override, V.
        f: supply frequency override, Hz.
        method: "numeric" (default) or "closed".

    Returns:
        (g_c dimensionless, T_max in N·m).
    """
    if np.ndim(v_phase) or np.ndim(f):
        raise ValueError("breakdown() takes scalar v_phase and f; use breakdown_slip / max_torque for arrays")
    if method == "closed":
        return float(breakdown_slip(m, f)), float(max_torque(m, v_phase, f))
    if method != "numeric":
        raise ValueError(f"method must be 'numeric' or 'closed', got {method!r}")
    _supply(m, v_phase, f)  # validate once
    res = minimize_scalar(
        lambda u: -float(torque(m, 10.0**u, v_phase, f)),
        bounds=_LOG_G_BOUNDS,
        method="bounded",
        options={"xatol": 1e-12},
    )
    lo, hi = _LOG_G_BOUNDS
    if not res.success or res.x - lo < 1e-6 or hi - res.x < 1e-6:
        raise ValueError(f"torque maximum not found inside g ∈ [1e{lo:.0f}, 1e{hi:.0f}]")
    return 10.0**res.x, -res.fun


# --- full operating point -----------------------------------------------------------

@dataclass(frozen=True)
class OperatingPoint:
    """Steady-state operating point (SI, three-phase powers); fields are arrays when g is.

    Attributes:
        slip: g (dimensionless).
        omega_mech: rotor speed, rad/s.
        e: |voltage across the magnetising branch|, V (= V in the terminals layout).
        i1: stator current, A.
        i2: rotor current referred to the stator, A.
        i_fe: iron-loss branch current E/Rf, A.
        i_mu: magnetising current E/Xm, A.
        power_factor: cos φ1 (signed: < 0 when generating).
        p_in: electrical input power, W.
        q_in: reactive input power, var.
        p_cu1: stator copper loss, W (3·R1·I1² in tp3, 3·R1·I'2² in terminals).
        p_fe: iron loss 3·E²/Rf, W.
        p_gap: air-gap power 3·(R'2/g)·I'2², W.
        p_cu2: rotor copper loss g·P_gap, W.
        p_mech: internal mechanical power (1 − g)·P_gap, W (before mechanical losses).
        torque: electromagnetic torque P_gap/Ω_s, N·m.
    """

    slip: FloatOrArray
    omega_mech: FloatOrArray
    e: FloatOrArray
    i1: FloatOrArray
    i2: FloatOrArray
    i_fe: FloatOrArray
    i_mu: FloatOrArray
    power_factor: FloatOrArray
    p_in: FloatOrArray
    q_in: FloatOrArray
    p_cu1: FloatOrArray
    p_fe: FloatOrArray
    p_gap: FloatOrArray
    p_cu2: FloatOrArray
    p_mech: FloatOrArray
    torque: FloatOrArray


def operating_point(
    m: MotorParams, g: ArrayLike, v_phase: ArrayLike | None = None, f: ArrayLike | None = None,
    r_fe: ArrayLike | None = None,
) -> OperatingPoint:
    """Every current and power at slip g; P_in = P_cu1 + P_fe + P_cu2 + P_mec holds exactly.

    g, v_phase, f and r_fe broadcast together (one operating point per element).

    Args:
        m: motor circuit.
        g: slip (dimensionless), scalar or array; g = 0 is the ideal no-load.
        v_phase: phase voltage override, V.
        f: supply frequency override, Hz.
        r_fe: iron-loss resistance override, Ω (e.g. frequency-dependent, core.losses).
    """
    sol = _solve(m, g, v_phase, f, r_fe)
    s = sol.s
    i1 = np.abs(sol.i1)
    i2 = np.abs(sol.i2)
    e = np.abs(sol.e)
    s_in = 3.0 * s.v * np.conj(sol.i1)
    p_cu1 = 3.0 * m.r1 * (i1 if m.layout == "tp3" else i2) ** 2
    ws = s.w / m.pole_pairs
    return OperatingPoint(
        slip=_out(sol.g),
        omega_mech=_out(ws * (1.0 - sol.g)),
        e=_out(e),
        i1=_out(i1),
        i2=_out(i2),
        i_fe=_out(e / s.r_fe),
        i_mu=_out(e / s.x_m),
        power_factor=_out(sol.i1.real / i1),
        p_in=_out(s_in.real),
        q_in=_out(s_in.imag),
        p_cu1=_out(p_cu1),
        p_fe=_out(3.0 * e**2 / s.r_fe),
        p_gap=_out(sol.p_gap),
        p_cu2=_out(sol.g * sol.p_gap),
        p_mech=_out((1.0 - sol.g) * sol.p_gap),
        torque=_out(sol.p_gap / ws),
    )


# --- temperature ----------------------------------------------------------------

def check_copper_temperature(name: str, temperature_k: float) -> None:
    """Raise ValueError unless temperature_k (K) is finite and above the copper zero −234,5 °C (38,65 K),
    where the linear copper law R ∝ (234,5 + T°C) would give R <= 0."""
    if not math.isfinite(temperature_k) or temperature_k <= 0:
        raise ValueError(f"{name} must be a finite temperature > 0 K, got {temperature_k!r}")
    if temperature_k - T_ZERO_C <= -COPPER_T0:
        raise ValueError(
            f"{name} = {temperature_k - T_ZERO_C:.2f} °C is at or below −234,5 °C: "
            "the copper law would give a resistance <= 0"
        )


def copper_resistance(r_20c: float, temperature_k: float) -> float:
    """R(T) = R20·(234.5 + T°C)/254.5: copper resistance is linear in T, zero at −234.5 °C, Ω.

    Args:
        r_20c: resistance measured at 20 °C, Ω (> 0).
        temperature_k: winding temperature, K (above −234,5 °C).
    """
    if not math.isfinite(r_20c) or r_20c <= 0:
        raise ValueError(f"r_20c must be a finite number > 0 Ω, got {r_20c!r}")
    check_copper_temperature("temperature_k", temperature_k)
    t_c = temperature_k - T_ZERO_C
    return r_20c * (COPPER_T0 + t_c) / (COPPER_T0 + 20.0)
