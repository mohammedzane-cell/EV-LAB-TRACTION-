# EV-Traction Lab

PROJECT ME3 — ENP Alger, Machines électriques. Laboratoire virtuel d'une chaîne
de traction de véhicule électrique à moteur asynchrone.

One motor, one chain: the Γ circuit identified in tab 1 (default TD5 Ex 1) feeds
every other module. See `CLAUDE.md` for the full specification and
`docs/roadmap.md` for the stages.

## Install

Python 3.11 or 3.12 (3.13 also works). Exact versions are pinned in `requirements.txt`.

```bash
pip install -r requirements.txt
```

```bash
pip install -e ".[dev]"
```

On a headless Linux machine Qt also needs system libraries (Debian/Ubuntu):

```bash
sudo apt-get install libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3
```

## Run

```bash
python -m evlab
```

The `evlab` command does the same. The window has seven tabs (1 · Identification …
7 · Optimisation) and a status bar showing which motor the whole chain uses.

## Test

```bash
pytest
```

GUI tests run headless (`QT_QPA_PLATFORM=offscreen`, set in `tests/conftest.py`).

## Layout

```
src/evlab/core/   pure physics (no Qt, no I/O)
src/evlab/io/     loaders and exports
src/evlab/gui/    PySide6 tabs
tests/            pytest
docs/             roadmap, assumptions, data notes (course PDFs local only)
data/             input files (*_demo.csv for demo data)
```

## Tab 1 · Identification (`gui/tab_identification.py`)

Left panel: **Machine** (V, f, p, R1 and its temperature, layout TP3 / Bornes;
rated speed read from the file's nameplate), **Essais (CSV)** (bench tests and
load points, each with a status line and a preview; "Charger la démo" loads the
two `data/*_demo.csv` files), **Méthode** (Formules classiques, Optimisation,
Comparer les deux), then **Identifier** (and Exporter PDF, disabled until
stage 9). Right: torque–slip and current–slip plots (model curves from the
core, measured points, breakdown point; chip "points synthétiques (démo)"), and
the table Référence / Formules classiques / Optimisation with error % and the
95 % interval of the fit as tooltip.

**Identifier** runs `core.identification.compare_methods` in a `QThreadPool`
worker; progress and any identifiability warning appear in the status bar. The
identified motor is published to the `Session`, so tabs 2 to 7 use it
(classical result, or the fit when there is one). Layout: `docs/mockup_tab1.png`.

## Tab 2 · Enveloppe (`core/drive.py`, `gui/tab_envelope.py`)

`drive.envelope(motor, DriveSettings(i_max, boost, margin, f_max))` computes the
torque–speed envelope of the Session motor under the V/f law V = V0 + (Vn − V0)·f/fn
up to fn, then V = Vn (field weakening). Every reactance scales with f. At each
speed the available torque is min(current-limited torque, margin·breakdown
torque, the speed's own torque peak), found over the rotor frequency by a
vectorised golden-section search and bisections (A17).
The three zones (constant torque, constant power, breakdown-limited) are read
from the curve: the log–log slope d ln T/d ln Ω and the binding limit (A18).

The tab shows the drive inputs, four KPI tiles (base speed, end of constant
power, P max, torque at max speed) and the torque and power curves with the
zones shaded. It recomputes in a worker whenever tab 1 publishes a motor.

## Tab 3 · Rendement (`core/losses.py`, `gui/tab_efficiency.py`)

`losses.efficiency_map(motor, torque, speed, drive_settings, LossSettings(...))`
solves, for every (shaft torque, speed) grid point, the operating point under
the V/f law of tab 2 (vectorised golden-section + bisection on the rotor
frequency, no loop over points; 160 × 120 in about 0,3 s). Loss terms: copper
3·R1(T)·I1² + 3·R'2·I'2², iron by Steinmetz (β, A19), mechanical a·Ω + b·Ω²
from the p_mec identified in tab 1 (A20), inverter P_0 + k·P (démo, A21).
It returns η and every term; NaN outside the envelope.

The tab draws the contour map with % labels, the shaft-torque envelope, the
best-efficiency point, the cycle points (from stage 5) and exports a PNG. It
uses the drive settings of tab 2 and recomputes when shown after a change.

## Tab 4 · Véhicule & WLTC (`core/vehicle.py`, `io/cycles.py`, `gui/tab_vehicle.py`)

The vehicle fits the motor. `vehicle.size_vehicle` takes the motor's rated power
(maximum shaft power of the envelope) and the vehicle mass, gives the
power-to-mass ratio and the WLTC class (≤ 22 W/kg → 1, ≤ 34 → 2, else 3), and
proposes the gear ratio G that keeps the whole cycle inside the envelope (A23).
`vehicle.simulate` drives the cycle second by second: road load
F = m·a + ½ρCxS·v² + Crr·m·g·cosθ + m·g·sinθ, motor torque F·r/(G·ηg) in
traction and F·r·ηg/G in regenerative braking, ωm = G·v/r, battery power =
shaft power + motor/inverter losses interpolated from the tab 3 map +
auxiliaries. The summary gives distance, energy, Wh/km, regenerated % and the
number of points outside the envelope; the energy balance closes to 1e-6.

Cycles are read by `io.cycles.load_cycle` (columns `t [s]`, `v [km/h]`,
resampled to 1 s). Put the official WLTC files in `data/` as
`wltc_class1.csv` and `wltc_class3.csv`; until then the tab uses the synthetic
`cycle_demo.csv` (démo). The demo vehicle is a light quadricycle (A22).

The tab shows the vehicle parameters, the WLTC class with its W/kg, the
regeneration checkbox, KPI tiles, the speed and battery-power plots and a red
warning when any point exceeds the envelope; the cycle points also appear on
the tab 3 map.

## Tab 5 · Thermique (`core/thermal.py`, `gui/tab_thermal.py`)

Two-node network: winding (C_w) —R_ws— iron/frame (C_s) —R_sa— ambient. It is
fed by the per-second losses of the tab 4 cycle read from the tab 3 map: stator
copper to the winding (recomputed every step with R1(T), 234,5 rule), iron and
rotor copper to the frame. Integrated over N cycles back to back by implicit
Euler (exact 2×2 solve per step) or `solve_ivp` RK45. Insulation life uses the
10 K rule from the mean winding temperature, as an order of magnitude (A28).
The network values are démo (A26); `fit_cooling_curve` fits the winding time
constant to timed resistance readings when TP3 provides them.

The tab shows the parameters (with the two time constants), the insulation
class, the cycle count, T(t) with the class line, and KPI tiles (T max,
T mean, margin, life).

## Tab 6 · Bobinage (`core/winding.py`, `gui/tab_winding.py`)

Three-phase, double-layer, integral-slot lap winding from Z, 2p and the coil
pitch y (an integer number of slots, 1 ≤ y ≤ τ; q = Z/(2p·m) must be an
integer, and a non-integer pitch such as "5/6" of τ = 9 is refused with the two
nearest integer pitches). Distribution, pitch and winding factors for any
harmonic, the slot table (top belts A+ C− B+ A− C+ B−, bottom = top shifted by y
and reversed), the stepped phase MMF and its FFT against kw_ν/ν, the rotating
field of balanced currents over one electrical period, and E = 4,44·f·N·kw1·Φ
(TD2 Ex 1 reproduced: 8 poles, 1023 V per phase, 1772 V line).

The tab shows the slot strip (labels and colours), the kw table for y = τ and
the chosen y, the MMF spectrum, the EMF, and the animated air-gap MMF with its
fundamental for y = τ and y side by side (play/pause, speed slider).

## Tab 7 · Optimisation (`core/optimise.py`, `gui/tab_optimisation.py`)

Design variables: gear ratio G, V/f boost, field-weakening margin and a
rewinding factor k_N (turns × k_N at the same copper area: every impedance
× k_N², rated voltage fixed). Each evaluation chains only the tested models
(envelope, 40 × 30 loss map, cycle simulation, 0–50 km/h, thermal model) and
returns Wh/km, the 0–50 km/h time and the constraints: every cycle point inside
the envelope, winding T max ≤ class limit − 20 K, stator current ≤ inverter limit.
`scipy.optimize.differential_evolution` (seeded, process pool) with an
ε-constraint sweep traces the Pareto front; every evaluation is logged (A31).

The tab takes the bounds of each variable (min = max fixes it) and the budget,
runs in a worker with progress and cancel, plots the front with the baseline
and every admissible evaluation, and shows baseline vs the selected design with
the gain in % per KPI. "Charger ce design" loads the rewound motor, the V/f
law and the gear ratio into every tab.

## Reports (`io/report.py`, `io/excel.py`, `io/snapshot.py`, `io/figures.py`)

Menu **Fichier → Exporter PDF… / Exporter Excel…** (also the "Exporter PDF"
button of tab 1) asks for the group name and a file, then writes, in a worker:

- an A4 French PDF (reportlab), 2–3 pages: title block (group, date),
  1 identification table, 2 envelope and efficiency figures, 3 cycle figure and
  KPI table, 4 thermal summary, 5 winding factors, 6 optimisation (baseline vs
  optimum and Pareto plot), an assumptions box built from the settings in use,
  and a footer on every page listing what is démo. Figures are drawn with
  matplotlib from the core results; fonts are DejaVu Sans from matplotlib.
- an Excel workbook (openpyxl): one sheet per module with the raw SI arrays and
  the units in the headers (16 significant digits).

Both come from one `Snapshot` of the session; results not computed yet (map,
cycle, thermal) are computed with the core for the export, the optimisation is
reported as "non calculée" until it has been run.

## Core: Γ equivalent circuit (`core/circuit.py`, `core/session.py`)

`MotorParams` is the single per-phase Γ circuit shared through a `Session`
(defaults to TD5 Ex 1: V = 230 V, f = 50 Hz, p = 2, Rf = 230 Ω, Xm = 46 Ω,
X = 4 Ω, R'2 = 2 Ω, R1 = 0). Its `layout` selects the topology:

- `"tp3"` (default, TP3 Figure 1): V → R1 (carries I1) → Rf ∥ jXm → jX + R'2/g
- `"terminals"`: Rf ∥ jXm at the terminals, R1 in series with jX + R'2/g

The two are identical when R1 = 0. All functions are vectorised over the slip g,
handle g = 0 (no-load) and g < 0 (generator) without division, and accept an
optional V/f supply override (`v_phase`, `f`):

- `impedance`, `stator_current`, `rotor_current`, `power_factor`
- `torque` — T = (3p/ω)·(R'2/g)·I'2²
- `mechanical_speed`, `slip_from_speed`
- `input_power`, `efficiency` (mechanical losses not included, see A10)
- `breakdown(m)` → (g_c, T_max): numeric by default, `method="closed"` for the
  Thévenin closed form; TD5: g_c = 0,5, T_max = 126,3 N·m
- `thevenin`, `magnetising_impedance`
- `operating_point` — every current and power; P_in = P_cu1 + P_fe + P_cu2 + P_mec
- `copper_resistance` — R(T) = R20·(234,5 + T)/254,5

## Core: identification (`core/identification.py`)

Classical TP3 / TD5 chain, `run_identification(records, method=...)`:

1. DC test → R1 cold = U_dc/(2·I_dc), then R1 hot = R1 cold·(234,5 + T_hot)/(234,5 + T_cold)
2. no-load series → P0' = P0 − 3·R1·I0² against U0², intercept at U = 0 = p_mec
3. rated no-load point → Rf = 3·V0²/P_fe, Xm = 3·V0²/Q0
4. locked-rotor test → R'2 = Pcc/(3·Icc²) − R1, X = sqrt(Zcc² − Rcc²)

`method="classical"` uses the course formulas; `method="exact"` (default) inverts
the circuit layout. Records (`DcTest`, `NoLoadTest`, `LockedRotorTest`, built with
`from_line(U, I, P, f)`) are validated. The report keeps each intermediate value
(R1 cold/hot, p_mec, P_fe, cos φ0, cos φcc).

`fit_load_points(points, start)` fits (Xm, X, R'2) to load-test points
(g, I, T, cos φ) with `scipy.optimize.least_squares`: residuals normalised per
reading (per quantity as an option), positive bounds, `soft_l1` loss, a 10-start multistart, 95 % confidence
intervals from the Jacobian and the correlation matrix (`IdentifiabilityWarning`
when |ρ| > 0,95). R1 and Rf stay fixed (DC and no-load tests): load points barely
depend on Rf (A13).

On noise-free TD5 Ex 1 records the exact method returns the circuit exactly. The
classical locked-rotor formula gives R'2 −13,1 % and X −7,7 %: that is the error of
the formula itself, which neglects the magnetising branch (A9).

## Data files (`io/loaders.py`, `io/demo_data.py`)

`load_bench_tests(path)` reads the DC, no-load and locked-rotor tests;
`load_load_points(path)` reads load-test points. Columns are written
`name [unit]`; a missing column, a wrong unit, an empty file or a bad value
raises `LoaderError` with a French message. Files named `*_demo.csv` are demo
data. Regenerate the demo files with:

```bash
python -m evlab.io.demo_data
```

Formats and provenance: `docs/data_notes.md`.

Modelling assumptions are listed in `docs/assumptions.md`.
