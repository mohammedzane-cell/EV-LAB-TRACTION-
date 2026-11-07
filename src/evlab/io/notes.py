"""Fixed French notes shown in the GUI and printed in the reports (text only: no physics).

demo_labels lists, in French, which inputs are démo or assumed values; the démo
flags themselves come from core (is_demo fields and the demo_fields functions).
"""

from __future__ import annotations

from evlab.core import drive, losses, thermal
from evlab.core import vehicle as vh
from evlab.core.session import MotorParams

R1_ZERO_NOTE = "R1 ≈ 0 : pas de pertes cuivre stator — lancez l'identification (onglet 1)"

_DRIVE_NAMES = {"i_max": "I max", "boost": "boost", "margin": "marge", "f_max": "f max"}
_THERMAL_NAMES = {"c_w": "C_w", "c_s": "C_s", "r_ws": "R_ws", "r_sa": "R_sa"}


def demo_labels(
    motor: MotorParams | None = None,
    drive_settings: drive.DriveSettings | None = None,
    loss_settings: losses.LossSettings | None = None,
    thermal_params: thermal.ThermalParams | None = None,
    vehicle: vh.Vehicle | None = None,
    cycle: vh.Cycle | None = None,
    include_beta: bool = False,
) -> list[str]:
    """French labels of the démo inputs among those given (empty list: nothing démo).

    Args:
        motor, drive_settings, loss_settings, thermal_params, vehicle, cycle: inputs a result depends on.
        include_beta: also list β = 1,5 (A19, assumed), as the reports do.
    """
    out = []
    if motor is not None and motor.is_demo:
        out.append(f"moteur identifié sur des essais synthétiques ({motor.source})")
    if cycle is not None and cycle.is_demo:
        out.append(f"cycle {cycle.name}")
    if vehicle is not None and vehicle.is_demo:
        out.append(vehicle.name)
    if drive_settings is not None and (f := drive.demo_fields(drive_settings)):
        out.append(f"réglages variateur {', '.join(_DRIVE_NAMES[n] for n in f)} (A16)")
    if loss_settings is not None:
        f = losses.demo_fields(loss_settings)
        if any(n.startswith("inverter") for n in f):
            out.append("pertes onduleur (A21)")
        if include_beta and "beta" in f:
            out.append(f"β = {str(loss_settings.beta).replace('.', ',')} (A19)")
    if thermal_params is not None and (f := thermal.demo_fields(thermal_params)):
        out.append(f"réseau thermique {', '.join(_THERMAL_NAMES[n] for n in f)} (A26)")
    return out
