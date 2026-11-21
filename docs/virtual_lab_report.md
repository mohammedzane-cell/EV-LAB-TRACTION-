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

See the « Test results » section below (filled from the final run).
