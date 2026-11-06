"""Snapshot of the session for the reports: the motor and the results of every tab, plus demo flags.

The PDF report (io.report) and the Excel export (io.excel) are both built from a
Snapshot, so they always show the same numbers. Every result in it comes from
core/; complete() fills the missing ones with the core and the given inputs.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field, replace

from evlab.core import drive, losses, thermal, vehicle
from evlab.core import winding as wd
from evlab.core import identification as ident
from evlab.core import optimise as op
from evlab.core.session import MotorParams

MAP_GRID = (80, 60)  # loss map recomputed for the report when tab 3 was never opened


@dataclass(frozen=True)
class Snapshot:
    """Everything a report shows. Optional fields are None when not computed.

    Attributes:
        group: group / author line of the title block.  date: report date.
        motor: the Session motor (identified in tab 1).
        identification: tab 1 comparison of the methods.
        drive_settings, envelope: tab 2.  loss_settings, emap: tab 3.
        vehicle, sizing, drive_result, cycle: tab 4.
        thermal_params, thermal, insulation_class, n_thermal_cycles: tab 5.
        winding: tab 6 (chosen pitch).  pareto: tab 7.
    """

    group: str
    date: dt.date
    motor: MotorParams
    drive_settings: drive.DriveSettings
    loss_settings: losses.LossSettings
    thermal_params: thermal.ThermalParams
    winding: wd.Winding
    identification: ident.MethodComparison | None = None
    envelope: drive.Envelope | None = None
    emap: losses.EfficiencyMap | None = None
    vehicle: vehicle.Vehicle | None = None
    sizing: vehicle.Sizing | None = None
    drive_result: vehicle.DriveResult | None = None
    cycle: vehicle.Cycle | None = None
    thermal: thermal.ThermalResult | None = None
    insulation_class: str = "F"
    n_thermal_cycles: int = 10
    pareto: op.ParetoResult | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    def demo_items(self) -> list[str]:
        """What in this report is démo or synthetic (shown in the footer)."""
        items = []
        if self.motor.is_demo:
            items.append(f"moteur identifié sur des essais synthétiques ({self.motor.source})")
        if self.cycle is not None and self.cycle.is_demo:
            items.append(f"cycle {self.cycle.name}")
        if self.vehicle is not None and self.vehicle.is_demo:
            items.append(self.vehicle.name)
        if self.thermal_params.is_demo:
            items.append("réseau thermique (C, R)")
        if self.loss_settings.inverter:
            items.append("pertes onduleur")
        return items


def complete(s: Snapshot) -> Snapshot:
    """Compute, with the core and the snapshot's inputs, every result still missing (except the optimisation)."""
    env = s.envelope or drive.envelope(s.motor, s.drive_settings)
    emap = s.emap if s.emap is not None and s.emap.envelope is env else None
    notes = list(s.notes)
    if emap is None:
        t, w = losses.default_grid(s.motor, env, s.loss_settings, *MAP_GRID)
        emap = losses.efficiency_map(s.motor, t, w, env.settings, s.loss_settings, envelope=env)
        notes.append("carte de rendement recalculée pour le rapport (grille 80 × 60)")
    res, sizing, veh = s.drive_result, s.sizing, s.vehicle
    if s.cycle is not None and s.vehicle is not None and (res is None or sizing is None):
        sizing = vehicle.size_vehicle(s.motor, env, s.loss_settings, s.vehicle, s.cycle)
        res = vehicle.simulate(s.cycle, s.vehicle, s.motor, env, emap, s.loss_settings)
    th = s.thermal
    if th is None and res is not None:
        pc, pf = thermal.cycle_losses(res, emap)
        th = thermal.simulate(s.thermal_params, pc, pf, n_cycles=s.n_thermal_cycles,
                              copper_ref_k=thermal.map_copper_temperature(emap, s.motor.r1_temperature_k),
                              insulation_class=s.insulation_class)
    return replace(s, envelope=env, emap=emap, drive_result=res, sizing=sizing, vehicle=veh, thermal=th,
                   notes=tuple(notes))
