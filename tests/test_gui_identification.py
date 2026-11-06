"""Tab 1 · Identification (pytest-qt, offscreen): demo files, the three methods, Session, errors."""

from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from evlab.core import circuit
from evlab.core import identification as ident
from evlab.gui.format import fr, fr_pct
from evlab.gui.main_window import MainWindow
from evlab.gui.tab_identification import COLUMNS, VALUE_ROLE
from evlab.io.loaders import load_bench_tests, load_load_points, reference_motor

DATA = Path(__file__).resolve().parents[1] / "data"
BENCH = DATA / "bench_tests_demo.csv"
LOAD = DATA / "load_points_demo.csv"
TIMEOUT = 30_000  # ms


@pytest.fixture
def win(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.show()
    return w


@pytest.fixture
def tab(win):
    t = win.tabs.widget(0)
    assert t.title == "1 · Identification"
    return t


def _expected(tab, method):
    """Same inputs as the tab, straight through the core."""
    bench = load_bench_tests(BENCH)
    rec = ident.TestRecords(
        dc=ident.DcTest.from_resistance(tab.spin_r1.value(), tab.spin_t_r1.value() + 273.15),
        t_hot_k=bench.winding_temperature_k, no_load=bench.no_load, locked=bench.locked,
        pole_pairs=2, v_rated=230.0, f_rated=50.0, p_mech=None,
    )
    return ident.compare_methods(rec, method, points=load_load_points(LOAD).points, layout="tp3",
                                 reference=reference_motor(bench.meta), is_demo=True,
                                 source="Identification TP3")


def _run(qtbot, tab, method):
    tab.radios[method].setChecked(True)
    with qtbot.waitSignal(tab.identification_done, timeout=TIMEOUT) as blocker:
        qtbot.mouseClick(tab.btn_identify, Qt.MouseButton.LeftButton)
        assert not tab.btn_identify.isEnabled()  # busy: the worker runs off the GUI thread
    assert tab.btn_identify.isEnabled()
    return blocker.args[0]


def test_layout(tab):
    assert tab.findChildren(type(tab.spin_v))  # spin boxes exist
    assert tab.layout().itemAt(0).widget().width() == 300
    titles = [g.title() for g in tab.findChildren(__import__("PySide6.QtWidgets").QtWidgets.QGroupBox)]
    assert titles == ["Machine", "Essais (CSV)", "Méthode"]
    assert tab.btn_identify.text() == "Identifier"
    assert tab.btn_pdf.text() == "Exporter PDF" and tab.btn_pdf.isEnabled()  # wired to Fichier → Exporter PDF
    assert [tab.combo_layout.itemText(i) for i in range(2)] == ["TP3 (R1 en tête)", "Bornes"]
    assert tab.combo_layout.currentData() == "tp3"
    assert [rb.text() for rb in tab.radios.values()] == ["Formules classiques", "Optimisation (scipy)",
                                                         "Comparer les deux"]
    assert tab.table.rowCount() == 3 and tab.table.columnCount() == 5
    assert [tab.table.horizontalHeaderItem(c).text() for c in range(5)] == \
        ["Méthode", "Rf (Ω)", "Xm (Ω)", "X fuites (Ω)", "R'2 (Ω)"]


def test_status_bar_shows_platform(win):
    texts = [w.text() for w in win.statusBar().findChildren(__import__("PySide6.QtWidgets").QtWidgets.QLabel)]
    assert "Python 3 · PySide6" in texts


def test_loading_demo_files_fills_machine_and_chip(tab):
    assert not tab.chip_demo.isVisibleTo(tab)
    assert tab.load_bench_file(BENCH) and tab.load_points_file(LOAD)
    bench = load_bench_tests(BENCH)
    assert tab.spin_r1.value() == pytest.approx(ident.r1_from_dc(bench.dc), abs=5e-5)
    assert tab.spin_t_r1.value() == pytest.approx(20.0)
    assert tab.spin_v.value() == 230.0 and tab.spin_p.value() == 2
    assert tab.lbl_speed.text() == "1350 tr/min"  # nameplate, read from the file
    assert "chargé (démo)" in tab.lbl_bench.text() and "8 à vide" in tab.lbl_bench.text()
    assert "12 points" in tab.lbl_points.text()
    assert tab.chip_demo.isVisibleTo(tab)
    assert "démo" in tab.lbl_table_note.text()
    # reference row is filled from the file before any identification
    assert tab.table.item(0, 1).data(VALUE_ROLE) == 230.0


def test_previews(tab):
    tab.load_bench_file(BENCH)
    tab.load_points_file(LOAD)
    dlg = tab.preview_bench()
    assert dlg.table.rowCount() == 1 + 8 + 1 and dlg.table.item(0, 0).text() == "dc"
    dlg.close()
    dlg = tab.preview_points()
    assert dlg.table.rowCount() == 12 and "," in dlg.table.item(0, 1).text()
    dlg.close()


@pytest.mark.parametrize("method", ["classical", "fit", "both"])
def test_identify_each_method(qtbot, win, tab, method):
    tab.load_bench_file(BENCH)
    tab.load_points_file(LOAD)
    result = _run(qtbot, tab, method)
    expected = _expected(tab, method)
    assert result.shown == expected.shown
    assert tab.table.rowCount() == 3
    ref = expected.reference
    for c, (name, _) in enumerate(COLUMNS, start=1):
        assert tab.table.item(0, c).data(VALUE_ROLE) == getattr(ref, name)
        for r, row in ((1, "classical"), (2, "fit")):
            item = tab.table.item(r, c)
            if row in expected.shown:
                value = getattr(expected.motor(row), name)
                assert item.data(VALUE_ROLE) == value  # the number comes from the core
                assert item.text() == f"{fr(value)} ({fr_pct(expected.errors[row][name])})"
                assert "," in item.text() or "." not in item.text()  # decimal comma
            else:
                assert item.text() == "—"
    # Session holds the identified motor, for tabs 2 to 7
    assert win.session.motor == expected.published
    assert win.session.motor.is_demo
    assert win.motor_text == f"Moteur : {expected.published.source} (démo)"
    assert "moteur publié" in win.statusBar().currentMessage()


def test_fit_tooltips_show_confidence_interval(qtbot, tab):
    tab.load_bench_file(BENCH)
    tab.load_points_file(LOAD)
    result = _run(qtbot, tab, "fit")
    lo, hi = result.fit.ci95["r2p"]
    assert tab.table.item(2, 4).toolTip() == f"Intervalle de confiance à 95 % : [{fr(lo, 4)} ; {fr(hi, 4)}] Ω"
    assert "essai à vide" in tab.table.item(2, 1).toolTip()


def test_plots_use_core_curves(qtbot, tab):
    tab.load_bench_file(BENCH)
    tab.load_points_file(LOAD)
    result = _run(qtbot, tab, "both")
    curves = tab.plot_torque.getPlotItem().listDataItems()
    names = [c.name() for c in curves]
    assert "modèle (formules classiques)" in names and "modèle (optimisation)" in names
    assert "points d'essai (démo)" in names
    fit_curve = curves[names.index("modèle (optimisation)")]
    x, y = fit_curve.getData()
    assert y[200] == pytest.approx(circuit.torque(result.fit.motor, x[200]))
    pts = curves[names.index("points d'essai (démo)")].getData()
    assert len(pts[0]) == 12


def test_identifiability_warning_in_status_bar(qtbot, win, tab, monkeypatch):
    real = ident.compare_methods

    def flagged(*a, **kw):
        res = real(*a, **kw)
        fit = ident.LoadFitResult(**{**res.fit.__dict__, "high_correlation": (("x_m", "x_leak", 0.97),)})
        return ident.MethodComparison(**{**res.__dict__, "fit": fit})

    monkeypatch.setattr(ident, "compare_methods", flagged)
    tab.load_bench_file(BENCH)
    tab.load_points_file(LOAD)
    _run(qtbot, tab, "fit")
    msg = win.statusBar().currentMessage()
    assert "paramètres mal séparés" in msg and "Xm–X ρ = 0,97" in msg


def test_errors_are_reported_in_french(qtbot, win, tab, tmp_path):
    bad = tmp_path / "essais.csv"
    bad.write_text("essai,U [kV],I [A],P [W],f [Hz],T [°C]\nvide,0.4,5,700,50,75\n", encoding="utf-8")
    assert not tab.load_bench_file(bad)
    assert "unité incorrecte" in tab.lbl_bench.text()
    assert tab.bench is None
    with qtbot.waitSignal(tab.identification_failed, timeout=TIMEOUT):
        assert not tab.identify()
    assert "chargez d'abord le fichier d'essais" in win.statusBar().currentMessage()
    tab.load_bench_file(BENCH)
    tab.radios["fit"].setChecked(True)
    assert not tab.identify()
    assert "points en charge" in win.statusBar().currentMessage()


def test_core_failure_is_reported(qtbot, win, tab):
    tab.load_bench_file(BENCH)
    tab.radios["classical"].setChecked(True)
    tab.spin_v.setValue(400.0)  # no no-load point near 400 V phase
    with qtbot.waitSignal(tab.identification_failed, timeout=TIMEOUT) as blocker:
        tab.identify()
    assert "10 %" in blocker.args[0]
    assert win.session.motor.source == "TD5 Ex 1"  # nothing published


def test_terminals_layout_is_used(qtbot, win, tab):
    tab.load_bench_file(BENCH)
    tab.load_points_file(LOAD)
    tab.combo_layout.setCurrentIndex(1)
    _run(qtbot, tab, "classical")
    assert win.session.motor.layout == "terminals"


def test_worker_failure_is_reported(qtbot, win, tab, monkeypatch):
    def boom(*a, **kw):
        raise ValueError("p_mec extrapolées négatives")

    monkeypatch.setattr(ident, "compare_methods", boom)
    tab.load_bench_file(BENCH)
    tab.radios["classical"].setChecked(True)
    with qtbot.waitSignal(tab.identification_failed, timeout=TIMEOUT) as blocker:
        assert tab.identify()  # accepted: the error comes from the worker thread
    assert blocker.args[0] == "Échec de l'identification : p_mec extrapolées négatives"
    assert tab.btn_identify.isEnabled() and not win.busy_bar.isVisible()


def test_fields_use_decimal_comma(tab):
    tab.load_bench_file(BENCH)
    assert "," in tab.spin_r1.text() and "." not in tab.spin_r1.text()
