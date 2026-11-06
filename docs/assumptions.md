# Assumptions

Every value or modelling choice here is one that the identified circuit or a
TP measurement does not give. Each has its value and its reason.

| # | Module | Assumption | Value | Reason |
|---|--------|-----------|-------|--------|
| A1 | circuit | Γ topology: magnetising branch (Rf ∥ jXm) across the terminals; R1 in the series branch carrying I'2 | — | Course Γ model (TD5). Gives the closed forms g_c = R'2/√(R1²+X²) and T_max used in the reference values. |
| A2 | circuit | Under V/f the reactances scale with f/f_n; R1, R'2, Rf stay constant | — | Reactance = L·ω with L fixed by the circuit. Rf frequency dependence is not measured; refined in `losses.py` if TP data allow. |
| A3 | circuit | Stator copper loss in the Γ model is 3·R1·I'2² (R1 carries I'2, not I1) | — | Consequence of A1; the magnetising current does not flow in R1 in this model. |
| A4 | circuit | Copper zero-resistance temperature 234.5 °C, reference 20 °C | 234,5 °C / 20 °C | Standard annealed copper value (course formula). |
