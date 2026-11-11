"""PDF of the whole course (Fichier → Exporter le cours en PDF): QTextDocument + QPrinter, A4.

A title page (EV-Traction Lab, ENP Alger, ME3, date), then every page of io.cours in its
print form (answers printed under their questions, links as plain text), each page on a
new sheet, always in the light theme (the document is meant to be printed). Page numbers
are added by QTextDocument.print_ (the document has no page size of its own).
Font: DejaVu Sans and DejaVu Sans Mono from matplotlib's data, as in the PDF report: they
cover every symbol of the course, and their text copies cleanly out of the PDF (the UI font
swaps in contextual glyphs that a PDF reader cannot map back to characters).
"""

from __future__ import annotations

import datetime as dt
import html
import re
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QMarginsF
from PySide6.QtGui import QFont, QFontDatabase, QPageLayout, QPageSize, QTextDocument
from PySide6.QtPrintSupport import QPrinter

from evlab.core.session import MotorParams
from evlab.gui.tab_cours import document_css, page_html
from evlab.io import cours

TITLE = "EV-Traction Lab"
SUBTITLE = "Cours : les lois de l'application, onglet par onglet"
SCHOOL = "École Nationale Polytechnique, Alger"
COURSE = "ME3 · Machines électriques"
PAGE_BREAK = '<p style="page-break-before: always; margin: 0px;"></p>'
FONT_FILES = ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans-Oblique.ttf", "DejaVuSans-BoldOblique.ttf",
              "DejaVuSansMono.ttf", "DejaVuSansMono-Bold.ttf")
SANS, MONO = "DejaVu Sans", "DejaVu Sans Mono"
FONT_POINT_SIZE = 10


@lru_cache(maxsize=1)
def register_fonts() -> tuple[str, ...]:
    """Load the DejaVu fonts of matplotlib into Qt once; returns the families now available."""
    import matplotlib

    ttf = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    families: list[str] = []
    for name in FONT_FILES:
        fid = QFontDatabase.addApplicationFont(str(ttf / name))
        if fid < 0:
            raise OSError(f"police introuvable pour le PDF du cours : {ttf / name}")
        families += QFontDatabase.applicationFontFamilies(fid)
    QFont.insertSubstitution(MONO, SANS)  # « ∥ » is not in DejaVu Sans Mono: take it from DejaVu Sans
    return tuple(dict.fromkeys(families))


def _print_fonts(body: str) -> str:
    """Every font of the page HTML replaced by DejaVu Sans / DejaVu Sans Mono."""
    body = re.sub(r"font-family:'[^']*monospace[^']*';", f"font-family:'{MONO}';", body)
    return re.sub(r"font-family:'(?!DejaVu)[^']*';", f"font-family:'{SANS}';", body)


def title_page(date: dt.date, motor_label: str) -> str:
    """HTML of the title page."""
    return (
        '<div align="center">'
        '<p style="margin-top: 180px; font-size: 28pt; font-weight: bold;">' + html.escape(TITLE) + "</p>"
        '<p style="font-size: 15pt;">' + html.escape(SUBTITLE) + "</p>"
        '<p style="margin-top: 60px; font-size: 13pt;">' + html.escape(SCHOOL) + "</p>"
        '<p style="font-size: 13pt;">' + html.escape(COURSE) + "</p>"
        '<p style="margin-top: 40px; font-size: 12pt;">' + date.strftime("%d/%m/%Y") + "</p>"
        '<p style="margin-top: 80px; font-size: 10pt;">Référence principale : cours du Pr Kamel Boughrara '
        "(AC Electrical Machines, ENP Alger). Tous les nombres sont calculés par l'application ; "
        "« Avec votre moteur » : " + html.escape(motor_label) + ".</p>"
        "</div>"
    )


def course_html(motor: MotorParams | None, date: dt.date | None = None, ex: dict | None = None) -> str:
    """The whole course as one HTML document (title page, table of contents, every page)."""
    from evlab.core import cours_valeurs as cv

    date = date or dt.date.today()
    values = cv.valeurs_moteur(motor)
    label = values["source"] if values else cours.NO_MOTOR
    toc = "<h2>Sommaire</h2><ol>" + "".join(f"<li>{html.escape(p.title)}</li>" for p in cours.PAGES) + "</ol>"
    parts = [title_page(date, str(label)), PAGE_BREAK, toc]
    for p in cours.PAGES:
        body = page_html(cours.rendre(p.slug, motor, ex=ex, imprimer=True), "light")
        start, end = body.find("<body"), body.rfind("</body>")
        parts += [PAGE_BREAK, _print_fonts(body[body.find(">", start) + 1:end])]
    return "<html><body>" + "".join(parts) + "</body></html>"


def export_course_pdf(path: str | Path, motor: MotorParams | None, date: dt.date | None = None,
                      ex: dict | None = None) -> Path:
    """Write the course PDF (A4, 15 mm margins) and return its path."""
    path = Path(path)
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(path))
    printer.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait,
                                      QMarginsF(15, 15, 15, 15), QPageLayout.Unit.Millimeter))
    printer.setDocName(f"{TITLE} — cours")
    printer.setCreator(TITLE)
    register_fonts()
    doc = QTextDocument()
    font = QFont(SANS, FONT_POINT_SIZE)
    for tag in ("liga", "clig"):  # no « ﬁ » ligature: the text copies out of the PDF as plain letters
        font.setFeature(QFont.Tag(tag), 0)
    doc.setDefaultFont(font)
    doc.setDefaultStyleSheet(document_css("light") + f" body {{ font-family: '{SANS}'; }}")
    doc.setHtml(course_html(motor, date, ex))
    doc.print_(printer)
    if not path.exists() or path.stat().st_size == 0:
        raise OSError(f"le PDF du cours n'a pas été écrit : {path}")
    return path
