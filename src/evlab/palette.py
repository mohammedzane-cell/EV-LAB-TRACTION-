"""The colour palette of EV-LAB: one dict per theme, shared data-series colours, font stacks. No Qt.

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
DEFAULT_THEME = DARK  # « Studio graphite »; the PDF figures stay light (printed)
# fonts, first available wins: Windows 11 → Segoe UI Variable, Windows 10 → Segoe UI, Linux → Inter
FONT_FAMILIES = ("Segoe UI Variable Text", "Segoe UI", "Inter")
DISPLAY_FAMILIES = ("Segoe UI Variable Display", "Segoe UI Semibold", "Inter Display", "Inter")
MONO_FAMILIES = ("Cascadia Mono", "JetBrains Mono", "Consolas", "DejaVu Sans Mono")

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
    # « Studio clair »: the same identity on a light workspace (bright rooms, projection)
    LIGHT: {
        "bg": "#EDF0F4",  # workspace base
        "surface": "#E4E9EF",  # sidebar and header
        "card": "#FFFFFF",  # result panels
        "border": "#CDD5DF",
        "divider": "#E1E6EC",
        "text": "#111923",
        "muted": "#556274",
        "primary": "#0A6E7B",  # electric cyan, deepened for contrast on light surfaces
        "primary_hover": "#085C67",
        "primary_pressed": "#064C55",
        "primary_disabled": "#9FC6CC",
        "on_primary": "#FFFFFF",
        "accent_soft": "#D9F1F4",
        "input": "#FFFFFF",
        "hover": "#E2E8EF",
        "tab": "#E8ECF1",  # secondary surface: table headers, navigation hover
        "selection": "#D3EEF2",
        "demo_bg": "#FFF3D6",
        "demo_fg": "#7A4E00",
        "demo_border": "#D9A23A",
        "alert_bg": "#FDECEC",
        "alert_fg": "#A8231B",
        "alert_border": "#D64541",
        "success": "#17703A",
        "note": "#7F4B07",
        "info": "#1F5FBF",
        "plot_bg": "#FFFFFF",
        "plot_fg": "#384352",
        "grid": "#DDE3EA",
        "cell_text": "#1F2733",
        "disabled_text": "#9AA3AF",  # greyed-out controls (WCAG exempts inactive UI from 4.5:1)
        "disabled_bg": "#E9EDF2",
    },
    # « Studio graphite » (default): deep graphite / midnight navy foundation, one cyan accent
    DARK: {
        "bg": "#0E141B",
        "surface": "#0A0F15",
        "card": "#141C26",
        "border": "#243142",
        "divider": "#1B2531",
        "text": "#E3E9F1",
        "muted": "#8F9DB0",
        "primary": "#22C3D6",
        "primary_hover": "#4FD3E2",
        "primary_pressed": "#149BAD",
        "primary_disabled": "#1C4A52",
        "on_primary": "#031317",
        "accent_soft": "#0F3640",
        "input": "#0F161E",
        "hover": "#1C2733",
        "tab": "#18212C",
        "selection": "#103844",
        "demo_bg": "#2B2212",
        "demo_fg": "#F0C36A",
        "demo_border": "#8F6A22",
        "alert_bg": "#33191B",
        "alert_fg": "#FF8F87",
        "alert_border": "#E5534B",
        "success": "#48D597",
        "note": "#E9B15F",
        "info": "#7AB6FF",
        "plot_bg": "#0F161E",
        "plot_fg": "#A9B6C6",
        "grid": "#1F2A37",
        "cell_text": "#1F2733",  # winding table cells keep their pastel background
        "disabled_text": "#4F5D6E",
        "disabled_bg": "#111820",
    },
}

# (text role, background role) pairs that must be readable (contrast >= 4.5:1)
TEXT_PAIRS = (
    ("text", "bg"), ("text", "card"), ("text", "input"), ("text", "tab"), ("text", "hover"),
    ("muted", "bg"), ("muted", "card"), ("on_primary", "primary"), ("on_primary", "primary_hover"),
    ("demo_fg", "demo_bg"), ("alert_fg", "alert_bg"), ("alert_fg", "card"), ("success", "card"),
    ("note", "card"), ("info", "card"), ("plot_fg", "plot_bg"), ("text", "selection"),
    ("text", "surface"), ("muted", "surface"), ("primary", "surface"), ("primary", "card"),
    ("text", "accent_soft"), ("muted", "tab"),
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
