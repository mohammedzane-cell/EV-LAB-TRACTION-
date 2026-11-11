"""Layout audit of a shown widget tree: overlaps, widgets outside their parent, cut text. Presentation only.

layout_problems(root) walks every visible widget under `root` that is placed by a layout
(internal sub-widgets of spin boxes, tables or plots are not layout items, so they are not
checked) and reports, in plain sentences:
  - a widget whose geometry leaves its parent's rectangle;
  - two widgets of the same parent whose rectangles intersect;
  - a label, button, check box or radio button smaller than its text needs (cut text):
    narrower than its minimum size hint, or, for a word-wrapped label, shorter than the
    height its text needs at its width.
Used by the GUI tests at 1280×720, 1366×768 and 1920×1080 and by tools/capture_screenshots.py.
"""

from __future__ import annotations

TOLERANCE = 1  # px: rounding of fractional layouts


def _managed(widget, root) -> list:
    """Widgets placed by `widget`'s layout (through nested layouts, not into child widgets), visible in root."""
    from PySide6.QtWidgets import QLayout

    lay = widget.layout()
    out = []
    if lay is None:
        return out
    stack: list[QLayout] = [lay]
    while stack:
        current = stack.pop()
        for k in range(current.count()):
            item = current.itemAt(k)
            if item.widget() is not None:
                w = item.widget()
                if w.isVisibleTo(root) and not w.isWindow():
                    out.append(w)
            elif item.layout() is not None:
                stack.append(item.layout())
    return out


def _name(w) -> str:
    text = ""
    for attr in ("text", "title"):
        f = getattr(w, attr, None)
        if callable(f):
            try:
                text = f()
            except TypeError:
                text = ""
            if isinstance(text, str) and text:
                break
    label = w.objectName() or type(w).__name__
    return f"{label} « {text[:40]} »" if isinstance(text, str) and text else label


def _cut(w) -> str | None:
    from PySide6.QtWidgets import QAbstractButton, QLabel

    if isinstance(w, QLabel):
        if not w.text() or w.pixmap() is not None and not w.pixmap().isNull():
            return None
        if w.wordWrap():
            need = w.heightForWidth(w.width())
            if need > w.height() + TOLERANCE:
                return f"{_name(w)} : texte coupé en hauteur ({w.height()} px pour {need} px)"
            return None
        need = w.minimumSizeHint().width()
        if need > w.width() + TOLERANCE:
            return f"{_name(w)} : texte coupé en largeur ({w.width()} px pour {need} px)"
        return None
    if isinstance(w, QAbstractButton) and w.text():
        hint = w.minimumSizeHint()
        if hint.width() > w.width() + TOLERANCE:
            return f"{_name(w)} : texte coupé en largeur ({w.width()} px pour {hint.width()} px)"
        if hint.height() > w.height() + TOLERANCE:
            return f"{_name(w)} : texte coupé en hauteur ({w.height()} px pour {hint.height()} px)"
    return None


def layout_problems(root) -> list[str]:
    """Every overlap, out-of-parent widget and cut text under the shown widget `root` (empty list: none)."""
    from PySide6.QtWidgets import QWidget

    problems: list[str] = []
    parents = [root] + [w for w in root.findChildren(QWidget) if w.isVisibleTo(root)]
    for parent in parents:
        kids = _managed(parent, root)
        bounds = parent.rect().adjusted(-TOLERANCE, -TOLERANCE, TOLERANCE, TOLERANCE)
        for w in kids:
            g = w.geometry()
            if g.width() > 0 and g.height() > 0 and not bounds.contains(g):
                problems.append(f"{_name(w)} déborde de {_name(parent)} ({g} hors de {parent.rect()})")
            cut = _cut(w)
            if cut:
                problems.append(cut)
        for i, a in enumerate(kids):
            ga = a.geometry().adjusted(TOLERANCE, TOLERANCE, -TOLERANCE, -TOLERANCE)
            for b in kids[i + 1:]:
                gb = b.geometry().adjusted(TOLERANCE, TOLERANCE, -TOLERANCE, -TOLERANCE)
                if ga.intersects(gb):
                    problems.append(f"{_name(a)} chevauche {_name(b)} dans {_name(parent)}")
    return problems
