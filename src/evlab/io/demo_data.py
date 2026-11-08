"""Generate the demo files of data/ from the core (synthetic, labelled "démo").

    python -m evlab.io.demo_data          # rewrites data/*_demo.csv

The "measurements" are computed with core.circuit from a known circuit, then
each reading gets 2,5 % relative Gaussian noise (fixed seed), so the identified
circuit can be compared with the true one.

Circuit: TD5 Ex 1 (Rf = 230 Ω, Xm = 46 Ω, X = 4 Ω, R'2 = 2 Ω) plus a synthetic
R1 = 0,5 Ω at 75 °C (DC test at 20 °C) and p_mec = 60 W, so that every step
of the chain (DC test, temperature correction, p_mec separation) is exercised.
TD5 Ex 1 itself has R1 = 0, which would make the DC test read 0 V.

data/cycle_demo.csv is a synthetic urban cycle (not a WLTC cycle), used until
the official WLTC files are placed in data/ by the user.

    python -m evlab.io.demo_data --tests  # rewrites data/tests/ (test datasets)

data/tests/ holds synthetic test datasets made by the same functions (write_dataset_files):
three motors (bench tests + load points), three smooth drive cycles (not WLTC) and
four deliberately bad files for the loaders' error messages. Every generated file
starts with a "# démo: …" line, which the loaders read as the démo label.
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

CYCLE_FILE = "cycle_demo.csv"
# synthetic urban cycle (not WLTC): (cruise speed km/h, accel m/s², cruise s, decel m/s², idle s after)
# (cruise speed km/h, cruise s, decel m/s², idle s after); the acceleration falls with
# speed as in real cycles: (upper speed km/h, accel m/s²) bands below
CYCLE_TRIPS = ((30, 20, 0.8, 15), (45, 40, 0.9, 20), (20, 15, 0.8, 10),
               (55, 60, 1.0, 20), (60, 30, 0.9, 25), (35, 25, 0.8, 0))
CYCLE_ACCEL_BANDS = ((20.0, 0.9), (40.0, 0.6), (1e9, 0.35))
CYCLE_IDLE_START = 10.0  # s
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
    load_slips: tuple[float, ...] = LOAD_SLIPS
    rated_speed_rpm: float = RATED_SPEED_RPM


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
        f"# plaque.vitesse_nominale [tr/min]: {spec.rated_speed_rpm:g}",
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
    for g in spec.load_slips:
        op = circuit.operating_point(m, g)
        t_shaft = op.torque - spec.p_mech / op.omega_mech
        rows.append(f"{_fmt(g)},{_fmt(SQRT3 * m.v_phase)},{_fmt(meas(op.i1))},{_fmt(meas(t_shaft))},"
                    f"{_fmt(meas(op.power_factor))},{_fmt(m.f_rated)}")
    load = "\n".join(_header(spec, "points en charge (tension et glissement exacts)") + rows) + "\n"
    return bench, load


def cycle_demo_text() -> str:
    """Synthetic urban cycle sampled at 1 s (micro-trips, acceleration falling with speed), labelled démo."""
    # breakpoints (t, v) of the piecewise-linear speed profile
    pts = [(0.0, 0.0), (CYCLE_IDLE_START, 0.0)]
    t = CYCLE_IDLE_START
    for v_kmh, cruise, dec, idle in CYCLE_TRIPS:
        v = v_kmh / 3.6
        v_now = 0.0
        for v_band, acc in CYCLE_ACCEL_BANDS:
            v_next = min(v, v_band / 3.6)
            if v_next > v_now:
                t += (v_next - v_now) / acc
                pts.append((t, v_next))
                v_now = v_next
        t += cruise
        pts.append((t, v))
        t += v / dec
        pts.append((t, 0.0))
        t += idle
        pts.append((t, 0.0))
    tb, vb = np.array(pts).T
    ts = np.arange(0.0, math.floor(tb[-1]) + 1.0)
    vs = np.interp(ts, tb, vb)
    vs[-1] = 0.0
    rows = ["t [s],v [km/h]"] + [f"{t_:g},{v_ * 3.6:.4f}" for t_, v_ in zip(ts, vs)]
    head = ["# démo: cycle urbain synthétique (pas un cycle WLTC), généré par evlab.io.demo_data",
            "# micro-trajets, accélération 0,9 / 0,6 / 0,35 m/s² sous 20 / 40 / au-delà km/h, v_max 60 km/h"]
    return "\n".join(head + rows) + "\n"


def write_demo_files(directory: Path, spec: DemoSpec = DemoSpec()) -> tuple[Path, Path]:
    """Write the two demo CSV files into `directory`; return their paths."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    bench, load = demo_csv_texts(spec)
    p1, p2 = directory / BENCH_FILE, directory / LOAD_FILE
    p1.write_text(bench, encoding="utf-8")
    p2.write_text(load, encoding="utf-8")
    (directory / CYCLE_FILE).write_text(cycle_demo_text(), encoding="utf-8")
    return p1, p2



# --- test datasets (data/tests/) -------------------------------------------------------

TESTS_DIR = "tests"
TEST_LOAD_SLIPS = tuple(float(g) for g in np.round(np.linspace(0.01, 0.08, 10), 4))
TEST_P_MECH_FRACTION = 0.01  # p_mec = 1 % of the rated power (synthetic, data/tests/README.md)
# name: (V, f, p, R1, Rf, Xm, X, R'2, rated shaft power W); R1 is the hot value (75 °C)
TEST_MOTOR_VALUES = {
    "petit_1.5kW": (230.0, 50.0, 2, 4.0, 1000.0, 115.0, 10.0, 3.6, 1500.0),
    "moyen_4kW": (230.0, 50.0, 2, 1.6, 900.0, 75.0, 6.5, 1.4, 4000.0),
    "grand_7.5kW": (230.0, 50.0, 2, 0.75, 600.0, 45.0, 4.2, 0.7, 7500.0),
}
TEST_SEED = 2101  # motor k uses TEST_SEED + k
# smooth cycles (not WLTC): trips (cruise km/h, cruise s, idle s after); peak acceleration
# and deceleration a (m/s²) of the raised-cosine speed ramps; idle at the start (s)
TEST_CYCLES = {
    "cycle_urbain": ("cycle urbain synthétique", 1.0, 12.0,
                     ((30, 25, 20), (45, 40, 25), (25, 20, 15), (50, 60, 30), (35, 30, 20),
                      (50, 45, 25), (30, 25, 20), (45, 50, 20), (25, 20, 15), (40, 35, 15))),
    "cycle_route": ("cycle routier synthétique", 0.8, 15.0,
                    ((60, 120, 30), (80, 240, 40), (70, 180, 30), (80, 150, 20))),
    "cycle_mixte": ("cycle mixte synthétique (urbain puis route)", 1.1, 10.0,
                    ((30, 25, 20), (45, 40, 20), (35, 30, 20), (50, 50, 25), (70, 150, 30),
                     (80, 180, 30), (60, 90, 25), (40, 40, 20), (30, 25, 10))),
}
BAD_FILES = ("bench_tests_bad_negative.csv", "load_points_bad_slip.csv", "cycle_bad_time.csv",
             "cycle_bad_header.csv")


def dataset_motor(name: str) -> tuple[MotorParams, float]:
    """(reference circuit, rated shaft power W) of a test motor of data/tests/."""
    v, f, p, r1, r_fe, x_m, x, r2p, p_n = TEST_MOTOR_VALUES[name]
    m = MotorParams(v_phase=v, f_rated=f, pole_pairs=p, r1=r1, r2p=r2p, x_leak=x, x_m=x_m, r_fe=r_fe,
                    source=f"{name} (synthétique, démo)", is_demo=True, p_mech=TEST_P_MECH_FRACTION * p_n)
    return m, p_n


def rated_speed_rpm(m: MotorParams, p_rated: float) -> float:
    """Speed (tr/min) at which the circuit gives the rated shaft power, below breakdown."""
    g_c = float(circuit.breakdown_slip(m))

    def shaft(g: float) -> float:
        op = circuit.operating_point(m, g)
        return op.p_mech - m.p_mech - p_rated

    g = brentq(shaft, 1e-6, g_c)
    return (1.0 - g) * 60.0 * m.f_rated / m.pole_pairs


def dataset_spec(name: str) -> DemoSpec:
    """DemoSpec of a test motor: 2,5 % noise, seed TEST_SEED + k, 10 load points g = 0,01…0,08."""
    m, p_n = dataset_motor(name)
    k = list(TEST_MOTOR_VALUES).index(name)
    return DemoSpec(motor=m, p_mech=m.p_mech, noise=NOISE, seed=TEST_SEED + k, load_slips=TEST_LOAD_SLIPS,
                    rated_speed_rpm=round(rated_speed_rpm(m, p_n)))


def smooth_cycle_text(title: str, a_peak: float, idle_start: float,
                      trips: tuple[tuple[float, float, float], ...]) -> str:
    """Cycle at 1 s with raised-cosine ramps v(τ) = v·(1 − cos(πτ/T))/2, T = πv/(2a): |dv/dt| ≤ a."""
    pieces = [(0.0, idle_start, 0.0, 0.0)]  # (t0, t1, v0, v1): ramp if v0 != v1, else constant
    t = idle_start
    for v_kmh, cruise, idle in trips:
        v = v_kmh / 3.6
        ramp = math.pi * v / (2.0 * a_peak)
        pieces += [(t, t + ramp, 0.0, v), (t + ramp, t + ramp + cruise, v, v)]
        t += ramp + cruise
        pieces += [(t, t + ramp, v, 0.0), (t + ramp, t + ramp + idle, 0.0, 0.0)]
        t += ramp + idle
    ts = np.arange(0.0, math.ceil(t) + 1.0)
    vs = np.zeros_like(ts)
    for t0, t1, v0, v1 in pieces:
        on = (ts >= t0) & (ts <= t1)
        x = (ts[on] - t0) / (t1 - t0) if t1 > t0 else 0.0
        vs[on] = v0 + (v1 - v0) * 0.5 * (1.0 - np.cos(math.pi * x))
    rows = ["t [s],v [km/h]"] + [f"{t_:g},{v_ * 3.6:.4f}" for t_, v_ in zip(ts, vs)]
    head = [f"# démo: {title}, PAS un cycle WLTC, généré par evlab.io.demo_data",
            f"# rampes en cosinus surélevé, accélération max {a_peak:g} m/s² (≤ 1,2), "
            f"v_max {max(v for v, _, _ in trips):g} km/h"]
    return "\n".join(head + rows) + "\n"


def _bad_files(petit_bench: str, petit_load: str, urbain: str) -> dict[str, str]:
    """The four bad files, each with one deliberate error (data/tests/README.md)."""
    out = {}
    lines = petit_bench.splitlines()
    k = next(i for i, ln in enumerate(lines) if ln.startswith("vide,"))
    cells = lines[k].split(",")
    cells[3] = "-" + cells[3]  # negative three-phase power on the first no-load point
    lines[k] = ",".join(cells)
    lines[0] = "# démo: FICHIER ERRONÉ (puissance négative sur le 1er essai à vide), pour tester les messages"
    out["bench_tests_bad_negative.csv"] = "\n".join(lines) + "\n"
    lines = petit_load.splitlines()
    k = [i for i, ln in enumerate(lines) if ln[:1].isdigit()][4]
    cells = lines[k].split(",")
    cells[0] = "1.2"  # slip 1,2 (plugging) in a load test
    lines[k] = ",".join(cells)
    lines[0] = "# démo: FICHIER ERRONÉ (un point avec g = 1,2), pour tester les messages"
    out["load_points_bad_slip.csv"] = "\n".join(lines) + "\n"
    lines = urbain.splitlines()
    k = next(i for i, ln in enumerate(lines) if ln.startswith("100,"))
    lines[k] = "95" + lines[k][3:]  # time goes back from 99 s to 95 s
    lines[0] = "# démo: FICHIER ERRONÉ (le temps revient de 99 s à 95 s), pour tester les messages"
    out["cycle_bad_time.csv"] = "\n".join(lines) + "\n"
    lines = urbain.splitlines()
    k = next(i for i, ln in enumerate(lines) if ln.startswith("t [s]"))
    lines[k] = "temps [s],vitesse [km/h]"
    lines[0] = "# démo: FICHIER ERRONÉ (en-têtes « temps », « vitesse » au lieu de « t », « v »)"
    out["cycle_bad_header.csv"] = "\n".join(lines) + "\n"
    return out


def dataset_texts() -> dict[str, str]:
    """Every file of data/tests/ (name → text), deterministic."""
    out = {}
    for name in TEST_MOTOR_VALUES:
        bench, load = demo_csv_texts(dataset_spec(name))
        out[f"bench_tests_{name}.csv"] = bench
        out[f"load_points_{name}.csv"] = load
    for name, args in TEST_CYCLES.items():
        out[f"{name}.csv"] = smooth_cycle_text(*args)
    out.update(_bad_files(out["bench_tests_petit_1.5kW.csv"], out["load_points_petit_1.5kW.csv"],
                          out["cycle_urbain.csv"]))
    return out


def write_dataset_files(directory: Path) -> list[Path]:
    """Write the test datasets into `directory` (data/tests/); return their paths."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, text in dataset_texts().items():
        (directory / name).write_text(text, encoding="utf-8")
        paths.append(directory / name)
    return paths


if __name__ == "__main__":
    import sys

    from evlab.io.paths import data_dir

    root = data_dir()
    if "--tests" in sys.argv[1:]:
        for p in write_dataset_files(root / TESTS_DIR):
            print(p)
    else:
        for p in write_demo_files(root):
            print(p)
        print(root / CYCLE_FILE)
