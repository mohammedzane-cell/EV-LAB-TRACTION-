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

## data/

Empty for now. Planned: WLTC class 1 and class 3 speed profiles, TP3 measured points.
