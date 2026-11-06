# EV-Traction Lab

ME3 mini-project (ENP Algiers, Machines électriques). Desktop virtual lab for an
induction-motor EV traction drive.

ONE MOTOR, ONE CHAIN: the motor identified in tab 1 (default: TD5 Ex 1, or TP3 data)
is the motor every other tab uses. Its circuit gives the envelope, the losses, the
cycle energy and the heat. Nothing downstream uses an invented motor.

Six modules, seven GUI tabs:
1. Identification of the Γ equivalent circuit (TP3 / TD5 tests): classical formulas + optimisation fit
2. V/f + field-weakening torque-speed envelope, computed from the identified circuit
3. Efficiency map η(T, ω) from the circuit losses (copper, iron via Rf, mechanical, inverter)
4. Vehicle sized to that motor (demo: light quadricycle), on the WLTC class set by its
   power-to-mass ratio (Wh/km, regeneration)
5. Two-node thermal model fed by the circuit losses + insulation life (10 K rule)
6. Winding: kd, kp, kw, MMF harmonics, EMF, slot table, animated rotating air-gap field
7. Design optimisation: drive and vehicle parameters optimised on the tested models
   (Pareto front Wh/km vs acceleration under thermal and envelope constraints)
Plus: PDF report (reportlab) and Excel export (openpyxl).

## Stack
Python 3.11/3.12 · numpy · scipy · pandas · matplotlib · pyqtgraph · PySide6 ·
pytest · pytest-qt · reportlab · openpyxl. No other dependency without asking me.
Optional, behind a feature flag: pymoo (NSGA-II), pyfemm + FEMM 4.2 (Windows, FEM stretch goal).

## Architecture (strict)
src/evlab/core/      pure physics, NO Qt import, NO file I/O, NO printing
  circuit.py identification.py drive.py losses.py vehicle.py thermal.py winding.py optimise.py
  session.py         one MotorParams object shared by all modules
src/evlab/io/        CSV/WLTC loaders, PDF and Excel export
src/evlab/gui/       PySide6 only: one module per tab, thin, calls core, draws results
tests/               pytest, one test file per core module, plus GUI smoke tests
docs/                course PDFs, roadmap, data notes, assumptions.md
data/                input files (WLTC, measured points); demo files named *_demo.csv

## Rules
1. core/ never imports Qt; gui/ never contains a formula.
2. Every public core function: type hints, SI units in the docstring, a test.
3. Inputs are validated (ValueError with a clear message), never silently clipped.
4. Every number shown in the GUI or the PDF comes from core/. No LLM ever computes a number.
5. Demo or synthetic data is labelled "démo" in the GUI and in the PDF.
6. Small steps: plan, write tests, implement, run pytest, show me the diff summary, stop.
7. No coefficient is invented if the identified circuit or a TP measurement can give it.
   Every remaining assumption goes in docs/assumptions.md with its value and reason.

## Conventions
- SI units internally (rad/s, N·m, W, K). Conversions (tr/min, km/h, °C) only at the GUI/IO edge.
- Per-phase quantities, star connection, phase voltage unless stated.
- Code, comments, docstrings in English. GUI text in French, decimal comma in displayed numbers.
- Long computations (optimisation, maps, cycles) run off the GUI thread (QThreadPool + signals).

## Reference values (tests must reproduce these)
- TD5 Ex 1 Γ circuit: V = 230 V/phase, f = 50 Hz, p = 2, Rf = 230 Ω, Xm = 46 Ω,
  X (leakage, N'2·ω) = 4 Ω, R'2 = 2 Ω, R1 ≈ 0.
  Breakdown slip g_c = R'2 / X = 0.5; T_max = 3·p·V² / (2·X·ω) = 126.3 N·m (ω = 2π·50).
- Torque: T = (3p/ω)·(R'2/g)·I'2².
- R1 temperature correction: R(T) = R20·(234.5 + T) / 254.5.
- Winding Z = 36, 2p = 4, m = 3 → q = 3, τ = 9 slots, α = 20° el.
  y = 9: kw1 = 0.9598, kw5 = 0.2176, kw7 = 0.1774
  y = 7: kd1 = 0.9598, kp1 = 0.9397, kw1 = 0.9019, kw5 = −0.0378, kw7 = −0.1359
  Coil pitch must be an integer number of slots ("5/6 pitch" is impossible for 36 slots / 4 poles).
- WLTC class by power-to-mass ratio: class 1 ≤ 22 W/kg, class 2 ≤ 34 W/kg, class 3 above.
  Class 1 (Low + Medium): 1022 s, 8.091 km, v_max 64.4 km/h.
  Class 3: 1800 s, 23.27 km, v_max 131.3 km/h.

## Definition of done (per stage)
pytest green · new code covered by tests · app starts and the tab works ·
no Qt in core/ · README section updated · one commit with a clear message.
