"""EV-LAB icon set: 24 × 24 line glyphs drawn for this product, rendered in a theme colour. Presentation only.

Each glyph is SVG drawing data (strokes, no fill) on a 24 × 24 grid, 1,6 px lines with round
ends, so the eight workspaces read as one family. `icon(name, colour)` renders it with
QtSvg in any colour (the nav uses the muted colour, the active workspace the accent);
`logo()` is the EV-LAB mark: a stator ring with four poles and a rotor, in the accent colour.
"""

from __future__ import annotations

from functools import lru_cache

GLYPHS: dict[str, str] = {
    # 1 · equivalent circuit: supply, series impedance, magnetising coil to the return line
    "identification": '<path d="M3 7h3l1-2 2 4 2-4 2 4 1-2h7"/><path d="M14 7v3"/>'
                      '<path d="M14 10c2 0 2 2 0 2c2 0 2 2 0 2c2 0 2 2 0 2"/><path d="M14 16v1"/>'
                      '<path d="M3 17h18"/><circle cx="3" cy="7" r="0.6"/><circle cx="3" cy="17" r="0.6"/>',
    # 2 · torque–speed envelope: constant torque, then the hyperbola of constant power
    "envelope": '<path d="M4 3v17h17"/><path d="M5 8h6c3 0 4 2 5.5 4.5S19 17 20.5 17.5"/>'
                '<path d="M11 8v11" stroke-dasharray="1.5 2"/>',
    # 3 · efficiency map: iso-efficiency contours inside the envelope
    "efficiency": '<path d="M4 3v17h17"/><path d="M5 7h7c4 0 6 4 8 9"/>'
                  '<path d="M9 17c0-4 2-6 5-6s4 2 4 6"/><path d="M12 17c0-2 1-3 2-3s2 1 2 3"/>',
    # 4 · vehicle: side view on its wheels
    "vehicle": '<path d="M3 15v-3l3-4h9l4 4h2v3h-2"/><path d="M8 15h7"/><path d="M3 15h1"/>'
               '<circle cx="6" cy="16" r="2"/><circle cx="17" cy="16" r="2"/><path d="M7 12h12"/>',
    # 5 · thermal: thermometer with its scale
    "thermal": '<path d="M10 4a2 2 0 0 1 4 0v9.5a4 4 0 1 1-4 0z"/><path d="M12 9v7"/>'
               '<path d="M17 6h2M17 9h2M17 12h2"/>',
    # 6 · winding: stator ring with slots and the rotating-field arrow
    "winding": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4.5"/>'
               '<path d="M12 4v3M12 17v3M4 12h3M17 12h3M6.3 6.3l2.1 2.1M15.6 15.6l2.1 2.1M6.3 17.7l2.1-2.1M15.6 8.4l2.1-2.1"/>'
               '<path d="M10 10.5a2.5 2.5 0 1 1 0 3"/>',
    # 7 · optimisation: Pareto front, dominated points behind it
    "optimisation": '<path d="M4 3v17h17"/><path d="M6 6c1 6 4 9 13 10"/>'
                    '<circle cx="7" cy="9" r="1"/><circle cx="10" cy="13" r="1"/><circle cx="15" cy="15.3" r="1"/>'
                    '<circle cx="13" cy="9" r="0.6"/><circle cx="17" cy="11" r="0.6"/><circle cx="11" cy="6" r="0.6"/>',
    # 8 · course: open book
    "cours": '<path d="M3 5c3-1 6-1 9 1v13c-3-2-6-2-9-1z"/><path d="M21 5c-3-1-6-1-9 1v13c3-2 6-2 9-1z"/>'
             '<path d="M6 9h3M6 12h3M15 9h3M15 12h3"/>',
    # 9 · 3D laboratory: an isometric block (scene)
    "lab3d": '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5"/>',
    # shell actions
    "help": '<circle cx="12" cy="12" r="8.5"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .8-1 1.5v.7"/>'
            '<circle cx="12" cy="16.8" r="0.5"/>',
    "report": '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/><path d="M9 12h6M9 15h6M9 18h4"/>',
    "collapse": '<path d="M15 6l-6 6 6 6"/>',
    "expand": '<path d="M9 6l6 6-6 6"/>',
    "motor": '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2.5"/><path d="M12 5v4.5M12 14.5V19M5 12h4.5M14.5 12H19"/>',
}

WORKSPACE_GLYPHS = ("identification", "envelope", "efficiency", "vehicle", "thermal", "winding", "optimisation",
                    "cours", "lab3d")


def svg(name: str, colour: str, stroke: float = 1.6) -> str:
    """Complete SVG document of a glyph in one colour."""
    if name not in GLYPHS:
        raise ValueError(f"unknown glyph {name!r}; known: {', '.join(GLYPHS)}")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{colour}" '
            f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{GLYPHS[name]}</svg>')


def logo_svg(accent: str, ink: str) -> str:
    """EV-LAB mark: stator ring, four pole arcs in the accent colour, rotor in the ink colour."""
    arcs = "".join(
        f'<path d="M {12 + 9 * c1:.3f} {12 + 9 * s1:.3f} A 9 9 0 0 1 {12 + 9 * c2:.3f} {12 + 9 * s2:.3f}"/>'
        for c1, s1, c2, s2 in _pole_arcs()
    )
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke-linecap="round">'
            f'<g stroke="{accent}" stroke-width="2.4">{arcs}</g>'
            f'<circle cx="12" cy="12" r="4.2" stroke="{ink}" stroke-width="1.6"/>'
            f'<circle cx="12" cy="12" r="1.1" fill="{accent}" stroke="none"/></svg>')


def _pole_arcs():
    import math

    for k in range(4):  # four poles (2p = 4), 60° arcs separated by 30° gaps
        a1, a2 = math.radians(90 * k + 15), math.radians(90 * k + 75)
        yield math.cos(a1), math.sin(a1), math.cos(a2), math.sin(a2)


def _render(document: str, size: int, ratio: float):
    from PySide6.QtCore import QByteArray, Qt
    from PySide6.QtGui import QPainter, QPixmap
    from PySide6.QtSvg import QSvgRenderer

    px = max(1, round(size * ratio))
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(document.encode("utf-8")))
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def _ratio() -> float:
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance()
    return max((s.devicePixelRatio() for s in app.screens()), default=1.0) if app else 1.0


@lru_cache(maxsize=256)
def _icon(name: str, colour: str, size: int, active: str | None):
    from PySide6.QtGui import QIcon

    icon = QIcon()
    ratio = _ratio()  # sharp on high-DPI screens (Windows 125 %, 150 %, 200 %)
    icon.addPixmap(_render(svg(name, colour), size, ratio), QIcon.Mode.Normal, QIcon.State.Off)
    if active:
        icon.addPixmap(_render(svg(name, active), size, ratio), QIcon.Mode.Normal, QIcon.State.On)
    return icon


def icon(name: str, colour: str, size: int = 20, active: str | None = None):
    """QIcon of a glyph in `colour`; with `active`, the checked state uses that colour."""
    return _icon(name, colour, size, active)


def logo(accent: str, ink: str, size: int = 28):
    """QPixmap of the EV-LAB mark."""
    return _render(logo_svg(accent, ink), size, _ratio())
