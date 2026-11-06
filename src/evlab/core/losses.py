"""Losses and efficiency map η(T, Ω) (stage 4, tab 3).

Copper (R1, R'2 with temperature correction), iron (via Rf), mechanical and
inverter losses, evaluated on the operating points of the identified circuit.

Inputs: MotorParams, torque grid in N·m, speed grid in rad/s, drive strategy.
Outputs: loss breakdown in W and efficiency (dimensionless) on the grid.
"""
