"""Design optimisation (stage 8, tab 7).

Drive and vehicle parameters optimised on the tested models: Pareto front of
Wh/km vs 0-50 km/h acceleration time, under thermal and envelope constraints.
scipy by default; pymoo NSGA-II behind a feature flag.

Inputs: MotorParams, design variable bounds, cycle.
Outputs: Pareto set (variables, Wh/km, acceleration time in s).
"""
