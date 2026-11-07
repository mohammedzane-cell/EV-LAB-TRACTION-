"""UI theme: applies the palette of evlab.palette to Qt (style.qss) and pyqtgraph. Presentation only.

The colours themselves live in src/evlab/palette.py (no Qt), shared with io/figures.py;
this module keeps the current theme, builds the stylesheet, styles the plots and
remembers the choice with QSettings. style.qss uses the palette roles as @tokens.
"""

from __future__ import annotations

import re
from pathlib import Path

from evlab import palette as _palette
from evlab.palette import (  # re-exported: the GUI and its tests use theme.<name>
    DARK,
    FONT_FAMILIES,
    LIGHT,
    PALETTES,
    SERIES,
    TEXT_PAIRS,
    THEMES,
    contrast,
)

THEME_LABELS = {LIGHT: "Thème clair", DARK: "Thème sombre"}
FONT_POINT_SIZE = 10
SETTINGS_ORG, SETTINGS_APP, SETTINGS_KEY = "ENP Alger", "EV-Traction Lab", "theme"
QSS = Path(__file__).with_name("style.qss")

_current = LIGHT


def palette(name: str | None = None) -> dict[str, str]:
    """Colours of a theme by role ("light" or "dark"; None: the current one)."""
    return _palette.palette(_current if name is None else name)


def current() -> str:
    """Name of the theme applied last ("light" by default)."""
    return _current


def color(role: str) -> str:
    """Colour of a role in the current theme, or of a data series (SERIES)."""
    return SERIES[role] if role in SERIES else palette()[role]


def stylesheet(name: str | None = None) -> str:
    """style.qss with every @role token replaced by its colour in the theme."""
    pal = palette(name)
    text = re.sub(r"/\*.*?\*/", "", QSS.read_text(encoding="utf-8"), flags=re.DOTALL)  # drop comments
    for role in sorted(pal, key=len, reverse=True):  # @primary_hover before @primary
        text = text.replace(f"@{role}", pal[role])
    text = text.replace("@font", ", ".join(f'"{f}"' for f in FONT_FAMILIES))
    leftover = sorted(set(re.findall(r"@\w+", text)))
    if leftover:
        raise ValueError(f"style.qss uses unknown theme roles: {leftover}")
    return text


def mpl_rc(name: str | None = None) -> dict:
    """matplotlib rcParams of a theme (None: the current one), from evlab.palette."""
    return _palette.mpl_rc(_current if name is None else name)


def pen(series: str, width: float = 2.0, dash: bool = False):
    """pyqtgraph pen of a data series (SERIES key) or palette role."""
    import pyqtgraph as pg
    from PySide6.QtCore import Qt

    kw = {"style": Qt.PenStyle.DashLine} if dash else {}
    return pg.mkPen(color(series), width=width, **kw)


def set_role(widget, role: str | None) -> None:
    """Give a widget a style role of style.qss (muted, error, success, note, warning, primary) and repolish."""
    widget.setProperty("role", role or "")
    st = widget.style()
    st.unpolish(widget)
    st.polish(widget)


def _style_plot(pw, pal: dict[str, str]) -> None:
    import pyqtgraph as pg

    pw.setBackground(pal["plot_bg"])
    item = pw.getPlotItem()
    for name in ("left", "bottom", "right", "top"):
        axis = item.getAxis(name)
        axis.setPen(pg.mkPen(pal["grid"]))
        axis.setTextPen(pg.mkPen(pal["plot_fg"]))
        if axis.label is not None:
            axis.label.setDefaultTextColor(pg.mkColor(pal["plot_fg"]))
    item.titleLabel.item.setDefaultTextColor(pg.mkColor(pal["plot_fg"]))
    if item.legend is not None:
        item.legend.setLabelTextColor(pal["plot_fg"])
        item.legend.setBrush(pg.mkBrush(pal["card"] + "E6"))
        item.legend.setPen(pg.mkPen(pal["border"]))


def apply(app, name: str = LIGHT) -> None:
    """Apply a theme to the application: font, style.qss, pyqtgraph defaults, existing plots."""
    global _current
    import pyqtgraph as pg
    from PySide6.QtGui import QFont

    if app is None:
        raise ValueError("theme.apply needs a QApplication (create it first)")
    pal = palette(name)
    _current = name
    font = QFont()
    font.setFamilies(list(FONT_FAMILIES))
    font.setPointSize(FONT_POINT_SIZE)
    app.setFont(font)
    app.setStyleSheet(stylesheet(name))
    pg.setConfigOptions(antialias=True, background=pal["plot_bg"], foreground=pal["plot_fg"])
    for w in app.allWidgets():
        if isinstance(w, pg.PlotWidget):
            _style_plot(w, pal)


def style_plot(pw) -> None:
    """Style one pyqtgraph PlotWidget with the current theme (axes, title, legend, background)."""
    _style_plot(pw, palette())


def _settings():
    from PySide6.QtCore import QSettings

    return QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, SETTINGS_ORG, SETTINGS_APP)


def saved() -> str:
    """Theme remembered by QSettings (light if none or unknown)."""
    name = _settings().value(SETTINGS_KEY, LIGHT)
    return name if name in THEMES else LIGHT


def save(name: str) -> None:
    """Remember the theme with QSettings."""
    palette(name)  # validates
    s = _settings()
    s.setValue(SETTINGS_KEY, name)
    s.sync()
