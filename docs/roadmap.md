# Roadmap

One stage = one commit (see Definition of done in CLAUDE.md).

| Stage | Content | Status |
|-------|---------|--------|
| 0 | Scaffold, `core/session.py` (MotorParams, TD5 Ex 1), `core/circuit.py` (Γ circuit: I'2, T, g_c, T_max, power balance, R(T)), architecture guard tests | done |
| 0b | TP3 circuit layout (R1 in series, Thévenin breakdown) | done |
| 1 | `core/identification.py`: no-load / locked-rotor / DC tests → Γ circuit (classical formulas + least-squares fit) | done (core) |
| 1b | Project setup: pinned requirements, documented empty modules, PySide6 main window with 7 empty tabs, `python -m evlab`, smoke tests | done |
| 2 | Tab 1 Identification (GUI on core.identification), demo CSV files and loaders | done |
| 3 | `core/drive.py`: V/f + field-weakening envelope; tab 2 | done |
| 4 | `core/losses.py`: efficiency map η(T, ω); tab 3 | done |
| 5 | `io/` WLTC loader + `core/vehicle.py` (class by W/kg, Wh/km, regen); tab 4 | |
| 6 | `core/thermal.py`: two-node model, insulation life (10 K rule); tab 5 | |
| 7 | `core/winding.py`: kd, kp, kw, MMF harmonics, EMF, slot table, rotating field; tab 6 | |
| 8 | `core/optimise.py`: Pareto Wh/km vs acceleration (scipy; pymoo behind flag); tab 7 | |
| 9 | PDF report (reportlab) + Excel export (openpyxl) | |
