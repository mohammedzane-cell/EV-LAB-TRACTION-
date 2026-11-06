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
up to fn, then V = Vn (field weakening). At each stator frequency every reactance
scales with f, and the available torque is min(current-limited torque,
margin·breakdown torque), solved on the stable branch by vectorised bisection.
The three zones (constant torque, constant power, breakdown-limited) are read
from the curve: the log–log slope d ln T/d ln Ω and the binding limit (A18).

The tab shows the drive inputs, four KPI tiles (base speed, end of constant
power, P max, torque at max speed) and the torque and power curves with the
zones shaded. It recomputes in a worker whenever tab 1 publishes a motor.

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
