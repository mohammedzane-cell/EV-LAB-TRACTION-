# EV-Traction Lab

Mini-projet ME3 — ENP Alger, Machines électriques. Laboratoire virtuel d'une chaîne
de traction de véhicule électrique à moteur asynchrone.

## Purpose

A desktop virtual lab (PySide6, French interface) that follows **one motor through
one chain**: the Γ equivalent circuit identified in tab 1 from bench tests
(default TD5 Ex 1, or the TP3-style démo files) is the motor that every other tab
uses. Its circuit gives the V/f + field-weakening envelope, the efficiency map, the
energy of a driving cycle, the winding temperature, and the design optimisation.
Tab 6 covers the stator winding (factors, MMF, rotating field, optional FEM). Tab 8 is a
French course that states and explains every law the app uses, tab by tab, in the notation
of Pr Boughrara's course, with examples computed by the app itself (« ? » on each tab, F1).
A PDF report and an Excel workbook export the whole session, and the course exports to
PDF. Specification: `CLAUDE.md`; user guide (French): `docs/user_guide.md`; 5½-minute
demo: `docs/demo_script.md`.

## Install

From source: Python 3.12 or later (tested on 3.12 and 3.13), versions pinned in
`requirements.txt`. Python 3.11 is not supported: the pinned PySide6 6.12.0 aborts
on it (a reference-count error inside PySide6, reproduced without any project code).

```bash
pip install -r requirements.txt
```

```bash
pip install -e ".[dev]"
```

Use the editable install (`-e`): the app reads `data/` next to the source tree
(or the folder named by the `EVLAB_DATA` environment variable). On a headless
Linux machine Qt also needs (Debian/Ubuntu):

```bash
sudo apt-get install libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3
```

Windows build (no Python needed on the target PC): copy the `dist\EVLab` folder and
run `EVLab.exe`; see **Build** below. The optional FEM part needs pyfemm and FEMM 4.2;
without them tab 6 replays the pre-computed FEM runs.

## Run

```bash
python -m evlab
```

The `evlab` command (or `EVLab.exe`) does the same. Start-up self-test, without
using the window (8 tabs, data folder, test datasets, FEM cache, demo files, envelope,
cycle, two-process optimisation, PDF and Excel export, course tab, course PDF: 12 checks;
log in `<dossier>/smoke.log`, exit code 0 when all pass):

```bash
python -m evlab --smoke build/smoke
```

Look: `src/evlab/palette.py` (no Qt) holds one palette per theme (light, dark);
`gui/theme.py` applies it to the Qt stylesheet `gui/style.qss` and the pyqtgraph plots,
and `io/figures.py` uses it for the PDF figures (always the light one); every text
colour pair is tested for a contrast ≥ 4,5:1.
*Affichage → Thème clair / sombre* switches it, remembered with QSettings.

Screen sizes: the window works down to 1100 × 650 logical px and opens maximised on a
screen smaller than 1440 × 900 (1366 × 768, or 1920 × 1080 at 150 %). Left panels
scroll, plots expand with a minimum height, KPI labels wrap, and every plot legend sits
above its plot, never over a curve. `gui/layout_check.py` reports overlaps, widgets
outside their parent and cut text; the GUI tests run it on every tab at 1100 × 650,
1280 × 720, 1366 × 768 and 1920 × 1080 (`capture_screenshots.py --size WxH` for images).

## Test

```bash
pytest
```

```bash
pytest --cov=evlab --cov-report=term
```

GUI tests run headless (`QT_QPA_PLATFORM=offscreen`, set in `tests/conftest.py`).
The FEM tests run only where FEMM is installed; three WLTC tests skip until the
official files are in `data/`.

Screenshots: `python tools/capture_screenshots.py` redoes every `docs/images/*.png` by driving the
app along `docs/demo_script.md` (headless, about 1 min) and prints the numbers the script quotes.
Tab 8 is captured in both themes (`08_cours.png`, `08_cours_sombre.png`); the tool points
QSettings to a temporary folder, so the theme you chose is left as it is.

## Build (PyInstaller, one folder)

On Windows, from the repository root (creates a clean `.venv-build`, builds, runs
the self-test of the result):

```bat
packaging\build_windows.bat
```

Any platform, in an environment with `requirements.txt` installed (it pins the
optional dev tools, PyInstaller included; or `pip install -e ".[dev]"`):

```bash
pyinstaller --noconfirm --clean packaging/EVLab.spec
```

Result: `dist/EVLab/EVLab(.exe)` with `_internal/` (Python, Qt, numpy, scipy …) and
`data/` next to the executable (démo files, FEM cache; put the official WLTC files
there). PyInstaller does not cross-compile: build the Windows version on Windows.
The course pages (`src/evlab/docs/cours/*.md`) are bundled as package data and read with
`importlib.resources`; the course is shown by a `QTextBrowser`, so the spec excludes
QtWebEngine and the other Qt web modules (about 200 MB).

## Module overview and key equations

| Module | Tab | Key equations / method |
|---|---|---|
| `core/circuit.py`, `core/session.py` | all | Γ circuit (TP3 layout): V → R1 → (Rf ∥ jXm) → jX + R'2/g. T = (3p/ω)·(R'2/g)·I'2². Breakdown from the Thévenin source V_th = V·Z_m/(R1 + Z_m), Z_th = R1 ∥ Z_m: g_c = R'2/√(R_th² + (X_th + X)²), T_max = 3p·V_th²/(2ω·(R_th + √(R_th² + (X_th + X)²))); R1 = 0: g_c = R'2/X, T_max = 3pV²/(2Xω). R(T) = R20·(234,5 + T)/254,5 |
| `core/identification.py` | 1 | R1 = U_dc/(2I_dc); P0 − 3R1I0² vs U0² → p_mec (intercept); Rf = 3V0²/P_fe, Xm = 3V0²/Q0; R'2 = Pcc/(3Icc²) − R1, X = √(Zcc² − Rcc²) (classical) or exact inversion; load-point fit of (Xm, X, R'2) by `least_squares` (soft_l1, multistart, 95 % CI) |
| `core/drive.py` | 2 | V/f law V = V0 + (Vn − V0)·f/fn up to fn, then V = Vn (field weakening); per speed: T = max over f_r of min(T_I(i_max), margin·T_bd, T_peak) |
| `core/losses.py` | 3 | P_cu = 3R1(T)I1² + 3R'2I'2²; iron P_fe ∝ f^β·B² → Rf(f) = Rf·(f/fn)^(2−β), β = 1,5; P_mec = aΩ + bΩ²; P_inv = P0 + k·P; η = P_out/P_in |
| `core/vehicle.py`, `io/cycles.py` | 4 | F = m·a + ½ρC_xS·v² + C_rr·m·g; T = F·r/(G·η_g) (traction), F·r·η_g/G (regen); ω_m = G·v/r; Wh/km = ∫P_batt dt / distance; WLTC class by W/kg (≤ 22 → 1, ≤ 34 → 2, else 3) |
| `core/thermal.py` | 5 | C_w·dT_w/dt = P_cu(T_w) − (T_w − T_s)/R_ws; C_s·dT_s/dt = P_fe + P_cu2 + (T_w − T_s)/R_ws − (T_s − T_a)/R_sa; life L = L_ref·2^((T_class − T)/10) |
| `core/winding.py` | 6 | q = Z/(2pm), α = 2πp/Z; k_d = sin(qνα/2)/(q·sin(να/2)), k_p = sin(νπy/(2τ)), k_w = k_d·k_p; stepped MMF and FFT ∝ k_wν/ν; E = 4,44·f·N·k_w1·Φ; Carter k_c = τ_s/(τ_s − γg) |
| `io/femm_model.py` (optional) | 6 | FEMM 4.2 magnetostatic stator model; B_r fundamental vs μ0·F1/(k_c·g); field at t + T/6 = field turned by q slots |
| `core/optimise.py` | 7 | Variables G, boost, margin, k_N (impedances × k_N²); min Wh/km and t_0–50 under envelope, T_w ≤ class − 20 K, I1 ≤ i_max, E/f ≤ 1,10·En/fn; differential evolution + ε-constraint sweep, 1500 evaluations per Pareto point |
| `io/report.py`, `io/excel.py`, `io/snapshot.py` | menu | A4 PDF (reportlab, 6 sections, assumptions box, démo footer); Excel sheet per module (SI arrays, units in headers) |
| `core/cours_valeurs.py`, `io/cours.py`, `src/evlab/docs/cours/*.md` | 8 | no new law: the 56 laws of tabs 1–7 explained, each with an example computed by core (201 numbers), live values of the motor in use, accent-insensitive search; PDF of the whole course (QTextDocument + QPrinter) |

## What is validated / what is démo

| Item | Status | Evidence |
|---|---|---|
| Γ circuit on TD5 Ex 1: g_c = 0,5, T_max = 126,3 N·m, torque formula, R(T) | **validated** | `tests/test_circuit.py` (numeric = closed form) |
| Identification chain (exact method) | **validated** | noise-free TD5 records → circuit recovered within 1 %; load fit within 0,1 %; 95 % CI coverage checked on 500 noisy draws (A14) |
| Classical locked-rotor formula bias (R'2 −13,1 %, X −7,7 % on TD5) | **validated** (known course-formula error) | `tests/test_identification.py`, A9 / A15 |
| Winding factors y = 9 and y = 7, MMF harmonics, TD2 Ex 1 EMF (1023 V) | **validated** | `tests/test_winding.py`: CLAUDE.md reference values |
| Envelope = best torque at each speed; T_bd·Ω_s² constant above fn (R1 = 0) | **validated** | brute-force scan, `tests/test_drive.py` |
| Efficiency map = circuit at fn; loss terms sum to P_in − P_out | **validated** | `tests/test_losses.py` |
| Vehicle: road-load terms, energy balance (1e-6), constant-speed analytical case, WLTC class thresholds | **validated** | `tests/test_vehicle.py` |
| Thermal: steady state, time constants = eigenvalues, implicit = RK45, 10 K rule | **validated** | `tests/test_thermal.py` |
| Optimisation: 1-variable optimum = brute force within 1 %; constraints met; same seed → same result | **validated** | `tests/test_optimise.py` |
| FEM air-gap fundamental vs analytical MMF (−6,5 % linear, 6 A); T/6 symmetry < 1 % | **validated** where FEMM is installed | `tests/test_femm_model.py`, A32 |
| Course (tab 8): every law named exists in core, every example number = an independent recomputation, every link has a target | **validated** | `tests/test_cours_pages.py`, `tests/test_cours_valeurs.py`, `tests/test_gui_cours.py` |
| Bench and load-point files `data/*_demo.csv` (TD5 Ex 1 + R1 = 0,5 Ω, p_mec = 60 W, 2,5 % noise) | **démo** | `docs/data_notes.md` |
| Driving cycle `data/cycle_demo.csv` (synthetic urban, not WLTC) | **démo** | A25; official WLTC files not yet provided |
| Vehicle (600 kg quadricycle, C_xS, C_rr, r) | **démo** | A22 |
| Drive limits (i_max 20 A, margin 80 %, f_max 100 Hz), inverter losses (50 W + 2 %) | **démo** | A16, A21 |
| Steinmetz β = 1,5; friction/windage split 0,5 | assumption | A19, A20 |
| Thermal network (C_w, C_s, R_ws, R_sa), insulation life L_ref | **démo** | A26, A28 (no timed TP3 readings) |
| FEM geometry and 10 turns per coil | **démo** | A32 |

The démo flags come from core: `drive.demo_fields` (A16), `losses.demo_fields` (A19 β, A21 inverter),
`thermal.demo_fields` (A26), one flag per field, plus the `is_demo` of the motor, the vehicle and the
cycle. Every tab's « démo » chip (tooltip: which values) and the PDF/Excel footer use the same French
labels (`io/notes.demo_labels`); the PDF footer is never truncated. Tab 4 reads its WLTC class from
`vehicle.wltc_class_for`.

---

# Module details

## Tab 1 · Identification (`gui/tab_identification.py`)

Left panel: **Machine** (V, f, p, R1 and its temperature, layout TP3 / Bornes;
rated speed read from the file's nameplate), **Essais (CSV)** (bench tests and
load points, each with a status line and a preview; "Charger la démo" loads the
two `data/*_demo.csv` files), **Méthode** (Formules classiques, Optimisation,
Comparer les deux), then **Identifier** and **Exporter PDF** (the whole
session report, same as Fichier → Exporter PDF). Right: a 2 × 2 grid, torque–speed | torque–slip on top and
current–speed | current–slip below (model curves over g ∈ (0, 1] from the core, speed
from `circuit.mechanical_speed` converted to tr/min at the GUI edge, measured points
on all four, C_max and g_c from `circuit.breakdown` on the torque–slip plot, one
shared legend in the card header; chip "points synthétiques (démo)"), and
the table Référence / Formules classiques / Optimisation with error % and the
95 % interval of the fit as tooltip.

**Identifier** runs `core.identification.compare_methods` in a `QThreadPool`
worker; progress and any identifiability warning appear in the status bar. The
identified motor is published to the `Session`, so tabs 2 to 7 use it
(classical result, or the fit when there is one). Layout: `docs/mockup_tab1.png`.
The layout choice (TP3 / bornes) does not change the classical formulas, which
are layout-free course approximations; it sets the circuit fitted to the load
points and the circuit used by tabs 2 to 7 (a note under the selector says so).

## Tab 2 · Enveloppe (`core/drive.py`, `gui/tab_envelope.py`)

`drive.envelope(motor, DriveSettings(i_max, boost, margin, f_max))` computes the
torque–speed envelope of the Session motor under the V/f law V = V0 + (Vn − V0)·f/fn
up to fn, then V = Vn (field weakening). Every reactance scales with f. At each
speed the available torque is min(current-limited torque, margin·breakdown
torque, the speed's own torque peak), found over the rotor frequency by a
vectorised golden-section search and bisections (A17).
The magnetic circuit is linear (A33). The air-gap flux is checked on E/f, with
E = |V − R1·I1| from the circuit, against E_n/fn at the rated no-load point; along
the envelope the worse of the full-torque and no-load points is kept
(`Envelope.flux`, `max_flux_ratio`). When it exceeds 1 (boost) the tab warns that
saturation is not modelled.
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
It returns η and every term; NaN outside the envelope. A point is kept only if the
map's own circuit (R1 at the winding temperature, Rf(f)) also respects the drive
limits: I1 ≤ i_max and T_em ≤ margin·T_bd (the envelope of tab 2 uses the
identified R1 and a constant Rf, so a hot winding shrinks the map slightly).
The default grid starts at zero shaft torque: that row holds the no-load losses
(iron, inverter P_0, mechanical) that tab 4 charges while coasting, with η = 0.

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
10 K rule with the mean ageing rate over the last cycle, L = L_ref/mean(2^((T_w −
T_class)/10)), as an order of magnitude (A28); `steady_state` raises « emballement
thermique » when the R1(T) feedback has no steady state.
The network values are démo (A26); `fit_cooling_curve` fits the winding time
constant to timed resistance readings when TP3 provides them.

The tab shows the parameters (with the two time constants), the insulation
class, the cycle count, T(t) with the class line, and KPI tiles (T max,
T mean, margin, life).
When the Session motor has R1 = 0 (TD5 Ex 1), the map has no stator copper
losses: tabs 5 and 7 show the chip « R1 ≈ 0 : pas de pertes cuivre stator —
lancez l'identification (onglet 1) », and the PDF prints the same line in its
thermal section.

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

### Animation FEM (`io/femm_model.py`, `gui/fem_view.py`, optional)

Button **Ouvrir l'animation FEM…** in tab 6. Needs pyfemm and FEMM 4.2 (Windows:
pyfemm's own calls; Linux: FEMM under Wine with Xvfb). Rotor lisse sans barres =
état magnétisant (à vide): a high current is overexcitation, not a load point;
the geometry is démo (A32).

- Currents are **peak** values, shown as "7,07 A crête (5,00 A eff)". Default:
  Î = √2·V/Xm, the magnetising current of the tab 1 motor; presets 6 and 18 A.
- Only the frames of t ∈ [0, T/6) are solved (n_frames multiple of 6); the others
  are the same field turned by 3 slots (30° mech.) with A+ → C− → B+.
  Per solved frame: linear iron ≈ 16 s, M-19 ≈ 60 s.
- Each complete run is saved in `data/fem_cache/` (frame PNGs, `b_r_demo.csv`,
  `meta.json`). Without FEMM the window replays these "résultats FEM
  pré-calculés"; two runs are committed (M-19 at I_µ = 7,07 A and at 18 A). FEM
  tests skip without FEMM.

| Iron, peak current | FEM B1 | μ0·F1/(k_c·g) | FEM / analytical |
|---|---|---|---|
| linear, 6 A | 0,647 T | 0,692 T | 0,935 |
| M-19, 6 A | 0,657 T | 0,692 T | 0,948 |
| M-19, I_µ = 7,07 A | 0,734 T | 0,816 T | 0,900 |
| M-19, 18 A | 0,966 T | 2,077 T | 0,465 (saturation) |

## Tab 7 · Optimisation (`core/optimise.py`, `gui/tab_optimisation.py`)

Design variables: gear ratio G, V/f boost, field-weakening margin and a
rewinding factor k_N (turns × k_N at the same copper area: every impedance
× k_N², rated voltage fixed). Each evaluation chains only the tested models
(envelope, 40 × 30 loss map, cycle simulation, 0–50 km/h, thermal model) and
returns Wh/km, the 0–50 km/h time and the constraints: every cycle point inside
the envelope, winding T max ≤ class limit − 20 K, stator current ≤ inverter limit,
max air-gap flux E/f over the envelope ≤ 1,10·En/fn (linear magnetic circuit, A33).
`scipy.optimize.differential_evolution` (seeded, process pool) with an
ε-constraint sweep traces the Pareto front; every evaluation is logged (A31).
Fixed budget: 1500 evaluations per Pareto point whatever the number of free
variables (generations = budget / (population × variables) − 1, no early stop).

Demo run (tab 1 démo identification, quick budget 3 points × 300 evaluations,
seed 0), minimum-consumption point of the front against the base design:

| | Base | Optimum |
|---|---|---|
| G / boost / margin / k_N | 3,53 / 0 V / 0,80 / 1,000 | 4,21 / 4,3 V / 0,88 / 1,026 |
| Wh/km | 75,4 | 73,4 (−2,7 %) |
| 0–50 km/h | 12,2 s | 11,2 s (−8,0 %) |
| T max winding | 61,5 °C | 57,2 °C |
| E/f max | 1,00 × En/fn | 1,07 × En/fn |

Before the E/f constraint the same run chose a 7,3 V boost (G = 4,32, 73,2 Wh/km,
10,9 s), i.e. 1,16 × En/fn at light load: the constraint costs 0,2 Wh/km and 0,3 s.

The tab takes the bounds of each variable (min = max fixes it) and the budget,
runs in a worker with progress and cancel, plots the front with the baseline
and every admissible evaluation, and shows baseline vs the selected design with
the gain in % per KPI. "Charger ce design" loads the rewound motor, the V/f
law and the gear ratio into every tab.

## Tab 8 · Cours (`core/cours_valeurs.py`, `io/cours.py`, `gui/tab_cours.py`, `gui/cours_pdf.py`)

A French course in 13 Markdown pages (`src/evlab/docs/cours/`, package data read with
`importlib.resources`): an introduction, one page per tab 1–7, then *Hypothèses et
limites*, *Glossaire des symboles*, *Notation : cours ↔ application*, *Validation* and
*Bibliographie*. It adds no physics: it states the 56 laws that tabs 1–7 compute (16, 8, 6,
6, 6, 8, 6), in the notation of Pr Boughrara's course (R_s, R_μ, X_μ, l_s'ω_s, R_r', I_s,
I_r', g; the notation page maps it to the code's R1, Rf, Xm, X, R'2). Sources: the course
PDF (*AC Electrical Machines*, cited as « Cours Pr Boughrara, MAS A §5.2, p. 94 », PDF page
numbers; the PDF itself is not in the repository); topics the course does not cover are
marked « hors cours » with a standard reference by author and title.

Every tab page has the same plan: *Ce que fait cet onglet*; *Lois et explications*,
grouped by theme (tab 1: Essais · Schéma équivalent · Couple et puissances · Ajustement par
moindres carrés), each law with its equation, symbol table, explanation, « Ce que ça
montre », the core function that computes it, an **Exemple** and the course reference;
*Hypothèses*; *Avec votre moteur*; three questions with hidden answers; a link to the tab.

- Numbers: the pages hold placeholders only. `core/cours_valeurs.exemples` computes the
  201 example numbers from core objects, on the reference motor without noise or on the
  noisy démo files (each example says which); `valeurs_moteur(motor)` gives the live values
  of « Avec votre moteur » (« moteur de référence » until a motor is identified).
  `io/cours.rendre` fills a page (French decimal comma) and raises `KeyError` on an unknown
  value; the tests check that no `{{` is left on any page.
- GUI: table of contents (pages, sections, law groups), search that ignores accents and
  case (« decrochage » finds « décrochage », matches highlighted), a `QTextBrowser` that
  never follows links itself: `evlab://onglet/…`, `evlab://page/…` and
  `evlab://reponse/…` are routed by the tab. A « ? » button on each tab 1–7, F1 (page of
  the tab on screen) and *Aide → Cours* open it. Light and dark themes.
- *Fichier → Exporter le cours en PDF…*: title page (EV-Traction Lab, ENP Alger, ME3, date),
  table of contents, one page per sheet, answers printed under their questions (52 A4 pages,
  about 1 s, DejaVu fonts, always light).

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
*Fichier → Exporter le cours en PDF…* writes the course of tab 8 (see above), not the session.

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
raises `LoaderError` with a French message. U, I, P, f of the tests must be > 0 and a
load point must have 0 < g < 1. Files named `*_demo.csv`, or starting with a
`# démo: …` line, are demo data. Regenerate the demo files with:

```bash
python -m evlab.io.demo_data
```

**Test datasets (`data/tests/`, synthetic, démo)**: three motors (petit 1,5 kW,
moyen 4 kW, grand 7,5 kW: bench tests + 10 load points g = 0,01…0,08, 2,5 % noise),
three smooth drive cycles that are not WLTC (urbain, route, mixte; 895–1190 s,
≤ 1,2 m/s²) and four bad files for the error messages. The French
`data/tests/README.md` gives each reference circuit and the tab 1 table to expect;
`tests/test_datasets.py` checks them (Xm, R'2 within 5 %, X inside the fit's 95 %
interval, Rf within ±16 %: the bounds that 2,5 % noise on light-load points allows).
They are copied into the Windows build (`EVLab\data\tests\`). Regenerate with:

```bash
python -m evlab.io.demo_data --tests
```

Formats and provenance: `docs/data_notes.md`.

Modelling assumptions are listed in `docs/assumptions.md`.
