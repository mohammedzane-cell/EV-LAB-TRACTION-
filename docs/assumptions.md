# Assumptions

Every value or modelling choice here is one that the identified circuit or a
TP measurement does not give. Each has its value and its reason.

| # | Module | Assumption | Value | Reason |
|---|--------|-----------|-------|--------|
| A1 | circuit | TP3 layout (docs/TPs_ME3.pdf, Figure 1): V1 → R1 in series (carries I1) → Rf ∥ jXm → jX + R'2/g. Breakdown slip and T_max use the Thévenin equivalent of R1 + magnetising branch | — | Decided by the user: TP3 subtracts 3·R1·I0² in the no-load test, so R1 carries the no-load current. With R1 = 0 it reduces to the TD5 values (g_c = R'2/X = 0,5, T_max = 126,3 N·m). |
| A2 | circuit | Under V/f the reactances scale with f/f_n; R1, R'2, Rf stay constant | — | Reactance = L·ω with L fixed by the circuit. Rf frequency dependence is not measured; refined in `losses.py` if TP data allow. |
| A3 | circuit | Stator copper loss is 3·R1·I1²; iron loss is 3·E²/Rf with E = V − R1·I1 | — | Consequence of A1. |
| A4 | circuit | Copper zero-resistance temperature 234.5 °C, reference 20 °C | 234,5 °C / 20 °C | Standard annealed copper value (course formula). |
