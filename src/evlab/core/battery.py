"""Traction battery: pack, open-circuit voltage vs SOC, internal resistance, SOC evolution, limits. No Qt.

Equivalent circuit of the pack: an open-circuit voltage V_oc(SOC) in series with a resistance R
(no RC branch: the 1 s steps of a driving cycle are longer than the fast polarisation; A34).

- Pack of n_s cells in series and n_p strings in parallel: V_oc = n_s·ocv_cell(SOC),
  R = n_s·R_cell/n_p, Q = n_p·C_cell (C), current limits n_p × the cell's.
- Terminal power P (> 0 discharging, < 0 charging) and current: P = V_oc·I − R·I², so
  I = (V_oc − √(V_oc² − 4·R·P)) / (2·R)  (the root that tends to P/V_oc when R → 0).
- Limits, never silently applied: a discharge beyond the current limit or beyond the power ceiling
  V_oc²/(4R), or below the minimum SOC, is reduced and the missing power recorded as « shortfall »;
  a charge beyond the charge-current limit or above the maximum SOC is reduced and the refused
  regenerative power recorded (it goes to the friction brakes).
- SOC: Coulomb counting, SOC_{k+1} = SOC_k − I_k·Δt_k/Q, with the current of the step held constant.
- Energy per step: V_oc·I·Δt (chemical) = P·Δt (terminal) + R·I²·Δt (Joule loss in the pack).

SI units: V, A, Ω, s, W, J; SOC in [0, 1].
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike

from evlab.core import inverter as inverter_mod


@dataclass(frozen=True)
class CellParams:
    """One cell.

    Attributes:
        soc: SOC points of the OCV table, strictly increasing in [0, 1].
        ocv: open-circuit voltage at those points, V (non-decreasing).
        r_int: series resistance, Ω.
        capacity_ah: capacity, A·h.
        i_discharge_max: maximum discharge current, A (> 0).
        i_charge_max: maximum charge current, A (> 0, magnitude).
    """

    soc: tuple[float, ...]
    ocv: tuple[float, ...]
    r_int: float
    capacity_ah: float
    i_discharge_max: float
    i_charge_max: float

    def __post_init__(self) -> None:
        s, v = np.asarray(self.soc, float), np.asarray(self.ocv, float)
        if s.ndim != 1 or s.size < 2 or s.shape != v.shape:
            raise ValueError("soc and ocv must be 1-D tables of the same length (>= 2 points)")
        if not (np.all(np.isfinite(s)) and np.all(np.isfinite(v))):
            raise ValueError("soc and ocv must be finite")
        if s[0] < 0 or s[-1] > 1 or np.any(np.diff(s) <= 0):
            raise ValueError("soc points must be strictly increasing within [0, 1]")
        if np.any(v <= 0) or np.any(np.diff(v) < 0):
            raise ValueError("ocv must be > 0 V and non-decreasing with SOC")
        for name in ("r_int", "capacity_ah", "i_discharge_max", "i_charge_max"):
            x = getattr(self, name)
            if not math.isfinite(x) or x <= 0:
                raise ValueError(f"{name} must be a finite number > 0, got {x!r}")


@dataclass(frozen=True)
class PackParams:
    """Battery pack: cells, arrangement, SOC window.

    Attributes:
        cell: cell parameters.
        n_series: cells in series (integer ≥ 1).
        n_parallel: strings in parallel (integer ≥ 1).
        soc_min, soc_max: usable SOC window, 0 ≤ soc_min < soc_max ≤ 1.
        is_demo: True for assumed values (labelled « démo »).
    """

    cell: CellParams
    n_series: int
    n_parallel: int = 1
    soc_min: float = 0.05
    soc_max: float = 0.95
    is_demo: bool = False

    def __post_init__(self) -> None:
        for name in ("n_series", "n_parallel"):
            x = getattr(self, name)
            if isinstance(x, bool) or not isinstance(x, (int, np.integer)) or x < 1:
                raise ValueError(f"{name} must be an integer >= 1, got {x!r}")
        if not (0.0 <= self.soc_min < self.soc_max <= 1.0):
            raise ValueError(f"need 0 <= soc_min < soc_max <= 1, got {self.soc_min!r}, {self.soc_max!r}")

    @property
    def r(self) -> float:
        """Pack resistance, Ω."""
        return self.n_series * self.cell.r_int / self.n_parallel

    @property
    def capacity_c(self) -> float:
        """Pack charge, C (A·s)."""
        return self.n_parallel * self.cell.capacity_ah * 3600.0

    @property
    def i_discharge_max(self) -> float:
        return self.n_parallel * self.cell.i_discharge_max

    @property
    def i_charge_max(self) -> float:
        return self.n_parallel * self.cell.i_charge_max

    def energy_wh(self) -> float:
        """Nominal energy ∫ V_oc dQ over SOC 0 → 1, Wh."""
        s = np.linspace(0.0, 1.0, 1001)
        return float(np.trapezoid(ocv(self, s), s)) * self.capacity_c / 3600.0


# typical NMC cell shape (démo, A34): not a measured cell
DEMO_CELL_A34 = CellParams(
    soc=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
    ocv=(3.00, 3.45, 3.55, 3.62, 3.68, 3.75, 3.83, 3.92, 4.00, 4.08, 4.20),
    r_int=0.003, capacity_ah=10.0, i_discharge_max=50.0, i_charge_max=20.0,
)


def demo_pack(n_series: int = 168, n_parallel: int = 1, capacity_ah: float = 10.0) -> PackParams:
    """Démo pack (A34): 168 NMC cells in series (≈ 622 V nominal, ≈ 6,2 kWh with 10 Ah)."""
    cell = CellParams(**{**DEMO_CELL_A34.__dict__, "capacity_ah": capacity_ah})
    return PackParams(cell=cell, n_series=n_series, n_parallel=n_parallel, is_demo=True)


def ocv(pack: PackParams, soc: ArrayLike) -> np.ndarray | float:
    """Pack open-circuit voltage at a SOC (linear interpolation of the cell table), V."""
    s = np.asarray(soc, dtype=float)
    if np.any(~np.isfinite(s)) or np.any(s < -1e-12) or np.any(s > 1 + 1e-12):
        raise ValueError("SOC must be within [0, 1]")
    v = pack.n_series * np.interp(s, pack.cell.soc, pack.cell.ocv)
    return float(v) if v.ndim == 0 else v


def current_for_power(v_oc: float, r: float, p: float) -> float:
    """Current (A, > 0 discharging) that delivers terminal power p (W) from (V_oc, R); p ≤ V_oc²/(4R)."""
    disc = v_oc * v_oc - 4.0 * r * p
    if disc < 0:
        raise ValueError(f"power {p:.4g} W above the pack's ceiling V_oc²/(4R) = {v_oc * v_oc / (4 * r):.4g} W")
    return (v_oc - math.sqrt(disc)) / (2.0 * r)


@dataclass(frozen=True)
class BatteryResult:
    """Pack trajectory over the steps of a driving cycle (one value per step, SI).

    soc has one more value than the steps (state at each step boundary).
    """

    dt: np.ndarray  # step durations, s
    soc: np.ndarray  # SOC at the step boundaries (len n + 1)
    current: np.ndarray  # A (> 0 discharging)
    v_oc: np.ndarray  # V
    v_terminal: np.ndarray  # V
    p_requested: np.ndarray  # W, asked at the terminals
    p_terminal: np.ndarray  # W, delivered (> 0) or accepted (< 0) at the terminals
    p_loss: np.ndarray  # W, R·I²
    shortfall: np.ndarray  # W, discharge demand that could not be delivered
    regen_refused: np.ndarray  # W, charging power refused (goes to the friction brakes)
    pack: PackParams

    def energy_wh(self, name: str) -> float:
        """∫ name·dt in Wh for a power series (e.g. "p_terminal", "p_loss", "regen_refused")."""
        return float(np.sum(getattr(self, name) * self.dt)) / 3600.0

    @property
    def chemical_energy_wh(self) -> float:
        """∫ V_oc·I dt, Wh (energy taken from the cells: terminal + losses)."""
        return float(np.sum(self.v_oc * self.current * self.dt)) / 3600.0


def simulate(pack: PackParams, p_terminal: ArrayLike, dt: ArrayLike, soc0: float) -> BatteryResult:
    """Pack trajectory for a terminal power series (W, > 0 discharging) over steps dt (s), from soc0."""
    if not isinstance(pack, PackParams):
        raise ValueError(f"pack must be a PackParams, got {type(pack).__name__}")
    p_req = np.asarray(p_terminal, dtype=float)
    d = np.broadcast_to(np.asarray(dt, dtype=float), p_req.shape).copy()
    if p_req.ndim != 1 or p_req.size == 0 or not np.all(np.isfinite(p_req)):
        raise ValueError("p_terminal must be a non-empty 1-D series of finite powers (W)")
    if not np.all(np.isfinite(d)) or np.any(d <= 0):
        raise ValueError("dt must be finite and > 0 s")
    if not (pack.soc_min <= soc0 <= pack.soc_max):
        raise ValueError(f"soc0 must be within the SOC window [{pack.soc_min}, {pack.soc_max}], got {soc0!r}")
    n, r, q = p_req.size, pack.r, pack.capacity_c
    soc = np.empty(n + 1)
    soc[0] = soc0
    out = {k: np.zeros(n) for k in ("current", "v_oc", "p_terminal", "p_loss", "shortfall", "regen_refused")}
    for k in range(n):
        voc = ocv(pack, min(max(soc[k], 0.0), 1.0))
        p = p_req[k]
        if p >= 0:  # discharge: current limit, power ceiling, SOC floor
            room = max(0.0, (soc[k] - pack.soc_min) * q / d[k])  # current that would empty the window
            i_max = min(pack.i_discharge_max, voc / (2 * r), room)
            ceiling = voc * voc / (4 * r)
            i = current_for_power(voc, r, min(p, ceiling))
            limited = p > ceiling
            if i > i_max:
                i, limited = i_max, True
            delivered = voc * i - r * i * i if limited else p  # within the limits the demand is met exactly
            out["shortfall"][k] = max(0.0, p - delivered) if limited else 0.0
        else:  # charge: current limit, SOC ceiling
            room = max(0.0, (pack.soc_max - soc[k]) * q / d[k])
            i_max = min(pack.i_charge_max, room)
            i = current_for_power(voc, r, p)  # negative
            limited = -i > i_max
            if limited:
                i = -i_max
            delivered = voc * i - r * i * i if limited else p
            out["regen_refused"][k] = max(0.0, delivered - p) if limited else 0.0  # refused magnitude
        out["current"][k], out["v_oc"][k] = i, voc
        out["p_terminal"][k], out["p_loss"][k] = delivered, r * i * i
        soc[k + 1] = soc[k] - i * d[k] / q
    v_t = out["v_oc"] - r * out["current"]
    return BatteryResult(dt=d, soc=soc, current=out["current"], v_oc=out["v_oc"], v_terminal=v_t,
                         p_requested=p_req, p_terminal=out["p_terminal"], p_loss=out["p_loss"],
                         shortfall=out["shortfall"], regen_refused=out["regen_refused"], pack=pack)


@dataclass(frozen=True)
class DcLinkCheck:
    """Battery voltage against the DC voltage the motor needs, per step (V).

    required: smallest DC voltage reaching the phase voltage of the step (inverter.required_dc_voltage).
    margin: terminal voltage − required (negative: the inverter cannot apply the voltage of the map).
    short_steps: number of steps with a negative margin; short_time: their duration, s.
    """

    required: np.ndarray
    margin: np.ndarray
    short_steps: int
    short_time: float
    min_margin: float


def dc_link_check(res: BatteryResult, v_phase: ArrayLike, modulation: str = "svpwm") -> DcLinkCheck:
    """Is the pack's terminal voltage at each step enough for the motor's phase voltage (RMS, V) of that step?

    Steps without current demand (v_phase = 0) need no voltage. The vehicle result is not changed: a negative
    margin means the operating point of the map would need field weakening earlier (or a higher pack voltage).
    """
    v = np.asarray(v_phase, dtype=float)
    if v.shape != res.v_terminal.shape:
        raise ValueError(f"v_phase must have one value per battery step ({res.v_terminal.size}), got {v.shape}")
    req = np.asarray(inverter_mod.required_dc_voltage(v, modulation), dtype=float)
    margin = res.v_terminal - req
    short = (margin < 0) & (v > 0)
    active = v > 0
    return DcLinkCheck(required=req, margin=margin, short_steps=int(short.sum()),
                       short_time=float(np.sum(res.dt[short])),
                       min_margin=float(np.min(margin[active])) if active.any() else math.inf)
