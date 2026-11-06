"""Excel export of a Snapshot (openpyxl): one sheet per module, raw arrays, units in the headers.

Values are the core results in SI units, unrounded (rad/s, N·m, W, K, J, s, m/s);
openpyxl writes 16 significant digits (Excel itself keeps 15), so a value reads
back equal to the core result within a relative 1e-15.
NaN and ±inf are written as empty cells (Excel has no NaN). Sheet "Lisez-moi" says
which values are démo.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from evlab.core import winding as wd
from evlab.io.snapshot import Snapshot

HEADER_FONT = Font(bold=True)
HEADER_FILL = PatternFill("solid", fgColor="EEF1F6")


def _cell(v):
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        return float(v) if math.isfinite(v) else None
    return v


def _sheet(wb: Workbook, title: str, header: list[str], rows) -> None:
    ws = wb.create_sheet(title)
    ws.append(header)
    for c in ws[1]:
        c.font, c.fill = HEADER_FONT, HEADER_FILL
    for row in rows:
        ws.append([_cell(v) for v in row])
    for k, h in enumerate(header, start=1):
        ws.column_dimensions[ws.cell(1, k).column_letter].width = max(12, len(h) + 2)
    ws.freeze_panes = "A2"


def _columns(arrays: dict[str, np.ndarray]):
    names = list(arrays)
    return names, zip(*(np.asarray(arrays[n]).ravel() for n in names))


MOTOR_FIELDS = (("r1", "R1 [Ω]"), ("r_fe", "Rf [Ω]"), ("x_m", "Xm [Ω]"), ("x_leak", "X [Ω]"), ("r2p", "R'2 [Ω]"))


def build_workbook(s: Snapshot, path: str | Path) -> Path:
    """Write the workbook of the snapshot to `path` and return it."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Lisez-moi"
    demo = s.demo_items()
    for line in (["EV-Traction Lab — export des résultats"], [s.group, s.date.isoformat()],
                 ["Unités SI dans les en-têtes ; valeurs non arrondies, issues de core/."],
                 ["Valeurs démo :", " ; ".join(demo) if demo else "aucune"]):
        ws.append(line)
    ws["A1"].font = Font(bold=True, size=13)
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 90

    # identification
    m = s.motor
    rows = [["session (" + m.source + ")", m.layout, m.v_phase, m.f_rated, m.pole_pairs]
            + [getattr(m, n) for n, _ in MOTOR_FIELDS] + [m.p_mech]]
    ic = s.identification
    if ic is not None:
        if ic.reference is not None:
            r = ic.reference
            rows.append(["référence (" + r.source + ")", r.layout, r.v_phase, r.f_rated, r.pole_pairs]
                        + [getattr(r, n) for n, _ in MOTOR_FIELDS] + [r.p_mech])
        for row in ic.shown:
            mm = ic.motor(row)
            rows.append([row, mm.layout, mm.v_phase, mm.f_rated, mm.pole_pairs]
                        + [getattr(mm, n) for n, _ in MOTOR_FIELDS] + [mm.p_mech])
    _sheet(wb, "Identification", ["circuit", "schéma", "V [V]", "f [Hz]", "p [-]"]
           + [h for _, h in MOTOR_FIELDS] + ["p_mec [W]"], rows)

    # envelope
    e = s.envelope
    names, rows = _columns({"omega [rad/s]": e.omega, "T [N·m]": e.torque, "P [W]": e.power, "f [Hz]": e.f,
                            "V [V]": e.v, "g [-]": e.slip, "I1 [A]": e.i1, "T_bd [N·m]": e.torque_breakdown,
                            "zone [-]": e.zone(), "limite": e.binding})
    _sheet(wb, "Enveloppe", names, rows)

    # efficiency map, long format
    mp = s.emap
    tt, ww = np.meshgrid(mp.torque, mp.speed, indexing="ij")
    names, rows = _columns({"T [N·m]": tt, "omega [rad/s]": ww, "valide": mp.valid, "eta [-]": mp.eta,
                            "P_out [W]": mp.p_out, "P_in [W]": mp.p_in, "P_cu1 [W]": mp.p_cu1,
                            "P_cu2 [W]": mp.p_cu2, "P_fe [W]": mp.p_fe, "P_mec [W]": mp.p_mech,
                            "P_ond [W]": mp.p_inv, "f [Hz]": mp.f, "I1 [A]": mp.i1})
    _sheet(wb, "Rendement", names, rows)

    # cycle
    if s.drive_result is not None:
        res = s.drive_result
        names, rows = _columns({"t [s]": res.t, "v [m/s]": res.v, "a [m/s²]": res.a, "F [N]": res.force,
                                "omega [rad/s]": res.omega, "T [N·m]": res.torque, "P_arbre [W]": res.p_shaft,
                                "P_pertes [W]": res.p_losses, "P_batt [W]": res.p_battery,
                                "hors_enveloppe": res.outside})
        _sheet(wb, "Cycle", names, rows)
        sm = res.summary
        _sheet(wb, "Cycle_KPI", ["grandeur", "valeur", "unité"], [
            ["distance", sm.distance_m, "m"], ["durée", sm.duration_s, "s"], ["énergie batterie", sm.energy_j, "J"],
            ["énergie tirée", sm.energy_traction_j, "J"], ["énergie récupérée", sm.energy_regen_j, "J"],
            ["consommation", sm.wh_per_km, "Wh/km"], ["récupéré", sm.regen_percent, "%"],
            ["points hors enveloppe", sm.n_outside, "-"],
            ["rapport G", s.vehicle.gear_ratio, "-"], ["classe WLTC", s.sizing.wltc_class, "-"],
            ["rapport puissance/masse", s.sizing.pmr, "W/kg"]])

    # thermal
    if s.thermal is not None:
        th = s.thermal
        names, rows = _columns({"t [s]": th.t, "T_bobinage [K]": th.t_w, "T_carcasse [K]": th.t_s,
                                "P_bobinage [W]": np.append(th.p_w, np.nan),
                                "P_carcasse [W]": np.append(th.p_s, np.nan)})
        _sheet(wb, "Thermique", names, rows)

    # winding
    w = s.winding
    full = wd.Winding(z=w.z, poles=w.poles, m=w.m, y=w.tau)
    rows = [[nu, wd.distribution_factor(w, nu), wd.pitch_factor(full, nu), wd.winding_factor(full, nu),
             wd.pitch_factor(w, nu), wd.winding_factor(w, nu)] for nu in range(1, 26, 2)]
    _sheet(wb, "Bobinage", ["nu [-]", "kd [-]", f"kp y={w.tau} [-]", f"kw y={w.tau} [-]",
                            f"kp y={w.y} [-]", f"kw y={w.y} [-]"], rows)
    _sheet(wb, "Encoches", ["encoche [-]", "haut", "bas"],
           [[k + 1, *slot.labels()] for k, slot in enumerate(wd.slot_table(w))])

    # optimisation log
    if s.pareto is not None:
        front = {id(p) for p in s.pareto.front}
        rows = [[ev.design.gear_ratio, ev.design.boost, ev.design.margin, ev.design.k_n, ev.wh_per_km, ev.t_0_50,
                 ev.min_margin, ev.t_winding_max, ev.i_cycle_max, ev.feasible, id(ev) in front, ev.message]
                for ev in (s.pareto.baseline, *s.pareto.log)]
        rows[0][-1] = "base"
        _sheet(wb, "Optimisation", ["G [-]", "boost [V]", "marge [-]", "k_N [-]", "Wh/km [Wh/km]", "t_0_50 [s]",
                                    "marge_couple [-]", "T_bobinage_max [K]", "I_cycle_max [A]", "admissible",
                                    "front", "message"], rows)
    path = Path(path)
    wb.save(path)
    return path
