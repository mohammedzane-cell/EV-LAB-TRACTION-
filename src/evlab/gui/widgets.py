"""Small shared widgets: French spin boxes, cards, KPI tiles, chips. Presentation only.

Their look comes from gui/style.qss (object names #card, #cardTitle, #kpi, #kpiLabel,
#kpiValue and the chip / role properties), applied by gui/theme.py.
"""

from __future__ import annotations

from PySide6.QtCore import QLocale, Qt
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

SCROLLBAR_ROOM = 12  # px kept for the left panel's vertical scroll bar

FRENCH = QLocale(QLocale.Language.French, QLocale.Country.France)


def french_spin(lo: float, hi: float, decimals: int, suffix: str, value: float) -> QDoubleSpinBox:
    """QDoubleSpinBox with a decimal comma, right-aligned, with a unit suffix."""
    s = QDoubleSpinBox()
    s.setLocale(FRENCH)
    s.setRange(lo, hi)
    s.setDecimals(decimals)
    s.setSuffix(f" {suffix}")
    s.setValue(value)
    s.setAlignment(Qt.AlignmentFlag.AlignRight)
    return s


def scroll_panel(content: QWidget) -> QScrollArea:
    """Left input panel in a vertical scroll area: on a short screen it scrolls instead of squeezing.

    content keeps its fixed width; the area adds room for the scroll bar and never scrolls sideways.
    """
    content.setObjectName("leftContent")
    area = QScrollArea()
    area.setObjectName("leftPanel")
    area.setWidget(content)
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setFixedWidth(content.maximumWidth() + SCROLLBAR_ROOM)
    area.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
    return area


def card(title: str) -> tuple[QFrame, QVBoxLayout, QHBoxLayout]:
    """Rounded card with a bold title (style.qss #card); returns (card, body layout, header layout)."""
    frame = QFrame()
    frame.setObjectName("card")
    lay = QVBoxLayout(frame)
    head = QHBoxLayout()
    label = QLabel(title)
    label.setObjectName("cardTitle")
    head.addWidget(label)
    head.addStretch(1)
    lay.addLayout(head)
    return frame, lay, head


def set_demo_chip(lbl: QLabel, labels: list[str]) -> None:
    """Show a démo chip when any input is démo; its tooltip lists them (labels from io.notes.demo_labels)."""
    lbl.setVisible(bool(labels))
    lbl.setToolTip("Valeurs démo : " + " ; ".join(labels) if labels else "")


def chip(text: str, kind: str = "demo") -> QLabel:
    """Rounded label: "demo" (amber, e.g. "points synthétiques (démo)") or "alert" (red)."""
    if kind not in ("demo", "alert"):
        raise ValueError(f"chip kind must be 'demo' or 'alert', got {kind!r}")
    lbl = QLabel(text)
    lbl.setProperty("chip", kind)
    return lbl


def muted(lbl: QLabel) -> QLabel:
    """Secondary text in the muted colour of the theme."""
    lbl.setProperty("role", "muted")
    return lbl


class KpiTile(QFrame):
    """Title + large value + unit."""

    def __init__(self, title: str, unit: str) -> None:
        super().__init__()
        self.setObjectName("kpi")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(2)
        self.title = QLabel(title)
        self.title.setObjectName("kpiLabel")
        self.title.setWordWrap(True)  # tiles can shrink on a narrow window: the label wraps
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.value = QLabel("—")
        self.value.setObjectName("kpiValue")
        self.unit = unit
        lay.addWidget(self.title)
        lay.addWidget(self.value)

    def set_value(self, text: str) -> None:
        self.value.setText(f"{text} {self.unit}" if text != "—" else "—")


# --- plots: flexible size, legends outside the plot area ---------------------------------

PLOT_MIN_HEIGHT = 120  # px: a plot never collapses on a short screen
CANVAS_MIN_HEIGHT = 260  # px: the matplotlib map of tab 3

_GLYPHS = {"o": "●", "star": "★", "x": "✖", "s": "■", "t": "▲", "+": "✚", "d": "◆"}


def _legend_entry(item, text: str) -> str:
    """HTML sample for one legend entry: a line, a dashed line or the item's symbol, in its colour."""
    import pyqtgraph as pg
    from PySide6.QtCore import Qt as _Qt

    opts = getattr(item, "opts", {}) or {}
    colour, glyph = "#888888", "■"
    if isinstance(item, pg.BarGraphItem):
        colour = pg.mkBrush(opts.get("brush")).color().name()
    else:
        pen = opts.get("pen")
        p = pg.mkPen(pen) if pen is not None else None
        if p is not None and p.style() != _Qt.PenStyle.NoPen and opts.get("symbol") is None:
            colour = p.color().name()
            glyph = "━━" if p.style() == _Qt.PenStyle.SolidLine else "╍╍"
        else:
            sym = opts.get("symbol") or "o"
            brush = opts.get("symbolBrush", opts.get("brush"))
            spen = opts.get("symbolPen", opts.get("pen"))
            hollow = brush is None
            ref = pg.mkPen(spen).color() if hollow else pg.mkBrush(brush).color()
            colour = ref.name()
            glyph = "○" if (hollow and sym == "o") else _GLYPHS.get(sym if isinstance(sym, str) else "o", "●")
    return f"<span style='color:{colour}'>{glyph}</span>&nbsp;{text}"


def external_legends(root: QWidget) -> None:
    """Move every pyqtgraph legend under `root` out of the plot area, into a row above the plot.

    The in-plot LegendItem keeps its entries (and its API) but is hidden; a QLabel mirrors it,
    updated whenever a curve is added, removed or the plot cleared, so a legend never covers data.
    """
    import pyqtgraph as pg

    for pw in root.findChildren(pg.PlotWidget):
        pi = pw.getPlotItem()
        legend = pi.legend
        if legend is None or getattr(pw, "legend_label", None) is not None:
            continue
        parent_layout = pw.parentWidget().layout() if pw.parentWidget() else None
        if parent_layout is None:
            continue
        box = QWidget()
        box.setObjectName("plotBox")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        label = QLabel("")
        label.setObjectName("plotLegend")
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        if parent_layout.replaceWidget(pw, box) is None:
            continue
        lay.addWidget(label)
        lay.addWidget(pw, 1)
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        legend.hide()
        pw.legend_label = label

        def refresh(legend=legend, label=label):
            entries = [_legend_entry(sample.item, lbl.text) for sample, lbl in legend.items]
            label.setText("&nbsp;&nbsp;&nbsp;&nbsp;".join(entries))
            label.setVisible(bool(entries))

        for meth in ("addItem", "removeItem", "clear"):
            orig = getattr(legend, meth)

            def wrapped(*a, _orig=orig, _refresh=refresh, **kw):  # bind this plot's refresh, not the loop's last
                out = _orig(*a, **kw)
                _refresh()
                return out

            setattr(legend, meth, wrapped)
        refresh()


def flexible_plots(root: QWidget) -> None:
    """Plots and canvases under `root` expand with the window and keep a minimum height."""
    import pyqtgraph as pg

    for pw in root.findChildren(pg.PlotWidget):
        pw.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        pw.setMinimumHeight(PLOT_MIN_HEIGHT)
    for w in root.findChildren(QWidget):
        if type(w).__name__ == "FigureCanvasQTAgg":
            w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            w.setMinimumHeight(CANVAS_MIN_HEIGHT)
