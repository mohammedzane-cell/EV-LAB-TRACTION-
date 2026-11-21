"""Tab 2 shows the characteristic points and sensitivities of the session motor exactly as core computes them."""

from evlab.core import characteristics as charac
from evlab.core.session import Session
from evlab.gui.format import fr, fr_fixed
from evlab.gui.tab_envelope import SENS_COLS, SENS_ROWS, EnvelopeTab


def test_characteristics_and_sensitivities_come_from_core(qtbot):
    session = Session()
    tab = EnvelopeTab(session)
    qtbot.addWidget(tab)
    c = charac.characteristics(session.motor)
    s = charac.sensitivity(session.motor)
    assert tab.char_labels["t_max"].text() == f"{fr(c.breakdown_torque)} N·m"
    assert tab.char_labels["t_start"].text() == f"{fr(c.start_torque)} N·m"
    assert tab.char_labels["g_c"].text() == fr(c.breakdown_slip)
    for r, (out, _) in enumerate(SENS_ROWS):
        for col, (par, _) in enumerate(SENS_COLS):
            v = s[out][par]
            v = 0.0 if abs(v) < 0.005 else v
            assert tab.sens_table.item(r, col).text() == fr_fixed(v, 2).replace("-", "−")
    # TD5 Ex 1 (R1 = 0): g_c ∝ R'2/X, so the displayed sensitivities are +1,00 and −1,00
    assert tab.sens_table.item(1, 1).text() == "1,00" and tab.sens_table.item(1, 2).text() == "−1,00"
