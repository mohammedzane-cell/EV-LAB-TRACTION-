"""Generate the demo bench files of data/ from the core (synthetic, labelled "démo").

    python -m evlab.io.demo_data          # rewrites data/*_demo.csv

The "measurements" are computed with core.circuit from a known circuit, then
each reading gets 2,5 % relative Gaussian noise (fixed seed), so the identified
circuit can be compared with the true one.

Circuit: TD5 Ex 1 (Rf = 230 Ω, Xm = 46 Ω, X = 4 Ω, R'2 = 2 Ω) plus a synthetic
R1 = 0,5 Ω at 75 °C (DC test at 20 °C) and p_mec = 60 W, so that every step
of the chain (DC test, temperature correction, p_mec separation) is exercised.
TD5 Ex 1 itself has R1 = 0, which would make the DC test read 0 V.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

from evlab.core import circuit
from evlab.core.session import MotorParams, td5_ex1

SQRT3 = math.sqrt(3.0)

DEMO_MOTOR = replace(td5_ex1(), r1=0.5, source="TD5 Ex 1 + R1 (démo)", is_demo=True)
P_MECH = 60.0  # W
T_DC_C = 20.0  # °C, DC test
T_HOT_C = 75.0  # °C, winding during the tests
I_DC = 5.0  # A
NOISE = 0.025
SEED = 2026
NO_LOAD_FRACTIONS = (0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1)
LOCKED_FRACTION = 0.25
RATED_SPEED_RPM = 1350.0  # TD5 Ex 1 nameplate
LOAD_SLIPS = tuple(float(g) for g in np.round(np.linspace(0.02, 0.40, 12), 4))

BENCH_FILE = "bench_tests_demo.csv"
LOAD_FILE = "load_points_demo.csv"
BENCH_COLUMNS = ("essai", "U [V]", "I [A]", "P [W]", "f [Hz]", "T [°C]")
LOAD_COLUMNS = ("g [-]", "U [V]", "I [A]", "T [N·m]", "cos_phi [-]", "f [Hz]")


@dataclass(frozen=True)
class DemoSpec:
    """What the demo files are generated from."""

    motor: MotorParams = DEMO_MOTOR
    p_mech: float = P_MECH
    noise: float = NOISE
    seed: int = SEED


def _no_load_slip(m: MotorParams, v: float, p_mech: float) -> float:
    return brentq(lambda g: circuit.operating_point(m, g, v_phase=v).p_mech - p_mech, 1e-12, 0.5)


def _fmt(x: float) -> str:
    return f"{x:.6g}"


def _header(spec: DemoSpec, what: str) -> list[str]:
    m = spec.motor
    return [
        f"# démo: {what}, généré par evlab.io.demo_data depuis le circuit de référence",
        f"# bruit: {spec.noise} (relatif, gaussien), graine: {spec.seed}",
        f"# plaque.tension_simple [V]: {m.v_phase:g}",
        f"# plaque.frequence [Hz]: {m.f_rated:g}",
        f"# plaque.paires_de_poles: {m.pole_pairs}",
        f"# plaque.vitesse_nominale [tr/min]: {RATED_SPEED_RPM:g}",
        f"# reference.source: {m.source}",
        f"# reference.v_phase: {m.v_phase}",
        f"# reference.f_rated: {m.f_rated}",
        f"# reference.pole_pairs: {m.pole_pairs}",
        f"# reference.r1: {m.r1}",
        f"# reference.r_fe: {m.r_fe}",
        f"# reference.x_m: {m.x_m}",
        f"# reference.x_leak: {m.x_leak}",
        f"# reference.r2p: {m.r2p}",
        f"# reference.p_mech: {spec.p_mech}",
        f"# reference.t_hot_c: {T_HOT_C}",
    ]


def demo_csv_texts(spec: DemoSpec = DemoSpec()) -> tuple[str, str]:
    """(bench CSV text, load-points CSV text), deterministic for a given spec."""
    rng = np.random.default_rng(spec.seed)

    def meas(x: float) -> float:
        return x * (1.0 + spec.noise * rng.standard_normal())

    m = spec.motor
    rows = [",".join(BENCH_COLUMNS)]
    r1_dc = m.r1 * (234.5 + T_DC_C) / (234.5 + T_HOT_C)
    rows.append(f"dc,{_fmt(meas(2 * r1_dc * I_DC))},{_fmt(meas(I_DC))},,,{_fmt(T_DC_C)}")
    for k in NO_LOAD_FRACTIONS:
        v = k * m.v_phase
        op = circuit.operating_point(m, _no_load_slip(m, v, spec.p_mech), v_phase=v)
        rows.append(f"vide,{_fmt(meas(SQRT3 * v))},{_fmt(meas(op.i1))},{_fmt(meas(op.p_in))},"
                    f"{_fmt(m.f_rated)},{_fmt(T_HOT_C)}")
    v_cc = LOCKED_FRACTION * m.v_phase
    op = circuit.operating_point(m, 1.0, v_phase=v_cc)
    rows.append(f"rotor_bloque,{_fmt(meas(SQRT3 * v_cc))},{_fmt(meas(op.i1))},{_fmt(meas(op.p_in))},"
                f"{_fmt(m.f_rated)},{_fmt(T_HOT_C)}")
    bench = "\n".join(_header(spec, "essais DC, à vide, rotor bloqué") + rows) + "\n"

    rows = [",".join(LOAD_COLUMNS)]
    for g in LOAD_SLIPS:
        op = circuit.operating_point(m, g)
        t_shaft = op.torque - spec.p_mech / op.omega_mech
        rows.append(f"{_fmt(g)},{_fmt(SQRT3 * m.v_phase)},{_fmt(meas(op.i1))},{_fmt(meas(t_shaft))},"
                    f"{_fmt(meas(op.power_factor))},{_fmt(m.f_rated)}")
    load = "\n".join(_header(spec, "points en charge (tension et glissement exacts)") + rows) + "\n"
    return bench, load


def write_demo_files(directory: Path, spec: DemoSpec = DemoSpec()) -> tuple[Path, Path]:
    """Write the two demo CSV files into `directory`; return their paths."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    bench, load = demo_csv_texts(spec)
    p1, p2 = directory / BENCH_FILE, directory / LOAD_FILE
    p1.write_text(bench, encoding="utf-8")
    p2.write_text(load, encoding="utf-8")
    return p1, p2


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[3] / "data"
    for p in write_demo_files(root):
        print(p)
