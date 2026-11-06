"""Vehicle sized to the motor, on a WLTC cycle (stage 5, tab 4).

Road load (rolling, aerodynamic, grade, inertia), WLTC class chosen from the
power-to-mass ratio (class 1 ≤ 22 W/kg, class 2 ≤ 34 W/kg, class 3 above),
energy consumption in Wh/km with regeneration.

Inputs: MotorParams-derived envelope and efficiency map, vehicle data, cycle v(t) in m/s.
Outputs: wheel/motor torque and speed vs time, battery energy in J, Wh/km.
"""
