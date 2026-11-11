"""Two-node thermal model of the motor and insulation life (stage 6, tab 5).

Network: winding (C_w) —R_ws— iron/frame (C_s) —R_sa— ambient (T_a).
  C_w·dT_w/dt = P_w(T_w) − (T_w − T_s)/R_ws
  C_s·dT_s/dt = P_s + (T_w − T_s)/R_ws − (T_s − T_a)/R_sa
P_w: stator copper losses of the cycle, read from the efficiency map (same
motor, tab 3) and recomputed at every step from the winding temperature with the
copper law: P_w = P_cu1,map·(234,5 + T_w)/(234,5 + T_map) (°C inside the brackets).
P_s: iron + rotor copper losses (to the iron/frame node). Mechanical and
inverter losses are not in the motor's thermal network (A27).

Integrators: implicit Euler at the loss sampling step (each step is an exact
2×2 linear solve, since P_w is linear in T_w) or scipy solve_ivp (RK45).

C_w, C_s, R_ws, R_sa are démo values (A26): TP3 gives no timed hot/cold
resistance readings. fit_cooling_curve is ready to fit the winding time
constant when such readings exist.

Insulation life uses the 10 K rule (Montsinger): at constant T, L = L_ref·2^((T_class − T)/10),
with L_ref = 20 000 h at the class temperature. Under a varying T_w(t) the ageing
RATES add (Miner): L = L_ref / mean(2^((T_w − T_class)/10)) over the last cycle,
which is shorter than the life at the mean temperature (the rule is convex in T).
It is an ORDER OF MAGNITUDE only: the rule is empirical and the hot spot is hotter
than the winding average computed here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike
from scipy.integrate import solve_ivp

from evlab.core import losses, vehicle
from evlab.core.circuit import check_copper_temperature
from evlab.core.session import MotorParams

T_ZERO_C = 273.15
COPPER_T0 = 234.5  # °C
INSULATION_CLASSES = {"A": 105.0, "E": 120.0, "B": 130.0, "F": 155.0, "H": 180.0}  # °C (IEC 60085)
L_REF_HOURS = 20_000.0  # life at the class temperature (A28)


def _pos(name: str, x: float) -> None:
    if not math.isfinite(x) or x <= 0:
        raise ValueError(f"{name} must be a finite number > 0, got {x!r}")


@dataclass(frozen=True)
class ThermalParams:
    """Two-node network (SI).

    Attributes:
        c_w: winding heat capacity, J/K.  c_s: iron/frame heat capacity, J/K.
        r_ws: winding → frame thermal resistance, K/W.  r_sa: frame → ambient, K/W.
        t_ambient_k: ambient temperature, K.  is_demo: démo values.
    """

    c_w: float
    c_s: float
    r_ws: float
    r_sa: float
    t_ambient_k: float = 298.15
    is_demo: bool = False

    def __post_init__(self) -> None:
        for n in ("c_w", "c_s", "r_ws", "r_sa", "t_ambient_k"):
            _pos(n, getattr(self, n))


DEMO_NETWORK = {"c_w": 3000.0, "c_s": 25_000.0, "r_ws": 0.10, "r_sa": 0.04}  # docs/assumptions.md A26


def demo_thermal() -> ThermalParams:
    """Démo network for a ~9 kW totally enclosed motor (A26)."""
    return ThermalParams(**DEMO_NETWORK, t_ambient_k=298.15, is_demo=True)


def demo_fields(p: ThermalParams) -> tuple[str, ...]:
    """Network fields of p still at their A26 démo value (one flag per field; the ambient is a user input)."""
    return tuple(name for name, value in DEMO_NETWORK.items() if getattr(p, name) == value)


def stator_copper_missing(m: MotorParams) -> bool:
    """True when the motor has R1 = 0 (TD5 Ex 1 hypothesis): the map has no stator copper
    losses, so the winding node is heated only through the frame (results not meaningful)."""
    return m.r1 == 0


def time_constants(p: ThermalParams) -> tuple[float, float]:
    """(τ_fast, τ_slow) = −1/λ of the 2×2 network matrix, s (λ from the characteristic quadratic)."""
    a11 = -1.0 / (p.r_ws * p.c_w)
    a12 = 1.0 / (p.r_ws * p.c_w)
    a21 = 1.0 / (p.r_ws * p.c_s)
    a22 = -(1.0 / p.r_ws + 1.0 / p.r_sa) / p.c_s
    tr, det = a11 + a22, a11 * a22 - a12 * a21
    disc = math.sqrt(tr * tr - 4.0 * det)
    lam_fast, lam_slow = (tr - disc) / 2.0, (tr + disc) / 2.0
    return -1.0 / lam_fast, -1.0 / lam_slow


def _copper_factor(copper_ref_k: float | None) -> tuple[float, float]:
    """P_w(T) = P0·(k0 + k1·T): (k0, k1); without a reference temperature P_w is constant."""
    if copper_ref_k is None:
        return 1.0, 0.0
    check_copper_temperature("copper_ref_k", copper_ref_k)
    den = COPPER_T0 + copper_ref_k - T_ZERO_C
    return (COPPER_T0 - T_ZERO_C) / den, 1.0 / den


def steady_state(p: ThermalParams, p_w: float, p_s: float, copper_ref_k: float | None = None) -> tuple[float, float]:
    """(T_w, T_s) at constant losses, K: the network's linear steady state (with the R1(T) feedback if asked).

    With the R1(T) feedback the copper losses grow with T_w; when they grow faster than
    the network removes heat (det ≤ 0, i.e. p_w·k1 ≥ 1/(R_ws + R_sa)) there is no steady
    state: ValueError("emballement thermique").

    Args:
        p: network.  p_w: stator copper losses at copper_ref_k, W (≥ 0).
        p_s: iron + rotor losses, W (≥ 0).  copper_ref_k: temperature of p_w, K (None: constant p_w).
    """
    for name, x in (("p_w", p_w), ("p_s", p_s)):
        if not math.isfinite(x) or x < 0:
            raise ValueError(f"{name} must be a finite number >= 0 W, got {x!r}")
    k0, k1 = _copper_factor(copper_ref_k)
    g_ws, g_sa = 1.0 / p.r_ws, 1.0 / p.r_sa
    # g_ws (T_w − T_s) = p_w (k0 + k1 T_w) ;  g_sa (T_s − T_a) = p_w (k0 + k1 T_w) + p_s
    a = np.array([[g_ws - p_w * k1, -g_ws], [-p_w * k1, g_sa]])
    b = np.array([p_w * k0, p_w * k0 + p_s + g_sa * p.t_ambient_k])
    det = float(np.linalg.det(a))
    if det <= 0 or a[0, 0] <= 0:
        raise ValueError(
            f"emballement thermique : {p_w:.0f} W de pertes cuivre croissent plus vite avec T "
            "que le réseau ne les évacue (pas de régime permanent)"
        )
    tw, ts = np.linalg.solve(a, b)
    if tw < p.t_ambient_k or ts < p.t_ambient_k:
        raise ValueError("emballement thermique : pas de régime permanent physique")
    return float(tw), float(ts)


def insulation_life(t_w_k: ArrayLike, insulation_class: str = "F", l_ref_h: float = L_REF_HOURS) -> float:
    """Insulation life by the 10 K rule, hours — an order of magnitude only.

    L = L_ref / mean(2^((T_w − T_class)/10)): the mean ageing rate over the samples of
    T_w (equally spaced in time); for a single temperature, L = L_ref·2^((T_class − T)/10).

    Args:
        t_w_k: winding temperature, K: a scalar or a 1-D profile (non-empty, > 0).
        insulation_class: A, E, B, F or H.  l_ref_h: life at the class temperature, h.
    """
    if insulation_class not in INSULATION_CLASSES:
        raise ValueError(f"insulation class must be one of {tuple(INSULATION_CLASSES)}, got {insulation_class!r}")
    t = np.atleast_1d(np.asarray(t_w_k, dtype=float))
    if t.ndim != 1 or t.size == 0 or not np.all(np.isfinite(t)) or np.any(t <= 0):
        raise ValueError(f"t_w_k must be a finite temperature > 0 K or a non-empty 1-D profile, got {t_w_k!r}")
    rate = np.mean(2.0 ** ((t - INSULATION_CLASSES[insulation_class] - T_ZERO_C) / 10.0))
    return float(l_ref_h / rate)


def order_of_magnitude(x: float) -> float:
    """10^floor(log10 x): the order of magnitude to display for an insulation life."""
    _pos("x", x)
    return 10.0 ** math.floor(math.log10(x))


@dataclass(frozen=True)
class ThermalSummary:
    """t_max (K, winding, whole run), t_mean (K, winding, last cycle), margin to the class (K),
    life (h, from the mean ageing rate over the last cycle)."""

    t_max: float
    t_mean: float
    margin: float
    life_hours: float
    insulation_class: str


@dataclass(frozen=True)
class ThermalResult:
    """Temperatures at the sampling instants (n_cycles·N + 1 values) and the losses used."""

    t: np.ndarray  # s
    t_w: np.ndarray  # winding, K
    t_s: np.ndarray  # iron/frame, K
    p_w: np.ndarray  # stator copper losses actually applied (with R1(T)), W
    p_s: np.ndarray  # iron/frame losses, W
    method: str
    summary: ThermalSummary


def simulate(
    p: ThermalParams,
    p_copper: ArrayLike,
    p_frame: ArrayLike,
    dt: float = 1.0,
    n_cycles: int = 1,
    copper_ref_k: float | None = None,
    method: str = "implicit",
    insulation_class: str = "F",
    t0_k: tuple[float, float] | None = None,
) -> ThermalResult:
    """Temperatures of the network over n_cycles repetitions of the per-step losses.

    Args:
        p: network.
        p_copper: stator copper losses per step at copper_ref_k, W (≥ 0).
        p_frame: iron + rotor losses per step, W (≥ 0), same length.
        dt: step of the loss series, s.
        n_cycles: cycles back to back (≥ 1).
        copper_ref_k: winding temperature of p_copper, K; None: no R1(T) recomputation.
        method: "implicit" (backward Euler, exact 2×2 solve per step) or "rk45" (solve_ivp).
        insulation_class: A, E, B, F or H.
        t0_k: initial (T_w, T_s), K; default ambient (cold start).
    """
    pc, pf = np.asarray(p_copper, dtype=float), np.asarray(p_frame, dtype=float)
    if pc.ndim != 1 or pc.shape != pf.shape or pc.size == 0:
        raise ValueError("p_copper and p_frame must be non-empty 1-D arrays of the same length")
    if not (np.all(np.isfinite(pc)) and np.all(np.isfinite(pf))) or np.any(pc < 0) or np.any(pf < 0):
        raise ValueError("losses must be finite and >= 0")
    _pos("dt", dt)
    if not isinstance(n_cycles, int) or n_cycles < 1:
        raise ValueError(f"n_cycles must be an integer >= 1, got {n_cycles!r}")
    if method not in ("implicit", "rk45"):
        raise ValueError(f"method must be 'implicit' or 'rk45', got {method!r}")
    if insulation_class not in INSULATION_CLASSES:
        raise ValueError(f"insulation class must be one of {tuple(INSULATION_CLASSES)}, got {insulation_class!r}")
    k0, k1 = _copper_factor(copper_ref_k)
    pc_all, pf_all = np.tile(pc, n_cycles), np.tile(pf, n_cycles)
    n = pc_all.size
    g_ws, g_sa = 1.0 / p.r_ws, 1.0 / p.r_sa
    tw0, ts0 = (p.t_ambient_k, p.t_ambient_k) if t0_k is None else t0_k
    t_w, t_s = np.empty(n + 1), np.empty(n + 1)
    t_w[0], t_s[0] = tw0, ts0

    if method == "implicit":
        cw, cs = p.c_w / dt, p.c_s / dt
        for k in range(n):
            a = pc_all[k] * k0
            b = pc_all[k] * k1
            m11, m12 = cw - b + g_ws, -g_ws
            m21, m22 = -g_ws, cs + g_ws + g_sa
            r1 = cw * t_w[k] + a
            r2 = cs * t_s[k] + pf_all[k] + g_sa * p.t_ambient_k
            det = m11 * m22 - m12 * m21
            t_w[k + 1] = (r1 * m22 - m12 * r2) / det
            t_s[k + 1] = (m11 * r2 - m21 * r1) / det
    else:
        def rhs(t: float, y: np.ndarray) -> list[float]:
            k = min(int(t / dt), n - 1)
            pw = pc_all[k] * (k0 + k1 * y[0])
            q = g_ws * (y[0] - y[1])
            return [(pw - q) / p.c_w, (pf_all[k] + q - g_sa * (y[1] - p.t_ambient_k)) / p.c_s]

        sol = solve_ivp(rhs, (0.0, n * dt), [tw0, ts0], method="RK45", t_eval=np.arange(n + 1) * dt,
                        max_step=dt, rtol=1e-8, atol=1e-6)
        if not sol.success:
            raise ValueError(f"solve_ivp failed: {sol.message}")
        t_w[:], t_s[:] = sol.y

    p_w = pc_all * (k0 + k1 * t_w[1:])
    start = n - pc.size  # last cycle
    t_mean = float(np.mean(t_w[start + 1:]))
    t_max = float(np.max(t_w))
    summary = ThermalSummary(
        t_max=t_max,
        t_mean=t_mean,
        margin=INSULATION_CLASSES[insulation_class] + T_ZERO_C - t_max,
        life_hours=insulation_life(t_w[start + 1:], insulation_class),
        insulation_class=insulation_class,
    )
    return ThermalResult(np.arange(n + 1) * dt, t_w, t_s, p_w, pf_all, method, summary)


def cycle_losses(res: vehicle.DriveResult, emap: losses.EfficiencyMap) -> tuple[np.ndarray, np.ndarray]:
    """Per-step (stator copper, iron + rotor copper) losses of a cycle, read from the efficiency map, W."""
    moving = res.omega > 0
    cu1 = np.where(moving, vehicle.LossTable(emap, "p_cu1")(res.torque, res.omega), 0.0)
    frame = np.where(moving, vehicle.LossTable(emap, "p_cu2")(res.torque, res.omega)
                     + vehicle.LossTable(emap, "p_fe")(res.torque, res.omega), 0.0)
    return cu1, frame


def map_copper_temperature(emap: losses.EfficiencyMap, r1_temperature_k: float | None) -> float | None:
    """Winding temperature at which the map's copper losses were computed, K (None: unknown)."""
    return emap.settings.winding_temperature_k or r1_temperature_k


def fit_cooling_curve(t: ArrayLike, r: ArrayLike, r_ref: float, t_ref_k: float,
                      t_ambient_k: float) -> tuple[float, float]:
    """Winding time constant from timed resistance readings during cooling: (τ in s, T(0) in K).

    T(t) is read from R(t) by the copper law, then ln(T − T_a) = ln(T0 − T_a) − t/τ is fitted.

    Args:
        t: reading times, s.  r: resistances, Ω.  r_ref: resistance at t_ref_k, Ω.
        t_ref_k: reference temperature, K.  t_ambient_k: ambient temperature, K.
    """
    tt, rr = np.asarray(t, dtype=float), np.asarray(r, dtype=float)
    if tt.ndim != 1 or tt.shape != rr.shape or tt.size < 3:
        raise ValueError("t and r must be 1-D arrays of the same length (>= 3)")
    _pos("r_ref", r_ref)
    temp = (rr / r_ref) * (COPPER_T0 + t_ref_k - T_ZERO_C) - COPPER_T0 + T_ZERO_C
    rise = temp - t_ambient_k
    if np.any(rise <= 0):
        raise ValueError("every reading must be above the ambient temperature to fit a cooling curve")
    slope, intercept = np.polyfit(tt, np.log(rise), 1)
    if slope >= 0:
        raise ValueError("the readings do not decay: not a cooling curve")
    return float(-1.0 / slope), float(t_ambient_k + math.exp(intercept))
