"""V/f and field-weakening torque-speed envelope (stage 3, tab 2).

Computed from the identified circuit (core.circuit) only: constant V/f up to the
base speed, then constant voltage (field weakening) up to the maximum speed,
limited by current and by the breakdown torque.

Inputs: MotorParams, inverter limits (V_max per phase in V, I_max in A), f_max in Hz.
Outputs: envelope T_max(Ω) in N·m vs Ω in rad/s, base speed, P_max in W.
"""
