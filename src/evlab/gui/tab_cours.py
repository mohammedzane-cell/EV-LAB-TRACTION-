"""Tab « 8 · Cours »: the course pages of io.cours, with a table of contents, a search and live values.

Thin view: the pages, their numbers (core.cours_valeurs) and the accent-insensitive search
are in io.cours; this module only shows them. Left: search box and table of contents
(pages, their sections and law groups). Right: a QTextBrowser that never follows links
itself; evlab:// links are routed here:
  evlab://onglet/<onglet>   → open_tab(<onglet>) (the main window switches tab)
  evlab://page/<page>       → show that page
  evlab://reponse/<page>/<n> → show or hide answer n
The examples are computed once in a worker thread (a few tenths of a second).
"""

from __future__ import annotations

import re

from PySide6.QtCore import QThreadPool, QUrl, Signal
from PySide6.QtGui import QColor, QPalette, QTextCharFormat, QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextBrowser,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from evlab.core.session import Session
from evlab.gui import theme
from evlab.gui.widgets import muted, scroll_panel
from evlab.gui.workers import CoreWorker
from evlab.io import cours

TITLE = "8 · Cours"
LEFT_WIDTH = 300
SLUG_ROLE = 0x0101  # Qt.ItemDataRole.UserRole + 1: page id of a tree item
HEADING_ROLE = 0x0102  # heading text of a section item (None for a page)
_MONO = re.compile(r"font-family:'[^']*monospace[^']*';")


def page_html(markdown: str, name: str | None = None) -> str:
    """HTML of a rendered page for QTextBrowser, coloured from the palette of a theme (None: current)."""
    pal = theme.palette(name)
    doc = QTextDocument()
    doc.setMarkdown(markdown)
    html = doc.toHtml()
    accent = pal["primary"] if (name or theme.current()) == theme.LIGHT else pal["info"]
    return _MONO.sub(lambda m: m.group(0) + f" color:{accent};", html)


def document_css(name: str | None = None) -> str:
    """Default stylesheet of the course document: text, links, tables (palette of a theme)."""
    pal = theme.palette(name)
    return (f"body {{ color: {pal['text']}; }} a {{ color: {pal['info']}; }} "
            f"table {{ border-color: {pal['border']}; border-style: solid; }} "
            f"th {{ background-color: {pal['tab']}; }} td, th {{ border-color: {pal['border']}; padding: 3px 6px; }}")


class CoursTab(QWidget):
    """Tab 8: one page at a time, table of contents and search on the left."""

    status_message = Signal(str)
    open_tab = Signal(str)  # name of a tab of io.cours.TABS
    page_shown = Signal(str)  # page id, once the page is on screen
    examples_ready = Signal()

    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session
        self.title = TITLE
        self.current: str = cours.PAGES[0].slug
        self.ouvertes: dict[str, set[int]] = {}
        self.ex: dict | None = None
        self._pending: tuple[str, str | None] | None = None
        self.query = ""  # last search (accents and case are ignored)
        self._worker: CoreWorker | None = None

        root = QHBoxLayout(self)
        left = QWidget()
        left.setFixedWidth(LEFT_WIDTH)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Rechercher dans le cours…")
        self.search.setToolTip("Les accents et les majuscules sont ignorés : « decrochage » trouve « décrochage »")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.apply_search)
        lv.addWidget(self.search)
        self.lbl_search = muted(QLabel(""))
        self.lbl_search.setWordWrap(True)
        lv.addWidget(self.lbl_search)
        self.toc = QTreeWidget()
        self.toc.setHeaderHidden(True)
        self.toc.setMinimumHeight(360)
        self.toc.itemClicked.connect(self._toc_clicked)
        lv.addWidget(self.toc, 1)
        self._fill_toc()
        hint = muted(QLabel("F1 ou « ? » sur un onglet : la page de cet onglet."))
        hint.setWordWrap(True)
        lv.addWidget(hint)
        root.addWidget(scroll_panel(left))

        self.browser = QTextBrowser()
        self.browser.setObjectName("coursBrowser")
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        self.browser.anchorClicked.connect(self.follow)
        root.addWidget(self.browser, 1)
        self._style_browser()
        self.browser.setPlainText("Préparation du cours…")

    # --- table of contents and search ----------------------------------------------------

    def _fill_toc(self) -> None:
        self.toc.clear()
        for p in cours.PAGES:
            top = QTreeWidgetItem([p.title])
            top.setData(0, SLUG_ROLE, p.slug)
            top.setData(0, HEADING_ROLE, None)
            for level, text in cours.titres(p.slug):
                parent = top if level == 2 or top.childCount() == 0 else top.child(top.childCount() - 1)
                item = QTreeWidgetItem([text])
                item.setData(0, SLUG_ROLE, p.slug)
                item.setData(0, HEADING_ROLE, text)
                parent.addChild(item)
            self.toc.addTopLevelItem(top)

    def _toc_clicked(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        self.show_page(item.data(0, SLUG_ROLE), item.data(0, HEADING_ROLE))

    def apply_search(self, text: str) -> list[str]:
        """Keep the pages that contain every word of `text` (accents and case ignored); returns their ids."""
        self.query = text
        hits = cours.rechercher(text)
        shown = [slug for slug, _ in hits] if text.strip() else [p.slug for p in cours.PAGES]
        for k in range(self.toc.topLevelItemCount()):
            item = self.toc.topLevelItem(k)
            item.setHidden(item.data(0, SLUG_ROLE) not in shown)
        if text.strip():
            n = sum(c for _, c in hits)
            self.lbl_search.setText(f"{n} occurrence(s) dans {len(hits)} page(s)" if hits else "Aucune page trouvée")
            self._highlight()
        else:
            self.lbl_search.setText("")
            self.browser.setExtraSelections([])
        return shown

    def _highlight(self) -> int:
        """Highlight the search words in the page shown; scroll to the first. Returns the number found."""
        words = cours.mots_recherche(self.query)
        if not words:
            self.browser.setExtraSelections([])
            return 0
        folded = cours.replier(self.browser.toPlainText())
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(theme.palette()["demo_bg"]))
        fmt.setForeground(QColor(theme.palette()["demo_fg"]))
        selections = []
        for w in words:
            for m in re.finditer(re.escape(w), folded):
                sel = QTextEdit.ExtraSelection()
                cur = QTextCursor(self.browser.document())
                cur.setPosition(m.start())
                cur.setPosition(m.end(), QTextCursor.MoveMode.KeepAnchor)
                sel.cursor, sel.format = cur, fmt
                selections.append(sel)
        selections.sort(key=lambda s: s.cursor.position())
        self.browser.setExtraSelections(selections)
        if selections:
            first = QTextCursor(selections[0].cursor)
            first.clearSelection()  # move there without selecting: every match keeps the same highlight
            self.browser.setTextCursor(first)
            self.browser.ensureCursorVisible()
        return len(selections)

    # --- pages ---------------------------------------------------------------------------

    def _style_browser(self) -> None:
        pal = theme.palette()
        self.browser.setStyleSheet(f"QTextBrowser#coursBrowser {{ background: {pal['card']}; color: {pal['text']}; "
                                   f"border: 1px solid {pal['border']}; border-radius: 8px; padding: 6px; }}")
        qp = self.browser.palette()
        qp.setColor(QPalette.ColorRole.Link, QColor(pal["info"]))
        qp.setColor(QPalette.ColorRole.Text, QColor(pal["text"]))
        qp.setColor(QPalette.ColorRole.Base, QColor(pal["card"]))
        self.browser.setPalette(qp)
        self.browser.document().setDefaultStyleSheet(document_css())

    def _ensure_examples(self) -> bool:
        """True when the example numbers are ready; else start computing them in a worker."""
        if self.ex is not None:
            return True
        if self._worker is None:
            worker = CoreWorker(lambda progress: cours.exemples())
            worker.signals.finished.connect(self._examples_done)
            worker.signals.failed.connect(lambda msg: self.status_message.emit(f"Cours : {msg}"))
            self._worker = worker
            QThreadPool.globalInstance().start(worker)
        return False

    def _examples_done(self, ex: dict) -> None:
        self.ex = ex
        self.examples_ready.emit()
        slug, heading = self._pending or (self.current, None)
        self._pending = None
        self.show_page(slug, heading)

    def show_page(self, slug: str, heading: str | None = None, keep_scroll: bool = False) -> bool:
        """Show a page (scrolled to one of its headings, or where it was). False until the examples are ready."""
        cours.page(slug)  # validates
        self.current = slug
        if not self._ensure_examples():
            self._pending = (slug, heading)
            return False
        bar = self.browser.verticalScrollBar()
        keep = bar.value() if keep_scroll else None
        markdown = cours.rendre(slug, self.session.motor, self.ouvertes.get(slug, set()), ex=self.ex)
        self.browser.document().setDefaultStyleSheet(document_css())
        self.browser.setHtml(page_html(markdown))
        if keep is not None:
            bar.setValue(keep)
        elif heading:
            self.scroll_to(heading)
        else:
            bar.setValue(0)
        if self.query.strip():
            self._highlight()
        self._select_in_toc(slug)
        p = cours.page(slug)
        self.status_message.emit(f"Cours : {p.title}")
        self.page_shown.emit(slug)
        return True

    def scroll_to(self, heading: str) -> bool:
        """Scroll to the heading block with this text; False if the page has none."""
        block = self.browser.document().begin()
        while block.isValid():
            if block.blockFormat().headingLevel() > 0 and block.text().strip() == heading:
                cur = QTextCursor(block)
                self.browser.setTextCursor(cur)
                bar = self.browser.verticalScrollBar()
                bar.setValue(bar.maximum())  # then back up: the heading lands at the top
                self.browser.ensureCursorVisible()
                return True
            block = block.next()
        return False

    def _select_in_toc(self, slug: str) -> None:
        for k in range(self.toc.topLevelItemCount()):
            item = self.toc.topLevelItem(k)
            if item.data(0, SLUG_ROLE) == slug:
                self.toc.setCurrentItem(item)
                return

    def show_tab_page(self, tab: str) -> bool:
        """Show the page that explains a tab (identification … optimisation)."""
        return self.show_page(cours.page_for_tab(tab).slug)

    def toggle_answer(self, slug: str, n: int) -> None:
        """Show or hide answer n of a page (stays where the reader is)."""
        opened = self.ouvertes.setdefault(slug, set())
        opened.symmetric_difference_update({n})
        self.show_page(slug, keep_scroll=True)

    def follow(self, url: QUrl | str) -> bool:
        """Route a link clicked in the page; False if it has no target."""
        text = url.toString() if isinstance(url, QUrl) else url
        if not cours.lien_valide(text):
            self.status_message.emit(f"Lien sans cible : {text}")
            return False
        parts = text.removeprefix("evlab://").split("/")
        if parts[0] == "onglet":
            self.open_tab.emit(parts[1])
        elif parts[0] == "page":
            self.show_page(parts[1])
        else:
            self.toggle_answer(parts[1], int(parts[2]))
        return True

    # --- refresh -------------------------------------------------------------------------

    def on_motor_changed(self) -> None:
        """A new motor was published: refresh the live values of the page shown."""
        if self.ex is not None:
            self.show_page(self.current, keep_scroll=True)

    def on_theme_changed(self) -> None:
        self._style_browser()
        if self.ex is not None:
            self.show_page(self.current, keep_scroll=True)

    def showEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().showEvent(event)
        if self.ex is None:
            self.show_page(self.current)
