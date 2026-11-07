"""The colour palette of EV-Traction Lab: one dict per theme, shared data-series colours. No Qt.

PALETTES holds every colour by role for the light and the dark theme; SERIES holds the
data-series colours, the same in both themes and in the PDF figures, so a quantity keeps
its colour everywhere. Used by gui/theme.py (Qt stylesheet, pyqtgraph, the tab 3 map) and
by io/figures.py (PDF figures, always in the light theme: the report is printed).
Text roles are checked for a WCAG contrast >= 4.5:1 on their backgrounds (TEXT_PAIRS, tests).
Plain data and matplotlib rcParams only: importing this module never imports Qt.
"""

from __future__ import annotations

LIGHT, DARK = "light", "dark"
THEMES = (LIGHT, DARK)
FONT_FAMILIES = ("Segoe UI", "Inter")

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
        "disabled_text": "#9AA3AF",  # greyed-out controls (WCAG exempts inactive UI from 4.5:1)
        "disabled_bg": "#ECEFF3",
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
        "disabled_text": "#6B7380",
        "disabled_bg": "#23262D",
    },
}

# (text role, background role) pairs that must be readable (contrast >= 4.5:1)
TEXT_PAIRS = (
    ("text", "bg"), ("text", "card"), ("text", "input"), ("text", "tab"), ("text", "hover"),
    ("muted", "bg"), ("muted", "card"), ("on_primary", "primary"), ("on_primary", "primary_hover"),
    ("demo_fg", "demo_bg"), ("alert_fg", "alert_bg"), ("alert_fg", "card"), ("success", "card"),
    ("note", "card"), ("info", "card"), ("plot_fg", "plot_bg"), ("text", "selection"),
)


def palette(name: str) -> dict[str, str]:
    """Colours of a theme by role ("light" or "dark")."""
    if name not in PALETTES:
        raise ValueError(f"theme must be one of {THEMES}, got {name!r}")
    return PALETTES[name]


def _luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    rgb = [int(h[k:k + 2], 16) / 255.0 for k in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(fg: str, bg: str) -> float:
    """WCAG 2 contrast ratio between two #RRGGBB colours (1 to 21)."""
    a, b = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def mpl_rc(name: str) -> dict:
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
