"""gui/theme.py + style.qss: both themes start, chips stay amber, text contrast >= 4.5:1, one palette."""

import pyqtgraph as pg
import pytest
from PySide6.QtWidgets import QApplication

from evlab.gui import theme
from evlab.gui.main_window import MainWindow

TIMEOUT = 30_000


@pytest.fixture
def light_after():
    yield
    theme.apply(QApplication.instance(), theme.LIGHT)  # the other GUI tests expect the default theme


# --- palette ------------------------------------------------------------------------------

@pytest.mark.parametrize("name", theme.THEMES)
def test_text_contrast_at_least_4_5(name):
    pal = theme.palette(name)
    for fg, bg in theme.TEXT_PAIRS:
        assert theme.contrast(pal[fg], pal[bg]) >= 4.5, (name, fg, bg)


def test_contrast_formula():
    assert theme.contrast("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert theme.contrast("#777777", "#777777") == pytest.approx(1.0)


def test_requested_palette_values():
    light, dark = theme.palette("light"), theme.palette("dark")
    assert light["bg"] == "#F5F7FA" and light["card"] == "#FFFFFF" and light["primary"] == "#2F6FDB"
    assert dark["bg"] == "#1E2128"
    assert set(light) == set(dark)  # every role exists in both themes
    with pytest.raises(ValueError):
        theme.palette("pink")


@pytest.mark.parametrize("name", theme.THEMES)
def test_stylesheet_has_every_token_replaced(name):
    qss = theme.stylesheet(name)
    assert "@" not in qss
    pal = theme.palette(name)
    for role in ("bg", "card", "primary", "demo_bg", "demo_fg", "alert_fg"):
        assert pal[role] in qss
    assert "border-radius: 8px" in qss and "border-radius: 6px" in qss and "border-radius: 13px" in qss
    assert '"Segoe UI", "Inter"' in qss


@pytest.mark.parametrize("name", theme.THEMES)
def test_matplotlib_rc_from_the_same_palette(name):
    rc = theme.mpl_rc(name)
    pal = theme.palette(name)
    assert rc["axes.facecolor"] == pal["plot_bg"] and rc["text.color"] == pal["plot_fg"]
    assert rc["axes.prop_cycle"].by_key()["color"][0] == theme.SERIES["blue"]


def test_pdf_figures_use_the_light_palette_whatever_the_gui_theme(qapp, light_after):
    import sys

    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    from fixtures.snapshot import demo_snapshot

    from evlab.io import figures

    theme.apply(QApplication.instance(), theme.DARK)
    s = demo_snapshot()
    fig = figures.envelope_and_map(s.motor, s.envelope, s.emap)
    assert fig.get_facecolor()[:3] == pytest.approx((1.0, 1.0, 1.0))
    line = fig.axes[0].get_lines()[0]
    assert line.get_color() == theme.SERIES["blue"]


# --- the application starts with each theme -------------------------------------------------

def _pixel(widget, x, y):
    return widget.grab().toImage().pixelColor(x, y).name().upper()


@pytest.mark.parametrize("name", theme.THEMES)
def test_app_starts_with_each_theme(qtbot, name, light_after):
    w = MainWindow(theme_name=name)
    qtbot.addWidget(w)
    w.show()
    app = QApplication.instance()
    pal = theme.palette(name)
    assert theme.current() == name
    assert app.styleSheet() == theme.stylesheet(name)
    assert app.font().pointSize() == theme.FONT_POINT_SIZE
    assert list(app.font().families())[:2] == list(theme.FONT_FAMILIES)
    assert w.theme_actions[name].isChecked()
    qtbot.waitUntil(lambda: w.tabs.widget(1).envelope is not None, timeout=TIMEOUT)
    w.tabs.setCurrentIndex(1)
    env_tab = w.tabs.widget(1)
    qtbot.wait(200)
    # plots: background from the palette
    pw = env_tab.plot_torque
    assert pw.backgroundBrush().color().name().upper() == pal["plot_bg"]
    # primary button and démo chip get their roles, the chip is amber and visible
    assert env_tab.btn_compute.property("role") == "primary"
    chip = env_tab.chip_demo
    assert chip.property("chip") == "demo" and chip.isVisibleTo(env_tab)
    assert _pixel(chip, 6, chip.height() // 2) == pal["demo_bg"]
    assert _pixel(env_tab.btn_compute, 4, env_tab.btn_compute.height() // 2) == pal["primary"]


def test_theme_menu_switches_and_is_remembered(qtbot, light_after):
    w = MainWindow(theme_name="light")
    qtbot.addWidget(w)
    w.show()
    w.theme_actions["dark"].trigger()
    assert theme.current() == "dark" and theme.saved() == "dark"
    assert QApplication.instance().styleSheet() == theme.stylesheet("dark")
    for pw in w.findChildren(pg.PlotWidget):
        assert pw.backgroundBrush().color().name().upper() == theme.palette("dark")["plot_bg"]
    w2 = MainWindow()  # no theme given: the remembered one
    qtbot.addWidget(w2)
    assert theme.current() == "dark" and w2.theme_actions["dark"].isChecked()
    w2.set_theme("light")
    assert theme.saved() == "light"


def test_saved_theme_defaults_to_light():
    assert theme.saved() == "light"
    with pytest.raises(ValueError):
        theme.save("pink")
