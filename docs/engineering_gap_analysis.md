# EV-LAB — engineering gap analysis (start of the virtual-laboratory mission)

Branch `feature/ev-lab-virtual-lab`, created from `feature/ev-lab-professional-ui` at `1ac88f1`, which holds
the working application: the redesign on top of `claude/sleepy-hypatia-nkmuki`. Neither is merged or pushed.
Baseline tests at `1ac88f1`: 684 passed, 3 skipped (the WLTC files), 0 failed; 6 live-FEMM tests deselected
because Wine crashes in this container (the same failure on the pre-redesign code).

Status: **COMPLETE** (implemented and tested against an independent reference), **PARTIAL** (part of
the capability), **MISSING**, **UNVERIFIED** (implemented but not demonstrated on the data that matters).
« Tested » means an automated test in `tests/`.

## Induction motor (`core/circuit.py`, `core/identification.py`, `io/demo_data.py`)

| Capability | Status | Evidence / gap |
|---|---|---|
| Per-phase Γ circuit, two layouts (R1 first, terminals) | COMPLETE | TD5 Ex 1: g_c = 0,5, T_max = 126,3 N·m (`test_circuit.py`) |
| Synchronous speed, slip, torque–speed, current, power factor, efficiency | COMPLETE | `circuit.operating_point`, power balance tested |
| Breakdown slip and torque | COMPLETE | numeric and Thévenin closed form |
| Starting torque and current, rated operating point | PARTIAL | computable with `operating_point` at g = 1 / rated slip, but no function, no display |
| Parameter identification (DC, no-load, locked rotor, load-point fit) | COMPLETE on synthetic data | known circuit recovered (exact method < 1 %), CI coverage checked |
| Identification on real TP3 measurements | UNVERIFIED | 2024-25: classical result = hand calculation (0,1 %); 2026-27 refused (negative p_méc); fit needs cos φ and fails on a zero torque |
| Test simulation (generate DC / no-load / locked / load tests from a circuit) | COMPLETE | `io/demo_data`, used by the démo and test datasets |
| R1 temperature correction | COMPLETE | 234,5 rule |
| R'2 temperature correction | MISSING | rotor copper at the identification temperature only |
| Saturation (Xm(E)) | MISSING | linear magnetising branch (A33); the FEM shows saturation at rated I_µ; no measured magnetisation curve |
| Rotor-frequency effects (deep bar) | MISSING | no data (no locked-rotor test at reduced frequency) |
| Parameter sensitivity | MISSING | — |

## Drive and inverter (`core/drive.py`, `core/losses.py`)

| Capability | Status | Evidence / gap |
|---|---|---|
| V/f law with boost, field weakening, current limit, breakdown margin | COMPLETE | `drive.envelope`, brute-force check |
| Air-gap flux E/f check | COMPLETE | warning above En/fn, optimisation constraint |
| DC-link voltage and modulation limit | MISSING | the phase voltage is capped by the motor rating only |
| Inverter losses | PARTIAL | P0 + k·P (démo, A21), no conduction/switching physics |
| Average-value inverter, SVPWM | MISSING | — |
| FOC | MISSING | — |

## Vehicle (`core/vehicle.py`, `io/cycles.py`)

| Capability | Status | Evidence / gap |
|---|---|---|
| Longitudinal dynamics (inertia, rolling, aero, grade), gearbox efficiency, wheel ↔ motor mapping | COMPLETE | energy balance 1e-6, analytical constant-speed case |
| Operating point on the loss map, regenerative braking, auxiliaries | COMPLETE | `vehicle.simulate` |
| Official WLTC cycles | UNVERIFIED | files not provided (3 tests skip); démo cycle used |
| Battery side | MISSING | « battery power » = shaft power + losses + auxiliaries; no voltage, current, SOC, limit |

## Battery and energy

| Capability | Status |
|---|---|
| Pack configuration, OCV(SOC), internal resistance, SOC evolution, current/power limits, regenerative-charging limit, battery losses | MISSING |

## Thermal, electromagnetics, optimisation

| Capability | Status | Evidence / gap |
|---|---|---|
| Two-node thermal network, time constants, R1(T) feedback, insulation life | COMPLETE (model); UNVERIFIED (parameters démo, no cooling measurement) | `test_thermal.py` |
| Winding factors, MMF harmonics, EMF, rotating field (integral-slot, 3-phase) | COMPLETE | reference values, FFT = k_wν/ν |
| Fractional-slot / multiphase windings | MISSING | refused with a message |
| 2D FEM (FEMM) of the magnetising state | COMPLETE where FEMM runs; UNVERIFIED here (Wine broken) | cached runs replayed |
| Optimisation (DE + ε-constraint, Pareto, constraints from the models) | COMPLETE | 1-variable optimum = brute force |
| Sensitivity analysis | MISSING | — |

## Interface and 3D

| Capability | Status |
|---|---|
| Professional redesign of the 8 workspaces | COMPLETE (`docs/ui_redesign_acceptance.md`) |
| Interactive 3D motor and powertrain linked to the simulation | MISSING |

## Priorities for this mission

1. **Battery and energy** (the missing link between the vehicle and the source): pack model, SOC, limits,
   regenerative-charging limit, losses, in the vehicle workspace.
2. **Inverter**: DC-link voltage limit and an average-value loss model (conduction + switching), with the
   existing linear model kept as the default baseline; SVPWM as a separate verified module.
3. **Motor characteristics**: starting and rated points, R'2(T) as an option, parameter sensitivity.
4. **Interactive 3D** (motor and powertrain) driven by the session motor, the winding and the cycle
   simulation.
5. **FUTURE** (needs data or a larger model): saturation from a measured magnetisation curve, deep-bar
   rotor, FOC, fractional-slot windings.
