"""Identification of the Γ equivalent circuit from the TP3 / TD5 tests.

Circuit layouts (see core.session.MotorParams):
  "tp3" (default, TP3 Figure 1): V1 → R1 (carries I1) → Rf ∥ jXm → jX + R'2/g
  "terminals": Rf ∥ jXm across V1, in parallel with R1 + jX + R'2/g
The "exact" methods invert the chosen layout; the "classical" ones are the
course formulas (TP3 recipe) and do not depend on the layout.

Two routes:
- classical formulas (DC, no-load, locked-rotor tests), in a "classical"
  variant (course approximations) and an "exact" variant (inverts the
  circuit above with no approximation);
- a least-squares fit of R'2, X, Xm, Rf to any set of measured points.

Per-phase quantities, star connection; powers are three-phase totals.
Records can be built from the line voltage U as measured on the bench (TD5:
"no-load test 380 V, 3.7 A, 350 W"); V = U/√3 is used internally.

Notation (TD5 → here): Rs → R1, Rm → Rf (r_fe), Xm → Xm (x_m),
R'2 → R'2 (r2p), X = X1 + X'2 → X (x_leak), J0/I0, P0, Ucc/Icc/Pcc as is.

Classical chain (run_identification):
  1. DC test → R1 cold = U_dc/(2·I_dc); then R1 hot = R1 cold·(234,5 + T_hot)/(234,5 + T_cold)
  2. no-load series → P0' = P0 − 3·R1·I0², fitted as a·U0² + p_mec (extrapolation to U = 0)
  3. rated no-load point → P_fe = P0' − p_mec, Rf = 3·V0²/P_fe, Xm = 3·V0²/Q0
  4. locked-rotor test → R'2 = Pcc/(3·Icc²) − R1, X = sqrt(Zcc² − Rcc²)
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, replace
from typing import Literal, Sequence

import numpy as np
from numpy.typing import ArrayLike
from scipy.optimize import least_squares
from scipy.stats import t as student_t

from evlab.core import circuit
from evlab.core.circuit import COPPER_T0, T_ZERO_C
from evlab.core.session import LAYOUTS, Layout, MotorParams

Method = Literal["classical", "exact"]


def _pos(name: str, value: float) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite number > 0, got {value!r}")


def _method(method: str) -> None:
    if method not in ("classical", "exact"):
        raise ValueError(f"method must be 'classical' or 'exact', got {method!r}")


def _layout(layout: str) -> None:
    if layout not in LAYOUTS:
        raise ValueError(f"layout must be one of {LAYOUTS}, got {layout!r}")


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
        temperature_k: winding temperature during the DC test, K (default 20 °C).
    """

    v_dc: float
    i_dc: float
    temperature_k: float = 293.15

    def __post_init__(self) -> None:
        _pos("v_dc", self.v_dc)
        _pos("i_dc", self.i_dc)
        _pos("temperature_k", self.temperature_k)


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

    @classmethod
    def from_line(cls, u_line: float, i_line: float, p_total: float, f: float) -> "NoLoadTest":
        """Build from bench readings: line voltage U (V), line current (A), 3-phase power (W), f (Hz)."""
        _pos("u_line", u_line)
        return cls(v_phase=u_line / math.sqrt(3.0), i_line=i_line, p_total=p_total, f=f)


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

    @classmethod
    def from_line(cls, u_line: float, i_line: float, p_total: float, f: float) -> "LockedRotorTest":
        """Build from bench readings: line voltage U (V), line current (A), 3-phase power (W), f (Hz)."""
        _pos("u_line", u_line)
        return cls(v_phase=u_line / math.sqrt(3.0), i_line=i_line, p_total=p_total, f=f)


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
    """R1 = U_dc / (2·I_dc), Ω: between two terminals of a star the current crosses two phases."""
    return test.v_dc / (2.0 * test.i_dc)


def r1_at_temperature(r_measured: float, t_measured_k: float, t_k: float) -> float:
    """R(T) = R(T_meas)·(234,5 + T°C)/(234,5 + T_meas°C), Ω: copper resistance is linear in T.

    With T_meas = 20 °C this is R(T) = R20·(234,5 + T)/254,5 (CLAUDE.md).

    Args:
        r_measured: resistance measured at t_measured_k, Ω (> 0).
        t_measured_k: temperature of the measurement, K (> 0).
        t_k: temperature to convert to, K (> 0).
    """
    _pos("r_measured", r_measured)
    _pos("t_measured_k", t_measured_k)
    _pos("t_k", t_k)
    return r_measured * (COPPER_T0 + t_k - T_ZERO_C) / (COPPER_T0 + t_measured_k - T_ZERO_C)


def mechanical_losses(v0: ArrayLike, p0_prime: ArrayLike) -> float:
    """p_mec = intercept at U = 0 of the straight line P0' = a·U0² + p_mec, W.

    Iron losses grow as U² (flux ∝ U), mechanical losses stay constant near
    synchronous speed, so the line through (U0², P0') cuts the axis at p_mec.
    Phase or line voltages give the same intercept (U² = 3·V²).

    Args:
        v0: voltages of the no-load points (phase or line), V (≥ 2 distinct values).
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
    test: NoLoadTest,
    r1: float,
    p_mech: float = 0.0,
    method: Method = "exact",
    layout: Layout = "tp3",
) -> tuple[float, float]:
    """Magnetising branch (Rf, Xm) from the no-load test, Ω.

    Q0 = sqrt((3·V0·I0)² − P0²); R1 absorbs no reactive power.
    classical:       P_fe = P0 − 3·R1·I0² − p_mec, Rf = 3·V0²/P_fe, Xm = 3·V0²/Q0 (R1 drop neglected).
    exact, tp3:      same P_fe, with E = |V0 − R1·I0| in place of V0 (R1 carries I0).
    exact, terminals: P_fe = P0 − p_mec, Rf = 3·V0²/P_fe, Xm = 3·V0²/Q0 (R1 carries no no-load current).

    Args:
        test: no-load measurement.
        r1: stator phase resistance, Ω (≥ 0).
        p_mech: mechanical losses, W (≥ 0), e.g. from mechanical_losses().
        method: "classical" or "exact".
        layout: circuit layout inverted by the "exact" method.

    Returns:
        (r_fe, x_m) in Ω, x_m at the test frequency.
    """
    r_fe, x_m, _, _ = _no_load_branch(test, r1, p_mech, method, layout)
    return r_fe, x_m


def _no_load_branch(
    test: NoLoadTest, r1: float, p_mech: float, method: Method, layout: Layout
) -> tuple[float, float, float, float]:
    """(Rf, Xm, P_fe, E) — see no_load_branch."""
    _method(method)
    _layout(layout)
    if not math.isfinite(r1) or r1 < 0:
        raise ValueError(f"r1 must be a finite number >= 0 Ω, got {r1!r}")
    if not math.isfinite(p_mech) or p_mech < 0:
        raise ValueError(f"p_mech must be a finite number >= 0 W, got {p_mech!r}")
    v, i, p = test.v_phase, test.i_line, test.p_total
    r1_noload = 0.0 if (method == "exact" and layout == "terminals") else r1
    p_fe = p - 3.0 * r1_noload * i**2 - p_mech
    if p_fe <= 0:
        raise ValueError(
            f"iron losses P0 − 3·R1·I0² − p_mec = {p_fe:.1f} W must be > 0: check P0, R1 and p_mec"
        )
    cos_phi = _power_factor("no-load test", v, i, p)
    sin_phi = math.sqrt(1.0 - cos_phi**2)
    q0 = 3.0 * v * i * sin_phi
    if q0 <= 0:
        raise ValueError("no-load reactive power is zero: Xm cannot be identified")
    if method == "classical" or layout == "terminals":
        e2 = v**2
    else:
        e2 = abs(v - r1 * i * complex(cos_phi, -sin_phi)) ** 2
    return 3.0 * e2 / p_fe, 3.0 * e2 / q0, p_fe, math.sqrt(e2)


def locked_rotor(
    test: LockedRotorTest,
    r1: float,
    f_rated: float,
    r_fe: float | None = None,
    x_m: float | None = None,
    method: Method = "exact",
    layout: Layout = "tp3",
) -> tuple[float, float]:
    """Rotor branch (R'2, X) from the locked-rotor test, Ω.

    classical:        magnetising branch neglected, Rcc = Pcc/(3·Icc²),
                      R'2 = Rcc − R1, X = sqrt(Zcc² − Rcc²).
    exact, tp3:       Z2 = 1 / (1/(Zcc − R1) − 1/Z_m)   (remove R1, then Z_m in parallel).
    exact, terminals: R1 + Z2 = 1 / (1/Zcc − 1/Z_m)     (remove Z_m in parallel, then R1).
    Z_m = Rf ∥ jXm at the test frequency.

    Args:
        test: locked-rotor measurement.
        r1: stator phase resistance, Ω (≥ 0).
        f_rated: frequency to which X (and x_m) are referred, Hz.
        r_fe: iron-loss resistance, Ω (required for "exact").
        x_m: magnetising reactance at f_rated, Ω (required for "exact").
        method: "classical" or "exact".
        layout: circuit layout inverted by the "exact" method.

    Returns:
        (r2p, x_leak) in Ω, x_leak referred to f_rated.
    """
    _method(method)
    _layout(layout)
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
        if layout == "tp3":
            z2 = 1.0 / (1.0 / (z_cc - r1) - 1.0 / z_m)
        else:
            z2 = 1.0 / (1.0 / z_cc - 1.0 / z_m) - r1
    if z2.real <= 0:
        raise ValueError(f"identified R'2 = {z2.real:.4f} Ω is not > 0: R1 too large for this test")
    if z2.imag <= 0:
        raise ValueError(f"identified X = {z2.imag:.4f} Ω is not > 0: check the locked-rotor test")
    return z2.real, z2.imag / k


@dataclass(frozen=True)
class TestRecords:
    """Everything measured on the bench for one motor (TP3 / TD5 test sequence).

    Attributes:
        dc: DC test, or None to take R1 = 0 (TD5 Ex 1 hypothesis R1 ≈ 0).
        t_hot_k: winding temperature during the no-load / locked-rotor tests, K.
            None: R1 is used as measured by the DC test (e.g. TD5 "hot resistance").
        no_load: no-load tests, one per voltage; the one closest to v_rated
            (within 10 %) gives Rf and Xm, the whole series gives p_mec.
        locked: locked-rotor test.
        pole_pairs: number of pole pairs p (nameplate).
        v_rated: rated phase voltage, V (nameplate).
        f_rated: rated frequency, Hz (nameplate).
        p_mech: mechanical losses, W, if known (TD5: "negligible" → 0);
            None: separated from the no-load series by the U² extrapolation.
    """

    dc: DcTest | None
    t_hot_k: float | None
    no_load: tuple[NoLoadTest, ...]
    locked: LockedRotorTest
    pole_pairs: int
    v_rated: float
    f_rated: float
    p_mech: float | None = None

    def __post_init__(self) -> None:
        if len(self.no_load) == 0:
            raise ValueError("at least one no-load test is needed")
        if self.t_hot_k is not None:
            _pos("t_hot_k", self.t_hot_k)
        _pos("v_rated", self.v_rated)
        _pos("f_rated", self.f_rated)
        if self.p_mech is not None and (not math.isfinite(self.p_mech) or self.p_mech < 0):
            raise ValueError(f"p_mech must be None or a finite number >= 0 W, got {self.p_mech!r}")
        if any(t.f != self.no_load[0].f for t in self.no_load):
            raise ValueError("all no-load tests must be at the same frequency")
        self.rated_no_load()  # validates that a rated point exists

    def rated_no_load(self) -> NoLoadTest:
        """No-load test closest to the rated voltage (must be within 10 %, i.e. 5σ of a 2 % voltmeter)."""
        best = min(self.no_load, key=lambda t: abs(t.v_phase - self.v_rated))
        if abs(best.v_phase - self.v_rated) > 0.10 * self.v_rated:
            raise ValueError(
                f"no no-load test within 10 % of the rated voltage {self.v_rated:.1f} V "
                f"(closest: {best.v_phase:.1f} V)"
            )
        return best


@dataclass(frozen=True)
class IdentificationReport:
    """Result of run_identification, with the intermediate values of each step.

    Attributes:
        motor: identified circuit.
        method: "classical" or "exact".
        r1_cold: R1 at the DC-test temperature, Ω.
        r1_hot: R1 used in the circuit (at t_hot_k), Ω.
        p_mech: mechanical losses used, W (given or extrapolated).
        p_fe: iron losses at the rated no-load point, W.
        e0: voltage across the magnetising branch at the rated no-load point, V.
        cos_phi0: no-load power factor.
        cos_phi_cc: locked-rotor power factor.
        n_no_load: number of no-load points used for the p_mec separation.
    """

    motor: MotorParams
    method: str
    r1_cold: float
    r1_hot: float
    p_mech: float
    p_fe: float
    e0: float
    cos_phi0: float
    cos_phi_cc: float
    n_no_load: int


def run_identification(
    records: TestRecords,
    method: Method = "exact",
    layout: Layout = "tp3",
    source: str = "TP3",
    is_demo: bool = False,
) -> IdentificationReport:
    """Whole chain: DC → R1 hot → p_mec by U² extrapolation → Rf, Xm → R'2, X → MotorParams.

    Args:
        records: bench measurements.
        method: "classical" (course formulas) or "exact" (inverts the layout).
        layout: circuit layout ("exact" inverts it; stored in the result).
        source: label stored in the MotorParams.
        is_demo: True if the records are demo data (labelled "démo" downstream).
    """
    _method(method)
    _layout(layout)
    if records.dc is None:
        r1_cold = r1_hot = 0.0
    else:
        r1_cold = r1_from_dc(records.dc)
        r1_hot = (
            r1_cold
            if records.t_hot_k is None
            else r1_at_temperature(r1_cold, records.dc.temperature_k, records.t_hot_k)
        )

    if records.p_mech is not None:
        p_mech = records.p_mech
    else:
        r1_noload = 0.0 if (method == "exact" and layout == "terminals") else r1_hot
        u0 = np.array([math.sqrt(3.0) * t.v_phase for t in records.no_load])
        p0p = np.array([t.p_total - 3.0 * r1_noload * t.i_line**2 for t in records.no_load])
        p_mech = mechanical_losses(u0, p0p)

    rated = records.rated_no_load()
    r_fe, x_m, p_fe, e0 = _no_load_branch(rated, r1_hot, p_mech, method, layout)
    f0 = rated.f
    x_m_rated = x_m * records.f_rated / f0
    r2p, x = locked_rotor(records.locked, r1_hot, records.f_rated, r_fe=r_fe, x_m=x_m_rated,
                          method=method, layout=layout)
    motor = MotorParams(
        v_phase=records.v_rated,
        f_rated=records.f_rated,
        pole_pairs=records.pole_pairs,
        r1=r1_hot,
        r2p=r2p,
        x_leak=x,
        x_m=x_m_rated,
        r_fe=r_fe,
        source=source,
        is_demo=is_demo,
        layout=layout,
    )
    lk = records.locked
    return IdentificationReport(
        motor=motor,
        method=method,
        r1_cold=r1_cold,
        r1_hot=r1_hot,
        p_mech=p_mech,
        p_fe=p_fe,
        e0=e0,
        cos_phi0=_power_factor("no-load test", rated.v_phase, rated.i_line, rated.p_total),
        cos_phi_cc=_power_factor("locked-rotor test", lk.v_phase, lk.i_line, lk.p_total),
        n_no_load=len(records.no_load),
    )


def identify(
    dc: DcTest | None,
    no_load: NoLoadTest,
    locked: LockedRotorTest,
    pole_pairs: int,
    p_mech: float = 0.0,
    method: Method = "exact",
    source: str = "TP3",
    is_demo: bool = False,
    layout: Layout = "tp3",
) -> MotorParams:
    """Γ circuit from one DC, one rated no-load and one locked-rotor test (no temperature correction).

    Shortcut for run_identification with rated V and f taken from the no-load test.

    Args:
        dc: DC test, or None to take R1 = 0 (TD5 hypothesis R1 ≈ 0).
        no_load: no-load test at rated voltage.
        locked: locked-rotor test.
        pole_pairs: number of pole pairs p.
        p_mech: mechanical losses, W.
        method: "classical" or "exact".
        source: label stored in the MotorParams.
        is_demo: True if the measurements are demo data.
        layout: circuit layout ("exact" inverts it; stored in the result).
    """
    records = TestRecords(
        dc=dc, t_hot_k=None, no_load=(no_load,), locked=locked, pole_pairs=pole_pairs,
        v_rated=no_load.v_phase, f_rated=no_load.f, p_mech=p_mech,
    )
    return run_identification(records, method, layout, source, is_demo).motor


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

    R1, p, rated V and f and the layout are taken from `start` and kept fixed. The four
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


# --- load-test fit of (Xm, X, R'2) -------------------------------------------------

class IdentifiabilityWarning(UserWarning):
    """Two fitted parameters are so correlated that the data cannot separate them."""


@dataclass(frozen=True)
class LoadTestPoint:
    """One load-test point.

    Attributes:
        slip: slip g from the tachometer (dimensionless).
        i_line: line current, A.
        torque: shaft torque, N·m (torquemeter or dynamometer).
        power_factor: cos φ1 (dimensionless, |cos φ| ≤ 1).
        v_phase: phase voltage, V.
        f: supply frequency, Hz.
    """

    slip: float
    i_line: float
    torque: float
    power_factor: float
    v_phase: float
    f: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.slip):
            raise ValueError(f"slip must be finite, got {self.slip!r}")
        _pos("i_line", self.i_line)
        _pos("v_phase", self.v_phase)
        _pos("f", self.f)
        if not math.isfinite(self.torque):
            raise ValueError(f"torque must be finite, got {self.torque!r}")
        if not math.isfinite(self.power_factor) or abs(self.power_factor) > 1.0:
            raise ValueError(f"power_factor must be in [-1, 1], got {self.power_factor!r}")


@dataclass(frozen=True)
class StartResult:
    """One run of the multistart: initial and final (Xm, X, R'2) in Ω, final cost."""

    start: tuple[float, float, float]
    end: tuple[float, float, float]
    cost: float


@dataclass(frozen=True)
class LoadFitResult:
    """Result of fit_load_points.

    Attributes:
        motor: circuit with the fitted Xm, X, R'2 (R1, Rf and the rest from `start`).
        success: optimiser status of the best run.
        cost: robust cost of the best run.
        rms: RMS of the normalised residuals (dimensionless; ≈ relative noise level).
        std: standard error of each fitted parameter, Ω.
        ci95: 95 % confidence interval of each fitted parameter, Ω.
        correlation: 3×3 correlation matrix in the order PARAM_NAMES.
        high_correlation: parameter pairs with |ρ| > 0,95.
        multistart: every run of the multistart.
        n_converged: runs that ended on the best parameters (relative distance < 1e-4).
    """

    motor: MotorParams
    success: bool
    cost: float
    rms: float
    std: dict[str, float]
    ci95: dict[str, tuple[float, float]]
    correlation: np.ndarray
    high_correlation: tuple[tuple[str, str, float], ...]
    multistart: tuple[StartResult, ...]
    n_converged: int


LOAD_FIT_NAMES = ("x_m", "x_leak", "r2p")
CORRELATION_LIMIT = 0.95


def check_correlation(
    corr: np.ndarray, names: Sequence[str], limit: float = CORRELATION_LIMIT
) -> tuple[tuple[str, str, float], ...]:
    """Pairs with |ρ| > limit; warns IdentifiabilityWarning for each (the data cannot separate them).

    Args:
        corr: square correlation matrix (dimensionless).
        names: parameter names, in matrix order.
        limit: threshold on |ρ|, in (0, 1).
    """
    c = np.asarray(corr, dtype=float)
    if c.ndim != 2 or c.shape[0] != c.shape[1] or c.shape[0] != len(names):
        raise ValueError(f"corr must be a {len(names)}×{len(names)} matrix, got shape {c.shape}")
    if not 0 < limit < 1:
        raise ValueError(f"limit must be in (0, 1), got {limit!r}")
    high = tuple(
        (names[a], names[b], float(c[a, b]))
        for a in range(len(names)) for b in range(a + 1, len(names))
        if abs(c[a, b]) > limit
    )
    for a, b, rho in high:
        warnings.warn(
            f"correlation {a}–{b} = {rho:+.3f} (|ρ| > {limit}): the data cannot separate "
            "these parameters; add load points over a wider slip range (towards breakdown)",
            IdentifiabilityWarning,
            stacklevel=3,
        )
    return high


def fit_load_points(
    points: Sequence[LoadTestPoint],
    start: MotorParams,
    p_mech: float = 0.0,
    n_starts: int = 10,
    f_scale: float = 0.05,
    seed: int = 0,
    normalise: Literal["quantity", "point"] = "quantity",
) -> LoadFitResult:
    """Least-squares fit of (Xm, X, R'2) to load points (g, I, T, cos φ); R1 and Rf stay fixed.

    R1 comes from the DC test and Rf from the no-load test (`start`, e.g. the
    classical result): load points barely depend on Rf (docs/assumptions.md A13).
    normalise="quantity": residual = (model − measured) / RMS(measured quantity),
    so current, torque and cos φ weigh the same (each point weighs the same in
    absolute terms). normalise="point": residual = (model − measured)/|measured|,
    which matches a relative (class-of-accuracy) instrument error; needs no
    zero reading. Model shaft torque = T_em − p_mec/Ω.
    Loss soft_l1 with f_scale (residuals beyond ≈ f_scale are down-weighted).
    Confidence intervals: linearised, Cov = s²·(JᵀJ)⁻¹ with J the Jacobian of the
    plain residuals at the optimum, s² = Σr²/(m − 3), Student t with m − 3 dof.
    They do not include the uncertainty of the fixed R1 and Rf.

    Args:
        points: load-test points, at least 3.
        start: initial circuit (classical result); gives R1, Rf, p, layout, rating.
        p_mech: mechanical losses, W (≥ 0), to convert T_em to shaft torque.
        n_starts: multistart runs (≥ 1): `start`, then log-uniform draws in [¼, 4]×start.
        f_scale: soft_l1 scale, in normalised residual units (> 0).
        seed: random seed of the multistart draws.
        normalise: "quantity" (default) or "point", see above.
    """
    if normalise not in ("quantity", "point"):
        raise ValueError(f"normalise must be 'quantity' or 'point', got {normalise!r}")
    pts = list(points)
    if len(pts) < 3:
        raise ValueError(f"fit_load_points needs at least 3 points, got {len(pts)}")
    if not isinstance(start, MotorParams):
        raise ValueError(f"start must be a MotorParams, got {type(start).__name__}")
    if not isinstance(n_starts, int) or n_starts < 1:
        raise ValueError(f"n_starts must be an integer >= 1, got {n_starts!r}")
    _pos("f_scale", f_scale)
    if not math.isfinite(p_mech) or p_mech < 0:
        raise ValueError(f"p_mech must be a finite number >= 0 W, got {p_mech!r}")

    g = np.array([p.slip for p in pts])
    meas = {
        "i": np.array([p.i_line for p in pts]),
        "t": np.array([p.torque for p in pts]),
        "pf": np.array([p.power_factor for p in pts]),
    }
    if normalise == "quantity":
        scale = {k: np.full_like(v, np.sqrt(np.mean(v**2))) for k, v in meas.items()}
    else:
        scale = {k: np.abs(v) for k, v in meas.items()}
    for k, sc in scale.items():
        if np.any(sc == 0):
            raise ValueError(f"measured {k} is zero ({normalise} normalisation): cannot normalise")
    groups: dict[tuple[float, float], list[int]] = {}
    for k, p in enumerate(pts):
        groups.setdefault((p.v_phase, p.f), []).append(k)

    def build(theta: np.ndarray) -> MotorParams:
        return replace(start, **dict(zip(LOAD_FIT_NAMES, (float(v) for v in theta))))

    def residuals(theta: np.ndarray) -> np.ndarray:
        m = build(theta)
        i_mod = np.empty_like(g)
        t_mod = np.empty_like(g)
        pf_mod = np.empty_like(g)
        for (v, f), idx in groups.items():
            op = circuit.operating_point(m, g[idx], v_phase=v, f=f)
            i_mod[idx] = op.i1
            t_mod[idx] = op.torque - p_mech / op.omega_mech
            pf_mod[idx] = op.power_factor
        return np.concatenate([
            (i_mod - meas["i"]) / scale["i"],
            (t_mod - meas["t"]) / scale["t"],
            (pf_mod - meas["pf"]) / scale["pf"],
        ])

    theta0 = np.array([getattr(start, n) for n in LOAD_FIT_NAMES])
    rng = np.random.default_rng(seed)
    starts = [theta0] + [theta0 * 4.0 ** rng.uniform(-1.0, 1.0, 3) for _ in range(n_starts - 1)]
    runs = []
    for th in starts:
        sol = least_squares(residuals, th, bounds=(1e-9, np.inf), loss="soft_l1",
                            f_scale=f_scale, x_scale="jac", xtol=1e-12, ftol=1e-12, gtol=1e-12)
        runs.append((sol, th))
    best, _ = min(runs, key=lambda r: r[0].cost)
    theta = best.x
    n_conv = sum(bool(np.all(np.abs(s.x / theta - 1.0) < 1e-4)) for s, _ in runs)

    # linearised uncertainty from the plain residuals
    r = residuals(theta)
    jac = np.empty((r.size, theta.size))
    for k in range(theta.size):
        h = 1e-6 * theta[k]
        tp, tm = theta.copy(), theta.copy()
        tp[k] += h
        tm[k] -= h
        jac[:, k] = (residuals(tp) - residuals(tm)) / (2.0 * h)
    dof = r.size - theta.size
    s2 = float(r @ r) / dof
    try:
        cov = s2 * np.linalg.inv(jac.T @ jac)
    except np.linalg.LinAlgError as exc:
        raise ValueError("Jacobian is singular: the load points do not determine Xm, X, R'2") from exc
    std = np.sqrt(np.diag(cov))
    corr = cov / np.outer(std, std)
    t95 = float(student_t.ppf(0.975, dof))
    high = check_correlation(corr, LOAD_FIT_NAMES)
    return LoadFitResult(
        motor=replace(build(theta), source=f"{start.source} + fit charge"),
        success=bool(best.success),
        cost=float(best.cost),
        rms=float(np.sqrt(np.mean(r**2))),
        std=dict(zip(LOAD_FIT_NAMES, std.tolist())),
        ci95={n: (float(v - t95 * e), float(v + t95 * e)) for n, v, e in zip(LOAD_FIT_NAMES, theta, std)},
        correlation=corr,
        high_correlation=high,
        multistart=tuple(StartResult(tuple(th.tolist()), tuple(s.x.tolist()), float(s.cost)) for s, th in runs),
        n_converged=n_conv,
    )
