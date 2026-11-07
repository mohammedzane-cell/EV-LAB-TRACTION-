"""io.excel: the workbook reopens with openpyxl and its values equal the core results."""

import math

import numpy as np
import pytest
from openpyxl import load_workbook

from evlab.core import winding as wd
from evlab.io.excel import build_workbook
from fixtures.snapshot import demo_snapshot


@pytest.fixture(scope="module")
def wb(tmp_path_factory):
    path = tmp_path_factory.mktemp("excel") / "resultats.xlsx"
    build_workbook(demo_snapshot(), path)
    return load_workbook(path, read_only=True)


def _col(ws, header):
    rows = list(ws.iter_rows(values_only=True))
    k = rows[0].index(header)
    return [r[k] for r in rows[1:]]


REL = 1e-15  # openpyxl writes 16 significant digits (Excel keeps 15)


def _same(xl, arr):
    arr = np.asarray(arr, dtype=float).ravel()
    assert len(xl) == arr.size
    for a, b in zip(xl, arr):
        if math.isfinite(b):
            assert a == pytest.approx(b, rel=REL, abs=0.0)
        else:
            assert a is None


def test_one_sheet_per_module(wb):
    assert wb.sheetnames == ["Lisez-moi", "Identification", "Enveloppe", "Rendement", "Cycle", "Cycle_KPI",
                             "Thermique", "Bobinage", "Encoches", "Optimisation"]
    for name in wb.sheetnames[1:]:
        header = next(wb[name].iter_rows(values_only=True))
        assert all(isinstance(h, str) for h in header)
    assert "[rad/s]" in "".join(next(wb["Enveloppe"].iter_rows(values_only=True)))


def test_envelope_and_map_values(wb):
    s = demo_snapshot()
    ws = wb["Enveloppe"]
    _same(_col(ws, "omega [rad/s]"), s.envelope.omega)
    _same(_col(ws, "T [N·m]"), s.envelope.torque)
    _same(_col(ws, "P [W]"), s.envelope.power)
    assert _col(ws, "limite") == list(s.envelope.binding)
    ws = wb["Rendement"]
    _same(_col(ws, "eta [-]"), s.emap.eta)
    _same(_col(ws, "P_cu1 [W]"), s.emap.p_cu1)
    tt, _ = np.meshgrid(s.emap.torque, s.emap.speed, indexing="ij")
    _same(_col(ws, "T [N·m]"), tt)


def test_cycle_thermal_winding_values(wb):
    s = demo_snapshot()
    _same(_col(wb["Cycle"], "P_batt [W]"), s.drive_result.p_battery)
    _same(_col(wb["Cycle"], "omega [rad/s]"), s.drive_result.omega)
    kpi = {r[0]: r[1] for r in list(wb["Cycle_KPI"].iter_rows(values_only=True))[1:]}
    assert kpi["consommation"] == pytest.approx(s.drive_result.summary.wh_per_km, rel=REL)
    assert kpi["classe WLTC"] == s.sizing.wltc_class
    _same(_col(wb["Thermique"], "T_bobinage [K]"), s.thermal.t_w)
    kw = _col(wb["Bobinage"], "kw y=7 [-]")
    assert kw[:4] == pytest.approx([wd.winding_factor(s.winding, nu) for nu in (1, 3, 5, 7)], rel=REL)
    assert _col(wb["Encoches"], "bas")[1] == wd.slot_table(s.winding)[1].labels()[1]


def test_identification_and_optimisation(wb):
    s = demo_snapshot()
    rows = list(wb["Identification"].iter_rows(values_only=True))
    assert rows[1][5:10] == pytest.approx((s.motor.r1, s.motor.r_fe, s.motor.x_m, s.motor.x_leak, s.motor.r2p),
                                          rel=REL)
    fit = next(r for r in rows if r[0] == "fit")
    assert fit[9] == pytest.approx(s.identification.fit.motor.r2p, rel=REL)
    opt = list(wb["Optimisation"].iter_rows(values_only=True))
    assert opt[1][-1] == "base" and opt[1][4] == pytest.approx(s.pareto.baseline.wh_per_km, rel=REL)
    assert len(opt) == 1 + 1 + len(s.pareto.log)
    head = opt[0]
    front_col, flux_col = head.index("front"), head.index("E/f_max [En/fn]")
    assert sum(1 for r in opt[2:] if r[front_col]) == len(s.pareto.front)
    assert opt[1][flux_col] == pytest.approx(s.pareto.baseline.flux_max, rel=REL)


def test_readme_lists_demo_values(wb):
    rows = list(wb["Lisez-moi"].iter_rows(values_only=True))
    demo = next(r for r in rows if r[0] == "Valeurs démo :")
    assert "réseau thermique" in demo[1]
