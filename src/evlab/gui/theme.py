"""UI theme: one palette per theme for Qt (style.qss), pyqtgraph and matplotlib. Presentation only.

PALETTES holds every colour of the application, by role, for the light and the dark
theme; SERIES holds the data-series colours, shared by both themes and by the PDF
figures, so a quantity keeps its colour everywhere. style.qss uses the roles as
@tokens. Qt is imported inside the functions only, so io/figures.py can read the
palette without importing Qt (the PDF always uses the light theme: it is printed).
Text roles are checked for a WCAG contrast >= 4.5:1 on their backgrounds (tests).
"""

from __future__ import annotations

import re
from pathlib import Path

LIGHT, DARK = "light", "dark"
THEMES = (LIGHT, DARK)
THEME_LABELS = {LIGHT: "Thème clair", DARK: "Thème sombre"}
FONT_FAMILIES = ("Segoe UI", "Inter")
FONT_POINT_SIZE = 10
SETTINGS_ORG, SETTINGS_APP, SETTINGS_KEY = "ENP Alger", "EV-Traction Lab", "theme"
QSS = Path(__file__).with_name("style.qss")

# data series: same colour in both themes and in the PDF (consistent meaning)
SERIES = {
    "blue": "#2F6FDB",
    "green": "#2E9E5B",
    "orange": "#E08A1E",
    "red": "#D64541",
    "light_blue": "#8DB3F0",
    "dark_green": "#1B5E35",
    "brown": "#8A5208",
    "grey": "#9AA3AF",
}

PALETTES: dict[str, dict[str, str]] = {
    LIGHT: {
        "bg": "#F5F7FA",
        "card": "#FFFFFF",
        "border": "#DDE2EA",
        "text": "#1F2733",
        "muted": "#5B6573",
        "primary": "#2F6FDB",
        "primary_hover": "#2559B5",
        "primary_pressed": "#1E4A99",
        "primary_disabled": "#A9C1EC",
        "on_primary": "#FFFFFF",
        "input": "#FFFFFF",
        "hover": "#EEF2F7",
        "tab": "#E6EBF2",
        "selection": "#D6E4FA",
        "demo_bg": "#FFF4D6",
        "demo_fg": "#7A4E00",
        "demo_border": "#E0A526",
        "alert_bg": "#FDECEC",
        "alert_fg": "#A8231B",
        "alert_border": "#D64541",
        "success": "#1C7235",
        "note": "#7F4B07",
        "info": "#2559B5",
        "plot_bg": "#FFFFFF",
        "plot_fg": "#3A4350",
        "grid": "#C9D0DA",
        "cell_text": "#1F2733",
    },
    DARK: {
        "bg": "#1E2128",
        "card": "#272B33",
        "border": "#3A404B",
        "text": "#E6E9EF",
        "muted": "#A7B0BD",
        "primary": "#2F6FDB",
        "primary_hover": "#2559B5",
        "primary_pressed": "#1E4A99",
        "primary_disabled": "#34486B",
        "on_primary": "#FFFFFF",
        "input": "#1E2128",
        "hover": "#323843",
        "tab": "#2E333C",
        "selection": "#2D4466",
        "demo_bg": "#3B3015",
        "demo_fg": "#F5C76B",
        "demo_border": "#C9952C",
        "alert_bg": "#3D2020",
        "alert_fg": "#FF9A90",
        "alert_border": "#D64541",
        "success": "#72D48E",
        "note": "#EBB46A",
        "info": "#8DB3F0",
        "plot_bg": "#272B33",
        "plot_fg": "#C9CFD8",
        "grid": "#4A515D",
        "cell_text": "#1F2733",  # winding table cells keep their pastel background
    },
}

# (text role, background role) pairs that must be readable (contrast >= 4.5:1)
TEXT_PAIRS = (
    ("text", "bg"), ("text", "card"), ("text", "input"), ("text", "tab"), ("text", "hover"),
    ("muted", "bg"), ("muted", "card"), ("on_primary", "primary"), ("on_primary", "primary_hover"),
    ("demo_fg", "demo_bg"), ("alert_fg", "alert_bg"), ("alert_fg", "card"), ("success", "card"),
    ("note", "card"), ("info", "card"), ("plot_fg", "plot_bg"), ("text", "selection"),
)

_current = LIGHT


def palette(name: str | None = None) -> dict[str, str]:
    """Colours of a theme by role ("light" or "dark"; None: the current one)."""
    name = _current if name is None else name
    if name not in PALETTES:
        raise ValueError(f"theme must be one of {THEMES}, got {name!r}")
    return PALETTES[name]


def current() -> str:
    """Name of the theme applied last ("light" by default)."""
    return _current


def color(role: str) -> str:
    """Colour of a role in the current theme, or of a data series (SERIES)."""
    return SERIES[role] if role in SERIES else palette()[role]


def _luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    rgb = [int(h[k:k + 2], 16) / 255.0 for k in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(fg: str, bg: str) -> float:
    """WCAG 2 contrast ratio between two #RRGGBB colours (1 to 21)."""
    a, b = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


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
    """matplotlib rcParams for a theme: colours from the palette, series cycle from SERIES."""
    from cycler import cycler

    pal = palette(name)
    return {
        "figure.facecolor": pal["plot_bg"], "axes.facecolor": pal["plot_bg"],
        "savefig.facecolor": pal["plot_bg"], "axes.edgecolor": pal["grid"],
        "axes.labelcolor": pal["plot_fg"], "text.color": pal["plot_fg"],
        "xtick.color": pal["plot_fg"], "ytick.color": pal["plot_fg"], "grid.color": pal["grid"],
        "legend.facecolor": pal["card"], "legend.edgecolor": pal["border"], "legend.labelcolor": pal["plot_fg"],
        "font.family": "sans-serif", "font.sans-serif": [*FONT_FAMILIES, "DejaVu Sans"],
        "axes.prop_cycle": cycler(color=[SERIES[k] for k in ("blue", "green", "orange", "red", "brown")]),
    }


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
