"""Stator winding analysis (stage 7, tab 6).

Distribution, pitch and winding factors kd, kp, kw for each harmonic, MMF
harmonics, EMF, slot table and the rotating air-gap field.
Reference: Z = 36, 2p = 4, m = 3 → q = 3, τ = 9 slots, α = 20° el.

Inputs: slots Z, pole pairs p, phases m, coil pitch y (integer number of slots).
Outputs: factors (dimensionless), MMF in A·turns, EMF in V.
"""
