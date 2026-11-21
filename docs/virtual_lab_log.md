# EV-LAB virtual laboratory — development log

Mission: turn EV-LAB into an integrated EV-traction virtual laboratory around the identified induction motor,
in small verified stages. Branch `feature/ev-lab-virtual-lab` (from the redesign head `1ac88f1`); every commit
is local: nothing is pushed or merged.

Rules followed at every stage (CLAUDE.md): physics in `core/` (no Qt), the GUI only formats and draws;
every new law tested against an independent reference; every assumed number listed in
`docs/assumptions.md` and labelled « démo » in the GUI; inputs validated, never silently clipped; no new
dependency (Qt Quick 3D is part of PySide6). Nothing here is claimed as experimentally validated: « verified »
means checked against an independent computation (closed form, numerical integration, ODE solver, energy
balance), not against measurements.

| Stage | Commit | Content | Verification |
|---|---|---|---|
| 1 · Audit | `25c1753` | `docs/engineering_gap_analysis.md`: COMPLETE / PARTIAL / MISSING / UNVERIFIED per capability, priorities | baseline 684 passed, 3 skipped (6 live-FEMM tests deselected: Wine crashes in this container) |
| 2 · Motor | `25c1753` | `core/characteristics.py`: starting torque/current/power factor, breakdown slip/torque/speed (exact Thévenin), no-load current, point at a speed, R'2 at the rotor temperature (Al or Cu), normalised sensitivities S = (∂y/∂p)(p/y); tab 2 « Caractéristiques » and « Sensibilités » | TD5 closed forms (S(Tmax, X) = −1, S(g_c, R'2) = 1, S(T_dém, R'2) = 0,6, S(T_dém, X) = −1,6), a direct difference with R1 ≠ 0, invalid inputs |
| 3 · Inverter | `85a8295` | `core/inverter.py`: DC-link linear range (V_dc/√6 SVPWM, V_dc/(2√2) SPWM), average-value IGBT/diode conduction and switching losses, SVPWM sectors and dwell times; selectable « moyen » inverter model in tab 3 (the linear A21 model stays the default) | closed forms = numerical integration over a period (1e-4); SVPWM volt-second balance on 1000 random references; default map unchanged; map p_inv = inverter.losses; power balance |
| 4 · Chain consistency | `85a8295` | the selected inverter model enters the efficiency map, hence the vehicle's battery power (tab 4) and the thermal losses (tab 5): one motor, one drive, one chain | power balance of the map with the new model; DC-link limit marks the points it cannot reach as outside |
| 5 · Battery | `a9cb81c` | `core/battery.py`: pack n_s × n_p, OCV(SOC), R, exact current for a power, Coulomb counting, current / power-ceiling / SOC-window limits with the undelivered power and the refused regeneration recorded; tab 4 « Batterie » page | exact root; per-step energy balance V_oc·I = P + R·I²; SOC against `solve_ivp` (2e-4); every limit; invalid inputs; motor → drive → map → vehicle → battery integration |
| 6 · 3D | `f09c74b` | `core/scene3d.py` (meshes, illustrative motor and powertrain, cycle playback), tab 9 « Labo 3D » in Qt Quick 3D: orbit/zoom/pan, exploded view, cutaway, labels, visibility, picking, colour modes, playback linked to tabs 4, 5, 6 | closed outward meshes with exact volumes; coil sides per layer = slot table; cutaway; gear kinematics; θ_wheel(end) = distance / r; link powers close the vehicle's own energy balance; GUI values = core; real rendering + mouse picking under Xvfb |
| 7 · DC-link voltage | `e1d5282` | battery terminal voltage against the DC voltage the motor needs at every cycle step (√6·V_ph with SVPWM): margin and the steps where the pack is too low | required voltage = inverse of the linear-range limit; démo cycle at 90 % SOC has a positive margin; a nearly empty pack is flagged |
| 8 · Regression | `0780866` | full test suite, render check, demo captures (`docs/images/lab3d/`) | 737 passed, 3 skipped, 0 failed; render check ok |
| 9 · Documentation | `0780866` | README, user guide, demo script, assumptions A34–A37, gap analysis status | — |
| 10 · Report | — | `docs/virtual_lab_report.md`: COMPLETED / PARTIAL / UNVERIFIED / FUTURE, exact commands and results | — |

## Notes per stage

**Stage 2.** The breakdown point uses `circuit.breakdown(m, method="closed")`: with the numerical search the
finite-difference sensitivities carried a 5e-5 noise (S = 0,99995 instead of 1).

**Stage 3.** The SPWM closed forms are reused for SVPWM (A36). The inverter DC voltage is a setting of tab 3;
stage 7 checks it against the battery voltage on the cycle instead of coupling the two silently.

**Stage 5.** A limit is recorded only when it is active (rounding had produced 1e-11 W « shortfalls»).
The pack follows the vehicle's terminal power: the vehicle result is not modified by the battery limits; the
refused regeneration and the undelivered power are reported, not fed back (A34).

**Stage 6.** Qt Quick 3D draws nothing on Qt's « offscreen » platform (no 3D API): the tab detects it and
says so; the rendering itself is checked by `tools/lab3d_render_check.py` under Xvfb + Mesa OpenGL (the
system packages libxcb-cursor0, libxcb-icccm4, libxcb-util1, libxcb-image0, libxcb-keysyms1,
libxcb-render-util0, libxcb-xkb1 and libxkbcommon-x11-0 were installed in the test container only; Windows
uses Direct3D and was not tested here). The layout-test fixture now shows tab 4's inner pages once:
the legend test checks geometry, which Qt computes only for pages that have been shown (a stage-5 regression
of the test, not of the app).
