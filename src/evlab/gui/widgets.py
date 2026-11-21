"""EV-LAB component library: French spin boxes, panels, section headers, KPI readouts, provenance chips,
plot legends and plot inspection (crosshair + readout). Presentation only.

Their look comes from gui/style.qss (object names #card, #cardTitle, #sectionHeader, #kpi,
#kpiLabel, #kpiValue, #plotLegend, #plotReadout and the chip / role properties), applied by
gui/theme.py. docs/ui_design_system.md documents each component.
"""

from __future__ import annotations

from PySide6.QtCore import QLocale, QRectF, QSize, Qt
from PySide6.QtGui import QFont, QFontMetrics, QPainter
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


CHIP_KINDS = ("demo", "alert", "source")


def chip(text: str, kind: str = "demo") -> QLabel:
    """Provenance / state label: "demo" (amber: synthetic or assumed values), "alert" (red),
    "source" (neutral: where a value comes from, e.g. « moteur de référence »)."""
    if kind not in CHIP_KINDS:
        raise ValueError(f"chip kind must be one of {CHIP_KINDS}, got {kind!r}")
    lbl = QLabel(text)
    lbl.setProperty("chip", kind)
    return lbl


def section_header(text: str) -> QLabel:
    """Small capitals label that opens a group of controls or results (#sectionHeader)."""
    lbl = QLabel(text.upper())
    lbl.setObjectName("sectionHeader")
    f = lbl.font()
    f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 108)
    lbl.setFont(f)
    return lbl


def divider() -> QFrame:
    """1 px horizontal rule in the divider colour."""
    line = QFrame()
    line.setObjectName("divider")
    line.setFrameShape(QFrame.Shape.NoFrame)
    return line


def muted(lbl: QLabel) -> QLabel:
    """Secondary text in the muted colour of the theme."""
    lbl.setProperty("role", "muted")
    return lbl


class ElidedLabel(QLabel):
    """One-line label that elides itself to the width it gets (« … »); text() and the tooltip keep the full text.

    Its minimum width is small, so a long caption never imposes its width on the window.
    """

    MIN_WIDTH = 40

    def setText(self, text: str) -> None:  # noqa: N802 (Qt API)
        super().setText(text)
        self.setToolTip(text)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt API)
        return QSize(self.MIN_WIDTH, super().minimumSizeHint().height())

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt API)
        p = QPainter(self)
        p.setFont(self.font())
        p.setPen(self.palette().color(self.foregroundRole()))
        r = self.contentsRect()
        text = self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideRight, r.width())
        p.drawText(r, int(self.alignment()) | int(Qt.AlignmentFlag.AlignVCenter), text)
        p.end()


class ReadoutLabel(QLabel):
    """Value label of a KPI tile: the number large, its unit smaller and muted, on one baseline.

    text() stays the plain "value unit" string (the reports, the tests and the tools read it);
    only the painting splits it.
    """

    def __init__(self, text: str = "", unit: str = "") -> None:
        super().__init__(text)
        self.unit = unit

    def _number_font(self) -> QFont:
        f = QFont(self.font())
        f.setFeature(QFont.Tag("tnum"), 1)  # tabular figures: readouts of a row line up
        return f

    def _parts(self) -> tuple[str, str]:
        text = self.text()
        if self.unit and text.endswith(" " + self.unit):
            return text[: -len(self.unit) - 1], self.unit
        return text, ""

    def _unit_font(self) -> QFont:
        f = QFont(self.font())
        f.setPointSizeF(max(8.0, self.font().pointSizeF() * 0.55))
        f.setWeight(QFont.Weight.Normal)
        return f

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt API)
        number, unit = self._parts()
        fm, fu = QFontMetrics(self._number_font()), QFontMetrics(self._unit_font())
        w = fm.horizontalAdvance(number) + (fu.horizontalAdvance(" " + unit) if unit else 0)
        return QSize(w + 2, fm.height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt API)
        return self.sizeHint()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt API)
        from evlab.gui import theme

        number, unit = self._parts()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        fm = QFontMetrics(self._number_font())
        base = (self.height() + fm.ascent() - fm.descent()) / 2
        p.setFont(self._number_font())
        p.setPen(self.palette().color(self.foregroundRole()))
        p.drawText(QRectF(0, 0, self.width(), self.height()), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   number)
        if unit:
            from PySide6.QtGui import QColor

            x = fm.horizontalAdvance(number) + 4
            p.setFont(self._unit_font())
            p.setPen(QColor(theme.palette()["muted"]))
            p.drawText(int(x), int(base), unit)
        p.end()


class KpiTile(QFrame):
    """Readout tile: muted title, then the value large with its unit smaller (ReadoutLabel)."""

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
        self.value = ReadoutLabel("—", unit)
        self.value.setObjectName("kpiValue")
        self.unit = unit
        lay.addWidget(self.title)
        lay.addWidget(self.value)

    def set_value(self, text: str) -> None:
        self.value.setText(f"{text} {self.unit}" if text != "—" else "—")
        self.value.updateGeometry()


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


# --- plot inspection: crosshair and readout ------------------------------------------------

READOUT_MAX_CURVES = 4  # curves listed in a readout (the nearest sample of each)


def _axis_title(item, name: str) -> str:
    ax = item.getAxis(name)
    return (ax.labelText or ("x" if name == "bottom" else "y")) + (f" ({ax.labelUnits})" if ax.labelUnits else "")


def readout_text(item, x: float, y: float) -> str:
    """Readout of the cursor at (x, y) in data units, then the nearest computed sample of each named curve.

    Values are those of the plotted arrays (nothing is interpolated or recomputed); numbers use the
    French decimal comma.
    """
    import numpy as np

    from evlab.gui.format import fr

    parts = [f"{_axis_title(item, 'bottom')} = {fr(x, 4)}", f"{_axis_title(item, 'left')} = {fr(y, 4)}"]
    vx = item.viewRange()[0]
    tol = 0.03 * abs(vx[1] - vx[0])
    n = 0
    for curve in item.listDataItems():
        name = curve.name()
        if not name or not curve.isVisible() or n >= READOUT_MAX_CURVES:
            continue
        xs, ys = curve.getData()
        if xs is None or len(xs) == 0:
            continue
        xs, ys = np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)
        k = int(np.nanargmin(np.abs(xs - x))) if np.isfinite(xs).any() else -1
        if k < 0 or abs(xs[k] - x) > tol or not np.isfinite(ys[k]):
            continue
        parts.append(f"{name} : {fr(float(ys[k]), 4)}")
        n += 1
    return "   ·   ".join(parts)


def inspect_plots(root: QWidget) -> None:
    """Give every pyqtgraph plot under `root` a crosshair and a floating readout.

    The crosshair follows the mouse inside the plot area; the readout floats in the corner of the
    plot area away from the cursor (it never changes the layout) and shows the cursor in the axis
    units and the nearest sample of each named curve. Zoom (wheel), pan (drag), reset (« A » button,
    or right-click → View All) and export (right-click → Export…) are pyqtgraph's own.
    """
    import pyqtgraph as pg

    for pw in root.findChildren(pg.PlotWidget):
        if getattr(pw, "readout_label", None) is not None:
            continue
        item = pw.getPlotItem()
        label = QLabel("", pw)  # child of the plot: floats over it, outside any layout
        label.setObjectName("plotReadout")
        label.setWordWrap(True)
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        label.setVisible(False)
        pw.readout_label = label
        pen = pg.mkPen((143, 157, 176, 200), width=1, style=Qt.PenStyle.DashLine)
        vline, hline = pg.InfiniteLine(angle=90, pen=pen), pg.InfiniteLine(angle=0, pen=pen)
        for line in (vline, hline):
            line.setZValue(1000)
            line.setVisible(False)
            item.addItem(line, ignoreBounds=True)
        pw.crosshair = (vline, hline)

        def moved(pos, pw=pw, item=item, vline=vline, hline=hline, label=label):
            vb = item.getViewBox()
            inside = vb.sceneBoundingRect().contains(pos)
            for line in (vline, hline):
                line.setVisible(inside)
            label.setVisible(inside)
            if not inside:
                return
            for line in (vline, hline):
                if line.scene() is None:  # the tab's redraw (plot.clear()) removed it: put it back
                    item.addItem(line, ignoreBounds=True)
            pt = vb.mapSceneToView(pos)
            vline.setPos(pt.x())
            hline.setPos(pt.y())
            label.setText(readout_text(item, pt.x(), pt.y()))
            area = pw.mapFromScene(vb.sceneBoundingRect()).boundingRect()
            label.setFixedWidth(int(max(120, min(340, area.width() - 12))))
            label.adjustSize()
            cursor = pw.mapFromScene(pos)
            x = area.left() + 6 if cursor.x() > area.center().x() else area.right() - label.width() - 6
            label.move(int(x), int(area.top() + 4))
            label.raise_()

        pw.scene().sigMouseMoved.connect(moved)
        pw.setToolTip("Molette : zoom · glisser : déplacer · bouton « A » (coin bas gauche) : vue complète · "
                      "clic droit : View All, Export… (PNG, SVG, CSV)")


# --- empty states: what to do before a plot has data ------------------------------------------


class _EmptyOverlay(QLabel):
    """Centred hint over an empty plot; hidden as soon as the plot holds a data item."""

    def __init__(self, pw, text: str) -> None:
        super().__init__(text, pw)
        self.setObjectName("emptyState")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._pw = pw
        pw.installEventFilter(self)
        self.refresh()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt API)
        from PySide6.QtCore import QEvent

        if obj is self._pw and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self._place()
        return False

    def _place(self) -> None:
        w, h = self._pw.width(), self._pw.height()
        width = min(320, max(120, w - 40))
        self.setFixedWidth(width)
        self.adjustSize()
        self.move((w - width) // 2, max(0, (h - self.height()) // 2))

    def refresh(self) -> None:
        has_data = any(getattr(c, "xData", None) is not None and len(c.xData) > 0
                       for c in self._pw.getPlotItem().listDataItems())
        self.setVisible(not has_data)
        self._place()
        self.raise_()


def empty_state(pw, text: str) -> QLabel:
    """Show `text` in the middle of plot `pw` while it has no data (e.g. « Lancez le calcul »)."""
    overlay = getattr(pw, "empty_overlay", None)
    if overlay is not None:
        overlay.setText(text)
        overlay.refresh()
        return overlay
    overlay = _EmptyOverlay(pw, text)
    pw.empty_overlay = overlay
    item = pw.getPlotItem()
    for meth in ("addItem", "removeItem", "clear"):
        orig = getattr(item, meth)

        def wrapped(*a, _orig=orig, **kw):
            out = _orig(*a, **kw)
            overlay.refresh()
            return out

        setattr(item, meth, wrapped)
    return overlay
