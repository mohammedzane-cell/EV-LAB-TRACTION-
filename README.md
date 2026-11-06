# EV-Traction Lab

PROJECT ME3 — ENP Alger, Machines électriques. Laboratoire virtuel d'une chaîne
de traction de véhicule électrique à moteur asynchrone.

One motor, one chain: the Γ circuit identified in tab 1 (default TD5 Ex 1) feeds
every other module. See `CLAUDE.md` for the full specification and
`docs/roadmap.md` for the stages.

## Install and test

```bash
pip install -e ".[dev]"
```

```bash
pytest
```

## Layout

```
src/evlab/core/   pure physics (no Qt, no I/O)
src/evlab/io/     loaders and exports
src/evlab/gui/    PySide6 tabs
tests/            pytest
docs/             roadmap, assumptions
data/             input files (*_demo.csv for demo data)
```

## Core: Γ equivalent circuit (`core/circuit.py`, `core/session.py`)

`MotorParams` is the single per-phase Γ circuit shared through a `Session`
(defaults to TD5 Ex 1: V = 230 V, f = 50 Hz, p = 2, Rf = 230 Ω, Xm = 46 Ω,
X = 4 Ω, R'2 = 2 Ω, R1 = 0).

`circuit.py` provides, in SI units, with optional V/f supply override:

- `rotor_current`, `torque` — T = (3p/ω)·(R'2/g)·I'2², vectorised over slip
- `breakdown_slip`, `max_torque` — TD5: g_c = 0,5, T_max = 126,3 N·m
- `slip_from_speed`, `speed_from_slip`
- `operating_point` — I1, I'2, Ife, Iµ, cos φ, P_in, P_fe, P_cu1, P_gap, P_cu2, P_mech
- `copper_resistance` — R(T) = R20·(234,5 + T)/254,5

Modelling assumptions are listed in `docs/assumptions.md`.
