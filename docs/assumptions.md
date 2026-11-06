# Assumptions

Every value or modelling choice here is one that the identified circuit or a
TP measurement does not give. Each has its value and its reason.

| # | Module | Assumption | Value | Reason |
|---|--------|-----------|-------|--------|
| A1 | circuit | Two Γ layouts, selected by `MotorParams.layout`. **tp3** (default): V1 → R1 in series (carries I1) → Rf ∥ jLω → jN'2ω + R'2/g. **terminals**: Rf ∥ jXm across V1, in parallel with R1 + jX + R'2/g (R1 carries I'2). Both reduce to a Thévenin source seen by the rotor branch (tp3: V·Zm/(R1+Zm), R1∥Zm; terminals: V, R1), which gives g_c and T_max in closed form; `breakdown()` also finds them numerically | tp3 | The user decided on tp3 (TP3 Figure 1: TP3 subtracts 3·R1·I0² at no-load, so R1 carries I0) and asked to keep the terminals layout available. With R1 = 0 the two are identical: checked against `docs/TD No 5.pdf`, Ex 1 figure (230 Ω ∥ j46 Ω across Vs, then 2/g + j4), g_c = 0,5, T_max = 126,3 N·m. The TP3 motor handout itself is not available (`TP_M3_ENP_Final_Complet.pdf` is the diode-rectifier TP). |
| A2 | circuit | Under V/f the reactances scale with f/f_n; R1, R'2, Rf stay constant | — | Reactance = L·ω with L fixed by the circuit. Rf frequency dependence is not measured; refined in `losses.py` if TP data allow. |
| A3 | circuit | Stator copper loss: 3·R1·I1² (tp3) or 3·R1·I'2² (terminals). Iron loss 3·E²/Rf, with E = V − R1·I1 (tp3) or E = V (terminals) | — | Consequence of the layout (A1). On TD5-like data with R1 = 1 Ω the two layouts give T_max = 97,4 vs 98,6 N·m. |
| A4 | circuit | Copper zero-resistance temperature 234.5 °C, reference 20 °C | 234,5 °C / 20 °C | Standard annealed copper value (course formula). |
| A5 | identification | DC test measured between two line terminals of the star winding: R1 = U_dc / (2·I_dc) | — | Star connection convention (CLAUDE.md). A delta-connected motor needs its own formula. |
| A6 | identification | The no-load test is done at rated voltage and frequency; they become V and f of the identified MotorParams | — | Rf and Xm depend on the flux level; the no-load test sets that level. |
| A7 | identification | `dc=None` means R1 = 0 | 0 Ω | TD5 Ex 1 hypothesis R1 ≈ 0. Used only when there is no DC test. |
| A8 | identification | Mechanical losses constant near synchronous speed, iron losses ∝ V²: p_mec = intercept of P0' vs V0² | — | Classical TP3 separation. With R1 ≠ 0, P_fe ∝ E² (not V0²), so the intercept carries a small bias. |
| A9 | identification | "Classical" locked-rotor test neglects the magnetising branch | — | Course formula. On TD5 it underestimates R'2 (1,74 vs 2 Ω) and X (3,69 vs 4 Ω), giving g_c = 0,47 and T_max = 136,8 N·m. The "exact" method (default) and the fit remove this error. |
| A10 | circuit | `efficiency(g)` uses the internal mechanical power (1 − g)·P_gap: mechanical losses are not in the circuit. Motor η = P_mec/P_in, generator η = P_in/P_mec, η = 0 when there is no useful output (no-load, locked rotor, plugging) | 0 W mechanical loss | TD5 Ex 1: "negligible mechanical losses". Shaft-side mechanical losses are added in `core/losses.py` (stage 4). |
| A11 | identification | The "exact" no-load and locked-rotor formulas invert the chosen layout; the "classical" formulas are the TP3 course recipe whatever the layout | — | In the terminals layout R1 carries no no-load current, so 3·R1·I0² is not subtracted. Identifying with the wrong layout gives a wrong circuit (tested). |
