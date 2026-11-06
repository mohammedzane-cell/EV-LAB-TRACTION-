"""Identification of the Γ equivalent circuit from the TP3 / TD5 tests.

Circuit (TP3, Figure 1): V1 → R1 (carries I1) → Rf ∥ jXm → jX + R'2/g.

Two routes:
- classical formulas (DC, no-load, locked-rotor tests), in a "classical"
  variant (course approximations) and an "exact" variant (inverts the
  circuit above with no approximation);
- a least-squares fit of R'2, X, Xm, Rf to any set of measured points.

Per-phase quantities, star connection; powers are three-phase totals.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Literal, Sequence

import numpy as np
from numpy.typing import ArrayLike
from scipy.optimize import least_squares

from evlab.core import circuit
from evlab.core.session import MotorParams

Method = Literal["classical", "exact"]


def _pos(name: str, value: float) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite number > 0, got {value!r}")


def _method(method: str) -> None:
    if method not in ("classical", "exact"):
        raise ValueError(f"method must be 'classical' or 'exact', got {method!r}")


def _power_factor(name: str, v: float, i: float, p: float) -> float:
    cos_phi = p / (3.0 * v * i)
    if cos_phi > 1.0 + 1e-12:
        raise ValueError(
            f"{name}: power factor P/(3·V·I) = {cos_phi:.4f} > 1, measurements are inconsistent"
        )
    return min(cos_phi, 1.0)


# --- measurement records ----------------------------------------------------------

@dataclass(frozen=True)
class DcTest:
    """DC resistance test between two line terminals of the star winding.

    Attributes:
        v_dc: DC voltage between the two terminals, V.
        i_dc: DC current, A.
    """

    v_dc: float
    i_dc: float

    def __post_init__(self) -> None:
        _pos("v_dc", self.v_dc)
        _pos("i_dc", self.i_dc)


@dataclass(frozen=True)
class NoLoadTest:
    """No-load test (g ≈ 0).

    Attributes:
        v_phase: phase voltage, V.
        i_line: line current I0, A.
        p_total: three-phase input power P0, W.
        f: supply frequency, Hz.
    """

    v_phase: float
    i_line: float
    p_total: float
    f: float

    def __post_init__(self) -> None:
        for n in ("v_phase", "i_line", "p_total", "f"):
            _pos(n, getattr(self, n))
        _power_factor("no-load test", self.v_phase, self.i_line, self.p_total)


@dataclass(frozen=True)
class LockedRotorTest:
    """Locked-rotor test (g = 1), usually at reduced voltage.

    Attributes:
        v_phase: phase voltage Vcc, V.
        i_line: line current Icc, A.
        p_total: three-phase input power Pcc, W.
        f: supply frequency, Hz.
    """

    v_phase: float
    i_line: float
    p_total: float
    f: float

    def __post_init__(self) -> None:
        for n in ("v_phase", "i_line", "p_total", "f"):
            _pos(n, getattr(self, n))
        _power_factor("locked-rotor test", self.v_phase, self.i_line, self.p_total)


@dataclass(frozen=True)
class LoadPoint:
    """One measured steady-state point for the least-squares fit.

    Attributes:
        v_phase: phase voltage, V.
        f: supply frequency, Hz.
        slip: slip g (dimensionless; 0 = no-load, 1 = locked rotor).
        i_line: line current, A.
        p_total: three-phase electrical input power, W (negative when generating).
    """

    v_phase: float
    f: float
    slip: float
    i_line: float
    p_total: float

    def __post_init__(self) -> None:
        _pos("v_phase", self.v_phase)
        _pos("f", self.f)
        _pos("i_line", self.i_line)
        if not math.isfinite(self.slip):
            raise ValueError(f"slip must be finite, got {self.slip!r}")
        if not math.isfinite(self.p_total):
            raise ValueError(f"p_total must be finite, got {self.p_total!r}")
        _power_factor("load point", self.v_phase, self.i_line, abs(self.p_total))


# --- classical tests ----------------------------------------------------------------

def r1_from_dc(test: DcTest) -> float:
    """Stator phase resistance from the DC test on a star winding, R1 = U / (2·I), Ω."""
    return test.v_dc / (2.0 * test.i_dc)


def mechanical_losses(v0: ArrayLike, p0_prime: ArrayLike) -> float:
    """Mechanical losses from no-load points by extrapolation to V = 0, W.

    Fits P0' = a·V0² + p_mec (least squares) where P0' = P0 − 3·R1·I0²
    (iron losses ∝ V², mechanical losses constant at ~ synchronous speed).

    Args:
        v0: phase voltages of the no-load points, V (≥ 2 distinct values).
        p0_prime: P0 − 3·R1·I0² at each point, W.

    Returns:
        p_mec, the intercept at V = 0, W (≥ 0).
    """
    v = np.asarray(v0, dtype=float)
    p = np.asarray(p0_prime, dtype=float)
    if v.ndim != 1 or v.shape != p.shape:
        raise ValueError(f"v0 and p0_prime must be 1-D arrays of the same length, got {v.shape} and {p.shape}")
    if not (np.all(np.isfinite(v)) and np.all(np.isfinite(p))):
        raise ValueError("v0 and p0_prime must be finite")
    if np.any(v <= 0):
        raise ValueError("v0 must be > 0 V")
    if np.unique(v).size < 2:
        raise ValueError("mechanical loss separation needs at least 2 distinct voltages")
    _, p_mec = np.polyfit(v**2, p, 1)
    if p_mec < 0:
        raise ValueError(
            f"extrapolated mechanical losses are negative ({p_mec:.1f} W): check the no-load points"
        )
    return float(p_mec)


def no_load_branch(
    test: NoLoadTest, r1: float, p_mech: float = 0.0, method: Method = "exact"
) -> tuple[float, float]:
    """Magnetising branch (Rf, Xm) from the no-load test, Ω.

    P_fe = P0 − 3·R1·I0² − p_mec,  Q0 = sqrt((3·V0·I0)² − P0²).
    classical: Rf = 3·V0²/P_fe, Xm = 3·V0²/Q0 (drop in R1 neglected).
    exact:     same with E = |V0 − R1·I0| in place of V0.

    Args:
        test: no-load measurement.
        r1: stator phase resistance, Ω (≥ 0).
        p_mech: mechanical losses, W (≥ 0), e.g. from mechanical_losses().
        method: "classical" or "exact".

    Returns:
        (r_fe, x_m) in Ω, x_m at the test frequency.
    """
    _method(method)
    if not math.isfinite(r1) or r1 < 0:
        raise ValueError(f"r1 must be a finite number >= 0 Ω, got {r1!r}")
    if not math.isfinite(p_mech) or p_mech < 0:
        raise ValueError(f"p_mech must be a finite number >= 0 W, got {p_mech!r}")
    v, i, p = test.v_phase, test.i_line, test.p_total
    p_fe = p - 3.0 * r1 * i**2 - p_mech
    if p_fe <= 0:
        raise ValueError(
            f"iron losses P0 − 3·R1·I0² − p_mec = {p_fe:.1f} W must be > 0: check P0, R1 and p_mec"
        )
    cos_phi = _power_factor("no-load test", v, i, p)
    sin_phi = math.sqrt(1.0 - cos_phi**2)
    q0 = 3.0 * v * i * sin_phi
    if q0 <= 0:
        raise ValueError("no-load reactive power is zero: Xm cannot be identified")
    if method == "classical":
        e2 = v**2
    else:
        e2 = abs(v - r1 * i * complex(cos_phi, -sin_phi)) ** 2
    return 3.0 * e2 / p_fe, 3.0 * e2 / q0


def locked_rotor(
    test: LockedRotorTest,
    r1: float,
    f_rated: float,
    r_fe: float | None = None,
    x_m: float | None = None,
    method: Method = "exact",
) -> tuple[float, float]:
    """Rotor branch (R'2, X) from the locked-rotor test, Ω.

    classical: magnetising branch neglected, Rcc = Pcc/(3·Icc²),
               R'2 = Rcc − R1, X = sqrt(Zcc² − Rcc²).
    exact:     Z2 = 1 / (1/(Zcc − R1) − 1/Z_m), with Z_m = Rf ∥ jXm at the test frequency.

    Args:
        test: locked-rotor measurement.
        r1: stator phase resistance, Ω (≥ 0).
        f_rated: frequency to which X (and x_m) are referred, Hz.
        r_fe: iron-loss resistance, Ω (required for "exact").
        x_m: magnetising reactance at f_rated, Ω (required for "exact").
        method: "classical" or "exact".

    Returns:
        (r2p, x_leak) in Ω, x_leak referred to f_rated.
    """
    _method(method)
    _pos("f_rated", f_rated)
    if not math.isfinite(r1) or r1 < 0:
        raise ValueError(f"r1 must be a finite number >= 0 Ω, got {r1!r}")
    v, i, p = test.v_phase, test.i_line, test.p_total
    k = test.f / f_rated
    cos_phi = _power_factor("locked-rotor test", v, i, p)
    z_cc = (v / i) * complex(cos_phi, math.sqrt(1.0 - cos_phi**2))
    if method == "classical":
        z2 = z_cc - r1
    else:
        if r_fe is None or x_m is None:
            raise ValueError("method 'exact' needs r_fe and x_m from the no-load test")
        _pos("r_fe", r_fe)
        _pos("x_m", x_m)
        z_m = 1.0 / (1.0 / r_fe + 1.0 / complex(0.0, x_m * k))
        z2 = 1.0 / (1.0 / (z_cc - r1) - 1.0 / z_m)
    if z2.real <= 0:
        raise ValueError(f"identified R'2 = {z2.real:.4f} Ω is not > 0: R1 too large for this test")
    if z2.imag <= 0:
        raise ValueError(f"identified X = {z2.imag:.4f} Ω is not > 0: check the locked-rotor test")
    return z2.real, z2.imag / k


def identify(
    dc: DcTest | None,
    no_load: NoLoadTest,
    locked: LockedRotorTest,
    pole_pairs: int,
    p_mech: float = 0.0,
    method: Method = "exact",
    source: str = "TP3",
    is_demo: bool = False,
) -> MotorParams:
    """Γ circuit from the DC, no-load and locked-rotor tests.

    Rated voltage and frequency are those of the no-load test.

    Args:
        dc: DC test, or None to take R1 = 0 (TD5 hypothesis R1 ≈ 0).
        no_load: no-load test at rated voltage.
        locked: locked-rotor test.
        pole_pairs: number of pole pairs p.
        p_mech: mechanical losses, W.
        method: "classical" or "exact".
        source: label stored in the MotorParams.
        is_demo: True if the measurements are demo data.
    """
    _method(method)
    r1 = 0.0 if dc is None else r1_from_dc(dc)
    r_fe, x_m = no_load_branch(no_load, r1, p_mech, method)
    r2p, x = locked_rotor(locked, r1, no_load.f, r_fe=r_fe, x_m=x_m, method=method)
    return MotorParams(
        v_phase=no_load.v_phase,
        f_rated=no_load.f,
        pole_pairs=pole_pairs,
        r1=r1,
        r2p=r2p,
        x_leak=x,
        x_m=x_m,
        r_fe=r_fe,
        source=source,
        is_demo=is_demo,
    )


# --- least-squares fit ----------------------------------------------------------------

@dataclass(frozen=True)
class FitResult:
    """Result of fit_circuit.

    Attributes:
        motor: fitted circuit (r1, p, rated V and f kept from the start).
        success: True if the optimiser converged.
        rms_relative_error: RMS of the residuals (I relative to I, P relative to 3·V·I).
        n_points: number of points used.
    """

    motor: MotorParams
    success: bool
    rms_relative_error: float
    n_points: int


_FIT_FIELDS = ("r2p", "x_leak", "x_m", "r_fe")


def fit_circuit(points: Sequence[LoadPoint], start: MotorParams, source: str = "fit") -> FitResult:
    """Least-squares fit of R'2, X, Xm, Rf to measured (V, f, g, I1, P1) points.

    R1, p, rated V and f are taken from `start` and kept fixed. The four
    unknowns are fitted in log space (they stay > 0 by construction).
    Residuals per point: (I_model − I)/I and (P_model − P)/(3·V·I).

    Args:
        points: measured points, at least 2 with distinct slips.
        start: initial circuit (e.g. from identify()).
        source: label of the returned MotorParams.
    """
    pts = list(points)
    if len(pts) < 2 or len({p.slip for p in pts}) < 2:
        raise ValueError(f"fit_circuit needs at least 2 points with distinct slips, got {len(pts)}")
    if not isinstance(start, MotorParams):
        raise ValueError(f"start must be a MotorParams, got {type(start).__name__}")

    def build(x: np.ndarray) -> MotorParams:
        vals = dict(zip(_FIT_FIELDS, np.exp(x)))
        return replace(start, source=source, **vals)

    def residuals(x: np.ndarray) -> np.ndarray:
        m = build(x)
        out = []
        for p in pts:
            op = circuit.operating_point(m, p.slip, v_phase=p.v_phase, f=p.f)
            out.append((op.i1 - p.i_line) / p.i_line)
            out.append((op.p_in - p.p_total) / (3.0 * p.v_phase * p.i_line))
        return np.asarray(out)

    x0 = np.log([getattr(start, n) for n in _FIT_FIELDS])
    sol = least_squares(residuals, x0, method="lm", xtol=1e-14, ftol=1e-14, gtol=1e-14)
    res = residuals(sol.x)
    return FitResult(
        motor=build(sol.x),
        success=bool(sol.success),
        rms_relative_error=float(np.sqrt(np.mean(res**2))),
        n_points=len(pts),
    )
