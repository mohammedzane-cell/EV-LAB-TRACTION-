# EV-LAB virtual laboratory — final status report

Branch `feature/ev-lab-virtual-lab` (from `1ac88f1`, the redesign head). Every commit is **local**: nothing
was pushed or merged. Development log: `docs/virtual_lab_log.md`; starting audit and end status:
`docs/engineering_gap_analysis.md`; assumptions A34–A38: `docs/assumptions.md`.

**Scope of the claims.** « Verified » below means checked by an automated test against an independent
computation (closed form, numerical integration, ODE solver, energy balance, brute force). Nothing in this
work is validated against measurements: the battery cell, the inverter components and the 3D dimensions are
démo or illustrative values, labelled as such in the GUI.

## COMPLETED

| Item | Where | Verified by |
|---|---|---|
| Motor characteristics: starting torque/current/cos φ, breakdown slip/torque/speed (exact Thévenin), no-load current, point at any speed | `core/characteristics.py`, tab 2 | TD5 closed forms; direct finite differences with R1 ≠ 0 |
| R'2 at the rotor temperature (aluminium 225 °C, copper 234,5 °C) | `characteristics.rotor_at_temperature` | linear law, inverse checks |
| Normalised sensitivities of T_max, g_c, T_start, I_start, η to R1, R'2, X, Xm, Rf | tab 2 table | S(Tmax, X) = −1, S(g_c, R'2) = 1, S(T_dém, R'2) = 0,6, S(T_dém, X) = −1,6 (TD5) |
| Inverter: linear range (V_dc/√6 SVPWM, V_dc/(2√2) SPWM), required DC voltage, average-value conduction and switching losses, SVPWM dwell times | `core/inverter.py`, tab 3 « moyen » model | integration over a fundamental period (1e-4); volt-second balance on 1000 random references |
| The selected inverter model in the loss map, hence in the vehicle's battery power and the thermal losses | `core/losses.py` | power balance; default map identical to the previous one |
| Battery pack: OCV(SOC), R, exact current, Coulomb-counting SOC, current/power-ceiling/SOC-window limits with undelivered power and refused regeneration recorded, pack losses | `core/battery.py`, tab 4 « Batterie » | per-step V_oc·I = P + R·I²; SOC vs `solve_ivp` (2e-4); every limit; motor → drive → map → vehicle → battery integration |
| Battery voltage vs the DC voltage the motor needs on the cycle (√6·V_ph) | `battery.dc_link_check`, tab 4 | inverse of the linear range; positive margin at 90 % SOC, shortfall flagged for a nearly empty pack |
| Interactive 3D (tab 9): motor (housing, shields, terminal box, stator, 3-phase winding with end turns, air gap, rotor, cage, shaft, bearings) and powertrain (battery, SOC column, inverter, DC/AC cables, motor, 2-stage reduction, differential, half-shafts, wheels, chassis); orbit/zoom/pan, presets, exploded view, cutaway, labels, per-component visibility, picking with the part's facts, colour modes | `core/scene3d.py`, `gui/tab_lab3d.py`, `gui/qml/lab3d.qml` | closed outward meshes with exact volumes; coil sides per layer = slot table; cutaway; render, pick, rotate, explode and hide checked on a real OpenGL renderer (Xvfb + Mesa) |
| 3D linked to the simulation: rotor/gear/wheel angles ∫ω dt, power flow per link (battery, DC, AC, shaft, wheels, friction brakes), SOC, two-node temperatures (one value per node) | tab 9 playback | wheel angle = distance / r; rotor = G × wheel; link powers close the vehicle's own energy balance; GUI values = core |

## PARTIAL

- **Battery ↔ drive coupling**: the DC-link margin is checked and reported (A38); the operating points of
  the vehicle are not recomputed with the battery's voltage or limits (refused regeneration and undelivered
  power are reported, not fed back).
- **Inverter DC voltage** of tab 3 is a setting, not tied to the pack voltage of tab 4 (the check above says
  whether the pack can supply it).
- **Sensitivity analysis** covers the motor parameters (tab 2), not the optimisation outputs (Wh/km,
  acceleration) of tab 7.
- **R'2(T)**: available in core (`rotor_at_temperature`), not exposed as a GUI control.
- **SVPWM losses** use the sine-PWM closed forms (A36).

## UNVERIFIED

- **Démo values**: battery cell (A34), inverter components (A35), 3D dimensions (A37): typical orders of
  magnitude, not a measured or catalogued part.
- **3D on Windows/macOS** (Direct3D/Metal through Qt's RHI): not run here; Linux Xvfb + Mesa OpenGL only.
- **Official WLTC cycles**: files not provided (3 skipped tests, démo cycle used).
- **Live FEMM runs** in this container: Wine crashes (also on the code before this mission); the 6 live-FEMM
  tests are deselected, cached runs are replayed.
- **No experimental validation** of any new model.

## FUTURE

Field-oriented control; magnetic saturation (needs a measured magnetisation curve); deep-bar / double-cage
rotor; fractional-slot and multiphase windings; battery RC branches and thermal model; recomputing the
operating points under battery voltage limits; sensitivity of the Pareto front; electromagnetic fields in
3D (would need a 3-D field solver: FEMM is 2-D and stays 2-D).

## Commands and results

Final full run on `e1d5282` (all code of the mission; docs only afterwards), Linux container, Python 3.13,
PySide6 6.12, offscreen Qt platform (`tests/conftest.py`):

```bash
python -m pytest tests/ -q -rs \
  --deselect tests/test_femm_model.py::test_case_validation \
  --deselect tests/test_femm_model.py::test_symmetry_matches_a_solved_frame \
  --deselect tests/test_femm_model.py::test_frames_and_pngs \
  --deselect tests/test_femm_model.py::test_air_gap_fundamental_against_the_analytical_mmf \
  --deselect tests/test_femm_model.py::test_saturation_lowers_the_fundamental \
  --deselect tests/test_gui_fem.py::test_real_femm_run_from_the_dialog
```

Result: **740 collected, 737 passed, 3 skipped, 0 failed** (exit code 0). The 3 skips wait for the official
WLTC files (`data/wltc_class1.csv`, `data/wltc_class3.csv`). The 6 deselected tests need a live FEMM run,
which crashes under Wine in this container, as it did before this mission. Baseline at the start of the
mission (`1ac88f1`): 684 passed, 3 skipped; the mission adds 53 tests (characteristics, inverter, losses with
the inverter, battery and DC link, scene3d, GUI of tabs 2–4 and 9, 3D rendering).

The 3D rendering test (`tests/test_gui_lab3d_render.py`, inside the run above) starts the check on Xvfb;
alone:

```bash
xvfb-run -a -s "-screen 0 1280x1024x24" env QT_QPA_PLATFORM=xcb QSG_RHI_BACKEND=opengl \
  python tools/lab3d_render_check.py --out /tmp/lab3d_check
```

Result: `"ok": true` — renders (OpenGL), 25 % of the view drawn for the motor and 67 % for the powertrain, a
click at the centre selects « rotor_core », a click on the background clears the selection, a 0,6 rad rotor
turn changes 1,1 % of the image, the exploded view 37 %, hiding the housing 13 %.

Demonstration of the real application (both themes, full chain from the démo bench files to tab 9):

```bash
xvfb-run -a -s "-screen 0 1920x1200x24" env QT_QPA_PLATFORM=xcb QSG_RHI_BACKEND=opengl \
  python tools/capture_lab3d.py --out docs/images/lab3d
```

Result: exit code 0, ten screenshots in `docs/images/lab3d/`, identical numbers in both themes, quoted in
`docs/demo_script.md` (t = 350 s: 58,7 km/h, 2036 tr/min, 30,3 N·m, P batterie 8,56 kW → DC 8,36 kW →
AC 8,14 kW → arbre 6,46 kW → roues 6,13 kW, SOC 86,7 %, bobinage 61,2 °C; t = 285 s: récupération,
−6,32 kW à l'arbre, −4,29 kW à la batterie).

Environment notes: the Xvfb runs needed the system packages libxcb-cursor0, libxcb-icccm4, libxcb-util1,
libxcb-image0, libxcb-keysyms1, libxcb-render-util0, libxcb-xkb1 and libxkbcommon-x11-0 (installed in this
test container only; no Python dependency was added). Not run here: Windows (Direct3D) and macOS (Metal),
live FEMM, official WLTC cycles.

## Commits (local, not pushed, not merged)

| Commit | Stage |
|---|---|
| `25c1753` | 1–2: audit, motor characteristics, R'2(T), sensitivities |
| `85a8295` | 3–4: inverter (DC link, average-value losses, SVPWM) and its place in the chain |
| `a9cb81c` | 5: battery |
| `f09c74b` | 6: interactive 3D, tab 9 |
| `e1d5282` | 7: battery voltage vs required DC voltage |
| this commit and the previous | 8–10: captures, documentation, log, report |
