"""Generate TP3/TD5-style test records from a known Γ circuit.

The records are what a test bench would measure (line voltage U, line current I,
three-phase power P, DC voltage and current), computed with core.circuit, so the
identified circuit can be compared with the circuit that produced the data.

Case A: TD5 Ex 1 as given (R1 = 0, mechanical losses negligible).
Case B: "démo" variant, TD5 Ex 1 + R1 = 0.5 Ω hot (75 °C), DC test at 20 °C,
        p_mec = 60 W, to exercise every step of the chain. Synthetic values.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np
from scipy.optimize import brentq

from evlab.core import circuit
from evlab.core import identification as ident
from evlab.core.session import MotorParams, td5_ex1

SQRT3 = math.sqrt(3.0)
T_COLD = 293.15  # K, DC test at 20 °C
T_HOT = 348.15  # K, 75 °C during the tests
NO_LOAD_FRACTIONS = (0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1)  # U0 / Un
LOCKED_FRACTION = 0.25  # Ucc / Un (TD5 Ex 2: 87.4 V / 380 V = 0.23)
I_DC = 5.0  # A


@dataclass(frozen=True)
class Case:
    name: str
    motor: MotorParams  # true circuit, R1 at T_HOT
    p_mech: float  # true mechanical losses, W
    p_mech_given: float | None  # what the chain is told (None = separate by the U² fit)


CASE_A = Case("TD5 Ex 1", td5_ex1(), p_mech=0.0, p_mech_given=0.0)
CASE_B = Case(
    "TD5 Ex 1 + R1, p_mec (démo)",
    replace(td5_ex1(), r1=0.5, source="TD5 Ex 1 + R1 démo", is_demo=True),
    p_mech=60.0,
    p_mech_given=None,
)


def _no_load_slip(m: MotorParams, v: float, p_mech: float) -> float:
    """Slip at which the internal mechanical power equals the mechanical losses."""
    if p_mech == 0:
        return 0.0
    return brentq(lambda g: circuit.operating_point(m, g, v_phase=v).p_mech - p_mech, 1e-12, 0.5)


def make_records(case: Case, noise: float = 0.0, seed: int = 0) -> ident.TestRecords:
    """Bench records for `case`; each measured value gets relative Gaussian noise `noise`."""
    rng = np.random.default_rng(seed)

    def meas(x: float) -> float:
        return x * (1.0 + noise * rng.standard_normal()) if noise else x

    m = case.motor
    dc = None
    if m.r1 > 0:
        r1_cold = m.r1 * (234.5 + T_COLD - 273.15) / (234.5 + T_HOT - 273.15)
        dc = ident.DcTest(v_dc=meas(2 * r1_cold * I_DC), i_dc=meas(I_DC), temperature_k=T_COLD)

    no_load = []
    for k in NO_LOAD_FRACTIONS:
        v = k * m.v_phase
        op = circuit.operating_point(m, _no_load_slip(m, v, case.p_mech), v_phase=v)
        no_load.append(ident.NoLoadTest.from_line(
            u_line=meas(SQRT3 * v), i_line=meas(op.i1), p_total=meas(op.p_in), f=m.f_rated))

    v_cc = LOCKED_FRACTION * m.v_phase
    op = circuit.operating_point(m, 1.0, v_phase=v_cc)
    locked = ident.LockedRotorTest.from_line(
        u_line=meas(SQRT3 * v_cc), i_line=meas(op.i1), p_total=meas(op.p_in), f=m.f_rated)

    return ident.TestRecords(
        dc=dc,
        t_hot_k=T_HOT if dc else None,
        no_load=tuple(no_load),
        locked=locked,
        pole_pairs=m.pole_pairs,
        v_rated=m.v_phase,
        f_rated=m.f_rated,
        p_mech=case.p_mech_given,
    )


PARAMS = ("r1", "r_fe", "x_m", "x_leak", "r2p")


def error_table(ref: MotorParams, got: MotorParams) -> list[tuple[str, float, float, float | None]]:
    """Rows (name, reference, identified, error %) for the circuit and its breakdown point."""
    g_r, t_r = circuit.breakdown(ref)
    g_g, t_g = circuit.breakdown(got)
    rows = [(n, getattr(ref, n), getattr(got, n)) for n in PARAMS]
    rows += [("g_c", g_r, g_g), ("T_max", t_r, t_g)]
    return [(n, r, g, None if r == 0 else 100.0 * (g - r) / r) for n, r, g in rows]


def format_table(title: str, rows) -> str:
    lines = [title, f"{'param':<7}{'reference':>12}{'identified':>12}{'error %':>10}"]
    for n, r, g, e in rows:
        es = "—" if e is None else f"{e:+.3f}"
        lines.append(f"{n:<7}{r:>12.5g}{g:>12.5g}{es:>10}")
    return "\n".join(lines)
