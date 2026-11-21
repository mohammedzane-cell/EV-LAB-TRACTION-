"""EV-LAB main window: sidebar navigation, workspace header, eight workspaces sharing one Session.

Seven engineering workspaces (one motor, one chain) and the course. The workspaces stay pages of a
QTabWidget (self.tabs, its tab bar hidden): every connection between them is unchanged; the
sidebar and the header only navigate and show context. Presentation only.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QAction, QActionGroup, QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QProgressBar,
    QSizePolicy,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from evlab.core.session import Session
from evlab.gui import glyphs, theme
from evlab.gui.tab_cours import CoursTab
from evlab.gui.tab_efficiency import EfficiencyTab
from evlab.gui.tab_envelope import EnvelopeTab
from evlab.gui.tab_identification import IdentificationTab
from evlab.gui.tab_optimisation import OptimisationTab
from evlab.gui.tab_thermal import ThermalTab
from evlab.gui.tab_vehicle import VehicleTab
from evlab.gui.tab_winding import WindingTab
from evlab.gui.widgets import ElidedLabel, chip, empty_state, external_legends, flexible_plots, inspect_plots
from evlab.gui.workers import CoreWorker
from evlab.io import cours

PRODUCT = "EV-LAB"
PRODUCT_SUBTITLE = "ELECTRIC TRACTION RESEARCH STUDIO"
WINDOW_TITLE = "EV-LAB · Electric Traction Research Studio — ENP Alger, ME3"
MIN_SIZE = (1100, 650)  # logical px: every tab stays usable down to this size (left panels scroll)
DEFAULT_SIZE = (1280, 800)
SMALL_SCREEN = (1440, 900)  # available screen below this: open maximised (e.g. 1366×768, 1920×1080 at 150 %)

TAB_CLASSES = (
    IdentificationTab,
    EnvelopeTab,
    EfficiencyTab,
    VehicleTab,
    ThermalTab,
    WindingTab,
    OptimisationTab,
    CoursTab,
)
COURSE_PDF_NAME = "cours_EV-Traction_Lab.pdf"  # file name kept: links and scripts already use it
COURSE_INDEX = len(TAB_CLASSES) - 1  # « 8 · Cours », last tab; tab k < 7 is explained by cours.TABS[k]


# sidebar: one entry per workspace, grouped by engineering domain; the caption is the header's subtitle
NAV_GROUPS = (("Machine", (0, 1, 2)), ("Véhicule", (3, 4)), ("Électromagnétisme", (5,)), ("Conception", (6,)),
              ("Ressources", (7,)))
CAPTIONS = (
    "Schéma équivalent en Γ identifié à partir des essais DC, à vide, rotor bloqué et en charge",
    "Enveloppe couple–vitesse du moteur identifié, sous loi V/f puis défluxage",
    "Carte de rendement η(C, n) et pertes du schéma équivalent, dans l'enveloppe",
    "Véhicule dimensionné pour ce moteur : effort à la roue, cycle WLTC, énergie et récupération",
    "Échauffement du bobinage et de la carcasse sur cycles enchaînés, durée de vie de l'isolant",
    "Bobinage triphasé : facteurs de bobinage, FMM et ses harmoniques, f.é.m., champ tournant",
    "Rapport, loi V/f, marge et rebobinage optimisés sur les modèles testés (front de Pareto)",
    "Les lois de chaque espace de travail, dans la notation du cours, avec les nombres de l'application",
)
SIDEBAR_WIDTH = 224  # px, expanded
SIDEBAR_COMPACT = 60  # px, icons only
MOTOR_CONTEXT_WIDTH = 300  # px: the motor label of the header is elided beyond (full text in its tooltip)
AUTO_COMPACT_BELOW = 1440  # window width (px) under which the sidebar starts compact (laptops keep their workspace width)
# hint shown over a workspace's plots while they are empty: the next action (empty state)
EMPTY_HINTS = {
    0: "Chargez les essais (ou « Charger la démo »), puis « Identifier ».",
    1: "Calcul de l'enveloppe en cours, ou réglages du variateur invalides.",
    3: "« Simuler le cycle » trace la vitesse et la puissance batterie.",
    4: "« Calculer les températures » : le cycle de l'onglet 4 alimente le modèle.",
    5: "Choisissez un bobinage valide (Z, 2p, pas y).",
    6: "Simulez d'abord le cycle (onglet 4), puis « Lancer l'optimisation ».",
}


def workspace_label(title: str) -> tuple[str, str]:
    """« 4 · Véhicule & WLTC » → ("04", "Véhicule & WLTC")."""
    num, _, name = title.partition(" · ")
    return f"{int(num):02d}", name


class WorkspaceStack(QTabWidget):
    """The workspace pages: a QTabWidget whose bar is hidden (the sidebar navigates).

    Qt still counts a hidden tab bar in QTabWidget.minimumSizeHint; here the minimum is that of the
    pages alone, so the bar that is never shown does not raise the minimum window size.
    """

    def minimumSizeHint(self):  # noqa: N802 (Qt API)
        if self.tabBar().isVisibleTo(self):
            return super().minimumSizeHint()
        w = h = 0
        for k in range(self.count()):
            hint = self.widget(k).minimumSizeHint()
            w, h = max(w, hint.width()), max(h, hint.height())
        return QSize(w, h)


def opens_maximised(avail_width: int, avail_height: int) -> bool:
    """True on a small screen (available area below 1440 × 900 logical px): the window opens maximised."""
    return avail_width < SMALL_SCREEN[0] or avail_height < SMALL_SCREEN[1]


def tab_label(title: str) -> str:
    """Escape '&' so Qt shows it instead of treating it as a shortcut marker."""
    return title.replace("&", "&&")


class MainWindow(QMainWindow):
    """EV-Traction Lab main window."""

    export_done = Signal(object)  # Path of the written file
    export_failed = Signal(str)

    def __init__(self, session: Session | None = None, theme_name: str | None = None) -> None:
        """theme_name: "light" or "dark"; None: the theme remembered by QSettings (Affichage menu)."""
        super().__init__()
        theme.apply(QApplication.instance(), theme_name if theme_name is not None else theme.saved())
        self.session = session if session is not None else Session()
        self.setWindowTitle(WINDOW_TITLE)
        self.setMinimumSize(*MIN_SIZE)
        self.resize(*DEFAULT_SIZE)

        self.busy_bar = QProgressBar()
        self.busy_bar.setRange(0, 0)  # indeterminate
        self.busy_bar.setMaximumWidth(140)
        self.busy_bar.setMaximumHeight(8)
        self.busy_bar.setTextVisible(False)
        self.busy_bar.setVisible(False)
        self.statusBar().addPermanentWidget(self.busy_bar)
        self.statusBar().addPermanentWidget(QLabel("Python 3 · PySide6"))

        self.tabs = WorkspaceStack()
        self.tabs.setDocumentMode(True)
        for cls in TAB_CLASSES:
            tab = cls(self.session)
            self.tabs.addTab(tab, tab_label(tab.title))
            if hasattr(tab, "status_message"):
                tab.status_message.connect(lambda msg, t=tab: self._status_from(t, msg))
            if hasattr(tab, "busy"):
                tab.busy.connect(self.busy_bar.setVisible)
            if hasattr(tab, "motor_published"):
                tab.motor_published.connect(self._on_motor_published)
        self.tabs.tabBar().hide()  # the sidebar navigates; the pages and their wiring stay as they were
        self.course = self.tabs.widget(COURSE_INDEX)
        self.course.open_tab.connect(self.open_tab)
        self.help_buttons: list[QToolButton] = []
        self.sidebar = self._build_sidebar()
        self.header = self._build_header()
        central = QWidget()
        central.setObjectName("central")
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self.sidebar)
        work = QWidget()
        work.setObjectName("workspace")
        col = QVBoxLayout(work)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(self.header)
        pages = QWidget()
        pl = QVBoxLayout(pages)
        pl.setContentsMargins(10, 6, 10, 2)
        pl.addWidget(self.tabs)
        col.addWidget(pages, 1)
        row.addWidget(work, 1)
        self.setCentralWidget(central)
        self.tabs.currentChanged.connect(self._on_workspace)
        self.tabs.currentChanged.connect(lambda _k: self._focus_page())
        external_legends(self.tabs)  # legends above the plots, never over a curve
        flexible_plots(self.tabs)
        inspect_plots(self.tabs)  # crosshair + readout in the axis units on every plot
        import pyqtgraph as pg

        for k, hint in EMPTY_HINTS.items():
            for pw in self.tabs.widget(k).findChildren(pg.PlotWidget):
                empty_state(pw, hint)
        for pw in self.tabs.findChildren(pg.PlotWidget):
            theme.style_plot(pw)  # plots built after theme.apply: titles, ticks and axes of the design system
        self._build_menu()
        self._export_worker: CoreWorker | None = None
        self.group = "Groupe ME3"
        # tab 2 → tab 3: the efficiency map uses the drive settings and boundary of the envelope
        env_tab, eff_tab = self.tabs.widget(1), self.tabs.widget(2)
        if hasattr(env_tab, "envelope_done") and hasattr(eff_tab, "on_envelope"):
            env_tab.envelope_done.connect(eff_tab.on_envelope)
            if env_tab.envelope is not None:
                eff_tab.on_envelope(env_tab.envelope)
        # tabs 2, 3 → tab 4: the vehicle uses the envelope and the loss map; its cycle goes back to tab 3
        veh_tab = self.tabs.widget(3)
        if hasattr(veh_tab, "on_envelope"):
            env_tab.envelope_done.connect(veh_tab.on_envelope)
            eff_tab.map_done.connect(veh_tab.on_map)
            veh_tab.loss_settings_provider = eff_tab.settings
            veh_tab.cycle_points.connect(eff_tab.set_cycle_points)
        # tab 4 → tab 5: the thermal model is fed by the cycle losses
        th_tab = self.tabs.widget(4)
        if hasattr(th_tab, "on_cycle") and hasattr(veh_tab, "simulation_done"):
            veh_tab.simulation_done.connect(th_tab.on_cycle)
        # tab 7: the optimisation problem is assembled from tabs 1–5; a chosen design goes back to them
        opt_tab = self.tabs.widget(6)
        if hasattr(opt_tab, "problem_provider"):
            opt_tab.problem_provider = self.optimisation_problem
            opt_tab.load_design.connect(self.load_design)
        self._compact_user: bool | None = None  # None: automatic (by window width)
        self._style_shell()
        self._on_workspace(self.tabs.currentIndex())
        self.refresh_status()
        self.tabs.setFocus()  # the window opens on the workspace, not on a sidebar button

    # --- shell: sidebar and header -------------------------------------------------

    def _build_sidebar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("sidebar")
        bar.setFixedWidth(SIDEBAR_WIDTH)
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(0, 14, 0, 10)
        lay.setSpacing(0)
        brand = QHBoxLayout()
        brand.setContentsMargins(14, 0, 10, 6)
        brand.setSpacing(10)
        self.logo = QLabel()
        self.logo.setFixedSize(30, 30)
        brand.addWidget(self.logo, 0, Qt.AlignmentFlag.AlignTop)
        words = QVBoxLayout()
        words.setSpacing(0)
        self.wordmark = QLabel(PRODUCT)
        self.wordmark.setObjectName("wordmark")
        wf = self.wordmark.font()
        wf.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 97)
        self.wordmark.setFont(wf)
        self.subtitle = QLabel(PRODUCT_SUBTITLE.replace(" RESEARCH", "\nRESEARCH"))
        self.subtitle.setObjectName("subtitle")
        f = self.subtitle.font()
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
        self.subtitle.setFont(f)
        words.addWidget(self.wordmark)
        words.addWidget(self.subtitle)
        brand.addLayout(words, 1)
        lay.addLayout(brand)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: list[QToolButton] = [None] * self.tabs.count()  # type: ignore[list-item]
        self.nav_group_labels: list[QLabel] = []
        for group, indices in NAV_GROUPS:
            gl = QLabel(group.upper())
            gl.setObjectName("navGroup")
            gf = gl.font()
            gf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.0)
            gl.setFont(gf)
            lay.addWidget(gl)
            self.nav_group_labels.append(gl)
            for k in indices:
                lay.addLayout(self._nav_row(k))
        lay.addStretch(1)
        self.chain_note = QLabel("Un moteur, une chaîne : le moteur identifié en 01 alimente 02 à 07.")
        self.chain_note.setObjectName("chainNote")
        self.chain_note.setWordWrap(True)
        lay.addWidget(self.chain_note)
        foot = QHBoxLayout()
        foot.setContentsMargins(10, 8, 10, 0)
        self.btn_collapse = QToolButton()
        self.btn_collapse.setObjectName("collapse")
        self.btn_collapse.setToolTip("Réduire / déployer la barre latérale")
        self.btn_collapse.setIconSize(QSize(16, 16))
        self.btn_collapse.clicked.connect(lambda: self.set_sidebar_compact(not self.sidebar_compact(), user=True))
        foot.addWidget(self.btn_collapse)
        foot.addStretch(1)
        lay.addLayout(foot)
        return bar

    def _nav_row(self, k: int) -> QHBoxLayout:
        tab = self.tabs.widget(k)
        num, name = workspace_label(tab.title)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 8, 0)
        row.setSpacing(2)
        btn = QToolButton()
        btn.setObjectName("navItem")
        btn.setCheckable(True)
        btn.setText(f"{num}   {tab_label(name)}")  # « & » escaped: Qt would read it as a shortcut marker
        btn.setToolTip(f"{tab.title} — {CAPTIONS[k]} (Ctrl+{k + 1})")
        btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)  # keyboard focus ring, but a click does not leave one
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btn.setIconSize(QSize(18, 18))
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn.clicked.connect(lambda _c=False, k=k: self.tabs.setCurrentIndex(k))
        self.nav_group.addButton(btn, k)
        self.nav_buttons[k] = btn
        row.addWidget(btn, 1)
        if k < COURSE_INDEX:
            hb = QToolButton()
            hb.setObjectName("navHelp")
            hb.setText("?")
            hb.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            hb.setToolTip(f"Cours : les lois de l'onglet {tab.title} (F1)")
            hb.clicked.connect(lambda _checked=False, name=cours.TABS[k]: self.open_course(name))
            row.addWidget(hb)
            self.help_buttons.append(hb)
        act = QAction(self)
        act.setShortcut(QKeySequence(f"Ctrl+{k + 1}"))
        act.triggered.connect(lambda _c=False, k=k: self.tabs.setCurrentIndex(k))
        self.addAction(act)
        return row

    def _build_header(self) -> QFrame:
        head = QFrame()
        head.setObjectName("header")
        lay = QHBoxLayout(head)
        lay.setContentsMargins(18, 7, 14, 7)
        lay.setSpacing(12)
        line = QHBoxLayout()
        line.setSpacing(10)
        self.ws_index = QLabel("")
        self.ws_index.setObjectName("wsIndex")
        self.ws_title = QLabel("")
        self.ws_title.setObjectName("wsTitle")
        self.ws_caption = ElidedLabel("")
        self.ws_caption.setObjectName("wsCaption")
        # one line: the caption takes the room left and elides itself (full text in its tooltip), so the
        # header never imposes its width or a second line on the window
        line.addWidget(self.ws_index, 0, Qt.AlignmentFlag.AlignBaseline)
        line.addWidget(self.ws_title, 0, Qt.AlignmentFlag.AlignBaseline)
        line.addWidget(self.ws_caption, 1, Qt.AlignmentFlag.AlignBaseline)
        lay.addLayout(line, 1)
        self.motor_context = QLabel("")
        self.motor_context.setObjectName("motorContext")
        self.motor_context.setToolTip("Moteur utilisé par toute la chaîne (identifié à l'onglet 1)")
        self.motor_context.setMaximumWidth(MOTOR_CONTEXT_WIDTH)
        self.motor_demo = chip("démo")
        self.motor_demo.setToolTip("Le moteur vient de données synthétiques ou de démonstration")
        lay.addWidget(self.motor_context, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self.motor_demo, 0, Qt.AlignmentFlag.AlignVCenter)
        self.btn_ws_course = QToolButton()
        self.btn_ws_course.setObjectName("headerAction")
        self.btn_ws_course.setText("Cours")
        self.btn_ws_course.setToolTip("Les lois de cet espace de travail, dans l'onglet Cours (F1)")
        self.btn_ws_course.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_ws_course.clicked.connect(self.course_for_current_tab)
        self.btn_ws_report = QToolButton()
        self.btn_ws_report.setObjectName("headerAction")
        self.btn_ws_report.setText("Rapport PDF")
        self.btn_ws_report.setToolTip("Rapport PDF de toute la session (Fichier → Exporter PDF…, Ctrl+P)")
        self.btn_ws_report.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        for b in (self.btn_ws_course, self.btn_ws_report):
            b.setIconSize(QSize(16, 16))
            lay.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
        return head

    def _style_shell(self) -> None:
        """Icons of the shell in the colours of the current theme."""
        pal = theme.palette()
        self.logo.setPixmap(glyphs.logo(pal["primary"], pal["text"], 30))
        self.wordmark.setText(f"EV<span style='color:{pal['primary']}'>-</span>LAB")
        for k, btn in enumerate(self.nav_buttons):
            btn.setIcon(glyphs.icon(glyphs.WORKSPACE_GLYPHS[k], pal["muted"], 18, active=pal["primary"]))
        self.btn_ws_course.setIcon(glyphs.icon("help", pal["text"], 16))
        self.btn_ws_report.setIcon(glyphs.icon("report", pal["text"], 16))
        self.btn_collapse.setIcon(glyphs.icon("expand" if self.sidebar_compact() else "collapse", pal["muted"], 16))

    def _on_workspace(self, k: int) -> None:
        """A workspace is shown: check its sidebar entry and write the header."""
        if k < 0:
            return
        tab = self.tabs.widget(k)
        num, name = workspace_label(tab.title)
        self.nav_buttons[k].setChecked(True)
        self.ws_index.setText(num)
        self.ws_title.setText(name)
        self.ws_caption.setText(CAPTIONS[k])
        self.btn_ws_course.setVisible(k != COURSE_INDEX)

    def _focus_page(self) -> None:
        """After a click in the sidebar, keyboard focus goes to the workspace shown (not the button)."""
        fw = QApplication.focusWidget()
        if fw is None or (isinstance(fw, QToolButton) and fw.objectName() in ("navItem", "navHelp", "collapse")):
            self.tabs.currentWidget().setFocus()

    def sidebar_compact(self) -> bool:
        return self.sidebar.width() <= SIDEBAR_COMPACT

    def set_sidebar_compact(self, compact: bool, user: bool = False) -> None:
        """Icons-only sidebar (narrow windows) or full sidebar; `user`: an explicit choice, kept on resize."""
        if user:
            self._compact_user = compact
        self.sidebar.setFixedWidth(SIDEBAR_COMPACT if compact else SIDEBAR_WIDTH)
        style = Qt.ToolButtonStyle.ToolButtonIconOnly if compact else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        for btn in self.nav_buttons:
            btn.setToolButtonStyle(style)
        for w in (self.wordmark, self.subtitle, self.chain_note, *self.nav_group_labels, *self.help_buttons):
            w.setVisible(not compact)
        self._style_shell()

    def showEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().showEvent(event)
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, self._focus_page)  # after Qt has given the first focus: start in the workspace

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().resizeEvent(event)
        if self._compact_user is None and hasattr(self, "sidebar"):
            compact = self.width() < AUTO_COMPACT_BELOW
            if compact != self.sidebar_compact():
                self.set_sidebar_compact(compact)

    def show_for_screen(self) -> None:
        """Show the window: maximised on a small screen (laptop), else at its default size."""
        screen = self.screen() or QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen is not None else None
        if avail is not None and opens_maximised(avail.width(), avail.height()):
            self.showMaximized()
        else:
            self.show()

    # --- theme ---------------------------------------------------------------------

    def set_theme(self, name: str) -> None:
        """Switch to the light or dark theme now and remember it (QSettings)."""
        theme.apply(QApplication.instance(), name)
        theme.save(name)
        self.theme_actions[name].setChecked(True)
        self._style_shell()
        for k in range(self.tabs.count()):
            tab = self.tabs.widget(k)
            if hasattr(tab, "on_theme_changed"):
                tab.on_theme_changed()

    # --- course (tab 8) -------------------------------------------------------------

    def open_course(self, tab: str | None = None) -> bool:
        """Show tab 8 at the page of a tab (identification … optimisation), or at the introduction (None)."""
        self.tabs.setCurrentIndex(COURSE_INDEX)
        if tab is None:
            return self.course.show_page(cours.PAGES[0].slug)
        return self.course.show_tab_page(tab)

    def course_for_current_tab(self) -> bool:
        """F1: the course page of the tab on screen (tab 8 stays where it is)."""
        k = self.tabs.currentIndex()
        if k == COURSE_INDEX:
            return False
        return self.open_course(cours.TABS[k])

    def _export_course_dialog(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Exporter le cours", COURSE_PDF_NAME, "PDF (*.pdf)")
        if path:
            self.export_course(path)

    def export_course(self, path) -> Path | None:
        """Write the whole course (tab 8) as a PDF: title page and every page, with the motor of the chain."""
        from PySide6.QtCore import Qt

        from evlab.gui.cours_pdf import export_course_pdf

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            out = export_course_pdf(path, self.session.motor, ex=self.course.ex)
        except (OSError, ValueError) as exc:
            self.statusBar().showMessage(f"Échec de l'export du cours : {exc}")
            self.export_failed.emit(str(exc))
            return None
        finally:
            QApplication.restoreOverrideCursor()
        self.statusBar().showMessage(f"Cours exporté : {out}")
        self.export_done.emit(out)
        return out

    def open_tab(self, name: str) -> None:
        """Switch to a tab by its name in io.cours.TABS (a link « → Ouvrir l'onglet N » of the course)."""
        self.tabs.setCurrentIndex(cours.TABS.index(name))

    # --- reports -------------------------------------------------------------------

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu("Fichier")
        self.act_pdf = QAction("Exporter PDF…", self)
        self.act_pdf.setShortcut(QKeySequence("Ctrl+P"))
        self.act_pdf.triggered.connect(lambda: self._export_dialog("pdf"))
        self.act_excel = QAction("Exporter Excel…", self)
        self.act_excel.setShortcut(QKeySequence("Ctrl+E"))
        self.act_excel.triggered.connect(lambda: self._export_dialog("xlsx"))
        self.act_course_pdf = QAction("Exporter le cours en PDF…", self)
        self.act_course_pdf.triggered.connect(self._export_course_dialog)
        act_quit = QAction("Quitter", self)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        menu.addAction(self.act_pdf)
        menu.addAction(self.act_excel)
        menu.addAction(self.act_course_pdf)
        menu.addSeparator()
        menu.addAction(act_quit)
        view = self.menuBar().addMenu("Affichage")
        aide = self.menuBar().addMenu("Aide")
        self.act_course = QAction("Cours", self)
        self.act_course.setToolTip("Onglet 8 · Cours : les lois de chaque onglet, dans la notation du cours")
        self.act_course.triggered.connect(lambda: self.open_course(None))
        self.act_course_tab = QAction("Cours de l'onglet affiché", self)
        self.act_course_tab.setShortcut(QKeySequence(QKeySequence.StandardKey.HelpContents))  # F1
        self.act_course_tab.triggered.connect(self.course_for_current_tab)
        aide.addAction(self.act_course)
        aide.addAction(self.act_course_tab)
        group = QActionGroup(self)
        group.setExclusive(True)
        self.theme_actions: dict[str, QAction] = {}
        for name in theme.THEMES:
            act = QAction(theme.THEME_LABELS[name], self, checkable=True)
            act.setChecked(name == theme.current())
            act.triggered.connect(lambda _checked=False, n=name: self.set_theme(n))
            group.addAction(act)
            view.addAction(act)
            self.theme_actions[name] = act
        self.btn_ws_report.clicked.connect(self.act_pdf.trigger)
        tab1 = self.tabs.widget(0)
        if hasattr(tab1, "btn_pdf"):
            tab1.btn_pdf.setEnabled(True)
            tab1.btn_pdf.setToolTip("Rapport PDF de toute la session (menu Fichier)")
            tab1.btn_pdf.clicked.connect(self.act_pdf.trigger)

    def _export_dialog(self, kind: str) -> None:
        group, ok = QInputDialog.getText(self, "Rapport", "Groupe / auteurs :", text=self.group)
        if not ok:
            return
        self.group = group or self.group
        name = f"ev_traction_{dt.date.today():%Y%m%d}.{kind}"
        filt = "PDF (*.pdf)" if kind == "pdf" else "Excel (*.xlsx)"
        path, _ = QFileDialog.getSaveFileName(self, "Exporter", name, filt)
        if path:
            self.export(kind, path, self.group)

    def snapshot(self, group: str):
        """io.snapshot.Snapshot of the current tabs (results not computed yet are left None)."""
        from evlab.core import winding as wd
        from evlab.io.snapshot import Snapshot

        t1, t2, t3, t4, t5, t6, t7 = (self.tabs.widget(i) for i in range(7))
        motor = self.session.motor
        dset, lset = t2.settings(), t3.settings()
        env = t2.envelope if t2.envelope is not None and t2.envelope.settings == dset else None
        emap = t3.emap if t3.emap is not None and t3.emap.envelope is env and t3.emap.settings == lset else None
        sizing = res = cycle = None
        if getattr(t4, "result", None) is not None:
            sizing, res, cycle, _, _ = t4.result
        thermal = t5.result if t5.result is not None and t5.cycle is not None and t5.cycle[0] is res else None
        return Snapshot(
            group=group, date=dt.date.today(), motor=motor, drive_settings=dset, loss_settings=lset,
            thermal_params=t5.params(), winding=t6.winding or wd.Winding(36, 4, 3, 7),
            identification=t1.result, envelope=env, emap=emap,
            vehicle=t4.vehicle() if cycle is not None else None, sizing=sizing, drive_result=res, cycle=cycle,
            thermal=thermal, insulation_class=t5.combo_class.currentData(), n_thermal_cycles=t5.spin_cycles.value(),
            pareto=t7.result,
        )

    def export(self, kind: str, path, group: str) -> bool:
        """Write the PDF report ("pdf") or the Excel workbook ("xlsx") in a worker thread."""
        from evlab.io import excel, report
        from evlab.io.snapshot import complete

        try:
            snap = self.snapshot(group)
        except ValueError as exc:
            self.statusBar().showMessage(f"Export impossible : {exc}")
            self.export_failed.emit(str(exc))
            return False
        build = report.build_report if kind == "pdf" else excel.build_workbook
        worker = CoreWorker(lambda progress: build(complete(snap), Path(path)))
        worker.signals.finished.connect(self._export_ok)
        worker.signals.failed.connect(self._export_ko)
        self._export_worker = worker
        self.busy_bar.setVisible(True)
        self.statusBar().showMessage(f"Export {kind.upper()} en cours…")
        QThreadPool.globalInstance().start(worker)
        return True

    def _export_ok(self, path) -> None:
        self.busy_bar.setVisible(False)
        self.statusBar().showMessage(f"Exporté : {path}")
        self.export_done.emit(path)

    def _export_ko(self, message: str) -> None:
        self.busy_bar.setVisible(False)
        self.statusBar().showMessage(f"Échec de l'export : {message}")
        self.export_failed.emit(message)

    def optimisation_problem(self):
        """core.optimise.Problem from the current state of tabs 1 to 5 (raises ValueError)."""
        from evlab.core import optimise

        env_tab, eff_tab, veh_tab, th_tab = (self.tabs.widget(i) for i in (1, 2, 3, 4))
        if getattr(veh_tab, "result", None) is None:
            raise ValueError("simulez d'abord le cycle dans l'onglet 4 · Véhicule & WLTC")
        _sizing, _res, cycle, _emap, _veh = veh_tab.result
        return optimise.Problem(
            motor=self.session.motor, drive=env_tab.settings(), loss_settings=eff_tab.settings(),
            vehicle=veh_tab.vehicle(), cycle=cycle, thermal=th_tab.params(),
            insulation_class=th_tab.combo_class.currentData(), n_thermal_cycles=th_tab.spin_cycles.value(),
        )

    def load_design(self, base_motor, design) -> None:
        """Load an optimised design into every tab: rewound motor, V/f law of tab 2, gear ratio of tab 4."""
        from evlab.core import optimise

        env_tab, veh_tab = self.tabs.widget(1), self.tabs.widget(3)
        motor = optimise.rewound(base_motor, design.k_n)
        env_tab.spin_boost.setValue(design.boost)
        env_tab.spin_margin.setValue(100.0 * design.margin)
        veh_tab.spin_g.setValue(design.gear_ratio)  # kept as the user's ratio, not re-proposed
        self.session.set_motor(motor)
        self._on_motor_published(motor)

    def _status_from(self, tab, message: str) -> None:
        """Show a tab's message only if that tab is visible (background recomputes stay quiet)."""
        if self.tabs.currentWidget() is tab:
            self.statusBar().showMessage(message)

    def _on_motor_published(self, _motor) -> None:
        """Tab 1 published a motor: update the status bar and let the other tabs recompute."""
        self.refresh_status(keep_message=True)
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if hasattr(tab, "on_motor_changed"):
                tab.on_motor_changed()

    def refresh_status(self, keep_message: bool = False) -> None:
        """Show which motor the whole chain is using (window title and status bar)."""
        m = self.session.motor
        demo = " (démo)" if m.is_demo else ""
        self.motor_text = f"Moteur : {m.source}{demo}"
        self.setToolTip(self.motor_text)
        if hasattr(self, "motor_context"):
            full = f"Moteur · {m.source}"
            fm = self.motor_context.fontMetrics()
            self.motor_context.setText(fm.elidedText(full, Qt.TextElideMode.ElideRight, MOTOR_CONTEXT_WIDTH - 22))
            self.motor_context.setToolTip(f"{full}{demo} — moteur utilisé par toute la chaîne (onglet 1)")
            self.motor_demo.setVisible(m.is_demo)
        if not keep_message:
            self.statusBar().showMessage(self.motor_text)
