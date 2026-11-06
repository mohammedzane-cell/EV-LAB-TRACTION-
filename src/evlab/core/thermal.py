"""Two-node thermal model and insulation life (stage 6, tab 5).

Winding and frame nodes fed by the circuit losses over the cycle; insulation
life by the 10 K rule (life halves every +10 K).

Inputs: losses vs time in W, thermal resistances in K/W, capacitances in J/K, ambient in K.
Outputs: node temperatures vs time in K, relative insulation life.
"""
