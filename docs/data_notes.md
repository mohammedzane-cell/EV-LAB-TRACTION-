# Data notes

Where every input comes from. Demo or synthetic data are named `*_demo.csv`
and labelled "démo" in the GUI and in the PDF.

## Course documents (local only, `docs/*.pdf` is git-ignored)

Copied from the ME3 course Drive; read locally, never committed.

| File | Content | Used for |
|------|---------|----------|
| `TD No 5.pdf` | Induction motor: Ex 1 Γ circuit (230 Ω ∥ j46 Ω, 2/g + j4; 230/400 V, 50 Hz, 1350 tr/min), Ex 2–3 no-load / locked-rotor tests, Ex 5–6 equivalent circuit | Reference motor `td5_ex1()`, identification tests |
| `TD No 2.pdf` | Synchronous machines: EMF, winding coefficient, synchronous reactance | Tab 6 (winding, EMF) |
| `TP_M3_ENP_Final_Complet.pdf` | Power electronics TP M3: three-phase diode rectifiers (PD3, Graetz bridge) | Not the motor TP3; possibly the inverter/DC-bus side later |

Missing: the TP3 induction-motor handout (Figure 1, measured points).

## Synthetic bench records (tests/fixtures/td5_records.py)

Generated from a known circuit with `core.circuit`, so the identified values can
be compared with the truth. Measured values: U (line), I, P for 8 no-load points
(0,4 … 1,1·Un) and one locked-rotor point at 0,25·Un; DC test U_dc, I_dc at 5 A.

| Case | Circuit | R1 | p_mec | Temperatures |
|------|---------|----|-------|--------------|
| A | TD5 Ex 1 | 0 | 0 (TD5: negligible, given) | — |
| B (démo) | TD5 Ex 1 + synthetic R1 and p_mec | 0,5 Ω at 75 °C | 60 W (separated by the U² fit) | DC test at 20 °C |

Noise: each measured value × (1 + 0,02·N(0, 1)), fixed seed 2026. Temperatures and nameplate are exact.

## data/

Empty for now. Planned: WLTC class 1 and class 3 speed profiles, TP3 measured points.
