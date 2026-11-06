"""Tab 7 · Optimisation (pytest-qt, offscreen): small budget, Pareto plot, selection, load into tabs."""

import pytest

from evlab.core import optimise as op
from evlab.gui.format import fr
from evlab.gui.main_window import MainWindow

TIMEOUT = 120_000


@pytest.fixture
def win(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitUntil(lambda: w.tabs.widget(1).envelope is not None, timeout=TIMEOUT)
    veh = w.tabs.widget(3)
    with qtbot.waitSignal(veh.simulation_done, timeout=TIMEOUT):
        w.tabs.setCurrentIndex(3)
    return w


@pytest.fixture
def tab(win):
    t = win.tabs.widget(6)
    assert t.title == "7 · Optimisation"
    win.tabs.setCurrentIndex(6)
    t.spin_points.setValue(2)
    t.spin_pop.setValue(3)
    t.spin_budget.setValue(36)  # 3·4 per generation → 2 generations + the initial population
    t.spin_workers.setValue(1)
    return t


def _run(qtbot, tab):
    with qtbot.waitSignal(tab.pareto_done, timeout=TIMEOUT) as b:
        assert tab.run()
        assert not tab.btn_run.isEnabled() and tab.btn_cancel.isEnabled()
    return b.args[0]


def test_problem_comes_from_the_tabs(win):
    p = win.optimisation_problem()
    assert p.motor == win.session.motor
    assert p.drive == win.tabs.widget(1).settings()
    assert p.vehicle.gear_ratio == pytest.approx(win.tabs.widget(3).spin_g.value())
    assert p.cycle is win.tabs.widget(3).result[2]
    assert p.insulation_class == "F" and p.n_thermal_cycles == 10


def test_run_plot_and_tables(qtbot, tab, win):
    res = _run(qtbot, tab)
    assert res.front and res.baseline.feasible
    assert len(res.log) == 2 * 3 * 4 * 3  # points × popsize·n_free × (maxiter + 1)
    x, y = tab.front_item.getData()
    assert list(x) == [e.t_0_50 for e in res.front] and list(y) == [e.wh_per_km for e in res.front]
    sel = tab.selected
    assert sel is min(res.front, key=lambda e: e.wh_per_km)
    assert tab.kpi_table.item(0, 1).text() == fr(res.baseline.wh_per_km)
    assert tab.kpi_table.item(0, 2).text() == fr(sel.wh_per_km)
    g = op.gains(res.baseline, sel)["wh_per_km"]
    assert tab.kpi_table.item(0, 3).text() == f"{g:+.1f} %".replace(".", ",")
    assert tab.progress.value() == len(res.log)
    dt = sel.t_winding_max - res.baseline.t_winding_max
    assert tab.kpi_table.item(2, 3).text() == f"{dt:.1f} K".replace(".", ",").replace("-", "−")


def test_click_selects_and_loads_design(qtbot, tab, win):
    res = _run(qtbot, tab)
    pts = tab.front_item.points()
    tab._clicked(tab.front_item, [pts[-1]])
    chosen = res.front[-1]
    assert tab.selected is chosen
    with qtbot.waitSignal(win.tabs.widget(1).envelope_done, timeout=TIMEOUT):
        tab.btn_load.click()
    d = chosen.design
    assert win.session.motor == op.rewound(tab.problem.motor, d.k_n)
    assert win.tabs.widget(1).spin_boost.value() == pytest.approx(d.boost, abs=0.05)
    assert win.tabs.widget(1).spin_margin.value() == pytest.approx(100 * d.margin, abs=0.5)
    assert win.tabs.widget(3).spin_g.value() == pytest.approx(d.gear_ratio, abs=5e-4)


def test_cancel(qtbot, tab):
    tab.spin_points.setValue(4)
    tab.spin_budget.setValue(372)  # 30 generations
    with qtbot.waitSignal(tab.pareto_done, timeout=TIMEOUT) as b:
        tab.run()
        tab.cancel()
    assert b.args[0].message == "cancelled"
    assert tab.btn_run.isEnabled()


def test_all_fixed_is_refused(qtbot, tab):
    for lo, hi, _ in tab.bound_spins.values():
        hi.setValue(lo.value())
    with qtbot.waitSignal(tab.pareto_failed, timeout=TIMEOUT) as b:
        assert not tab.run()
    assert "fixées" in b.args[0]


def test_needs_a_cycle(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    t = w.tabs.widget(6)
    with qtbot.waitSignal(t.pareto_failed, timeout=TIMEOUT) as b:
        t.run()
    assert "onglet 4" in b.args[0]


def test_budget_is_fixed_per_pareto_point(tab):
    tab.spin_points.setValue(6)
    tab.spin_pop.setValue(15)
    tab.spin_budget.setValue(op.BUDGET)
    assert tab.expected_evaluations() == 6 * 1500
    assert "4 variable(s) libre(s) → 24 générations, 1500 évaluations par point" in tab.lbl_budget.text()
    lo, hi, _ = tab.bound_spins["k_n"]
    hi.setValue(lo.value())  # k_N fixed: still ≈ 1500 per point
    assert "3 variable(s) libre(s) → 32 générations, 1485 évaluations par point" in tab.lbl_budget.text()
