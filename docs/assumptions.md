# Assumptions

Every value or modelling choice here is one that the identified circuit or a
TP measurement does not give. Each has its value and its reason.

| # | Module | Assumption | Value | Reason |
|---|--------|-----------|-------|--------|
| A1 | circuit | TP3 layout: V1 → R1 in series (carries I1) → Rf ∥ jLω → jN'2ω + R'2/g. Breakdown slip and T_max use the Thévenin equivalent of R1 + magnetising branch | — | Decided by the user (TP3 Figure 1): TP3 subtracts 3·R1·I0² at no-load, so R1 carries I0. Checked against `docs/TD No 5.pdf`, Ex 1 figure (230 Ω ∥ j46 Ω across Vs, then 2/g + j4, no R1): this is the R1 = 0 case, g_c = 0,5, T_max = 126,3 N·m. The TP3 motor handout itself is not available: `TP_M3_ENP_Final_Complet.pdf` is the power-electronics TP (three-phase diode rectifiers), so the R1 position rests on the user's statement. |
| A2 | circuit | Under V/f the reactances scale with f/f_n; R1, R'2, Rf stay constant | — | Reactance = L·ω with L fixed by the circuit. Rf frequency dependence is not measured; refined in `losses.py` if TP data allow. |
| A3 | circuit | Stator copper loss is 3·R1·I1²; iron loss is 3·E²/Rf with E = V − R1·I1 | — | Consequence of A1. |
| A4 | circuit | Copper zero-resistance temperature 234.5 °C, reference 20 °C | 234,5 °C / 20 °C | Standard annealed copper value (course formula). |
| A5 | identification | DC test measured between two line terminals of the star winding: R1 = U_dc / (2·I_dc) | — | Star connection convention (CLAUDE.md). A delta-connected motor needs its own formula. |
| A6 | identification | The no-load test is done at rated voltage and frequency; they become V and f of the identified MotorParams | — | Rf and Xm depend on the flux level; the no-load test sets that level. |
| A7 | identification | `dc=None` means R1 = 0 | 0 Ω | TD5 Ex 1 hypothesis R1 ≈ 0. Used only when there is no DC test. |
| A8 | identification | Mechanical losses constant near synchronous speed, iron losses ∝ V²: p_mec = intercept of P0' vs V0² | — | Classical TP3 separation. With R1 ≠ 0, P_fe ∝ E² (not V0²), so the intercept carries a small bias. |
| A9 | identification | "Classical" locked-rotor test neglects the magnetising branch | — | Course formula. On TD5 it underestimates R'2 (1,74 vs 2 Ω) and X (3,69 vs 4 Ω), giving g_c = 0,47 and T_max = 136,8 N·m. The "exact" method (default) and the fit remove this error. |
