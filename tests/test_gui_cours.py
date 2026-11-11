"""Tab 8 · Cours (pytest-qt, offscreen): pages, « ? » buttons, F1, Aide menu, links, answers, search, live values."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTabBar

from evlab.gui import main_window as mw
from evlab.gui import theme
from evlab.gui.main_window import MainWindow
from evlab.gui.tab_cours import TITLE, CoursTab
from evlab.io import cours

TIMEOUT = 60_000


@pytest.fixture
def win(qtbot):
    w = MainWindow(theme_name="light")
    qtbot.addWidget(w)
    w.resize(1280, 720)
    w.show()
    qtbot.waitExposed(w)
    return w


def _shown(qtbot, w, action, slug):
    with qtbot.waitSignal(w.course.page_shown, timeout=TIMEOUT, check_params_cb=lambda s: s == slug):
        action()
    assert w.course.current == slug and w.tabs.currentIndex() == mw.COURSE_INDEX


def test_tab_8_is_the_course(win):
    assert win.tabs.count() == 8 and win.tabs.widget(mw.COURSE_INDEX).title == TITLE == "8 · Cours"
    assert isinstance(win.course, CoursTab)
    assert [win.course.toc.topLevelItem(k).text(0) for k in range(win.course.toc.topLevelItemCount())] == \
        [p.title for p in cours.PAGES]
    assert win.course.browser.openLinks() is False and win.course.browser.openExternalLinks() is False


@pytest.mark.parametrize("k", range(7))
def test_each_help_button_opens_its_page(qtbot, win, k):
    assert len(win.help_buttons) == 7 and win.tabs.tabBar().tabButton(mw.COURSE_INDEX, QTabBar.ButtonPosition.RightSide) is None
    btn = win.help_buttons[k]
    assert btn.text() == "?" and win.tabs.widget(k).title in btn.toolTip()
    _shown(qtbot, win, btn.click, cours.page_for_tab(cours.TABS[k]).slug)
    assert win.statusBar().currentMessage() == f"Cours : {cours.page_for_tab(cours.TABS[k]).title}"


@pytest.mark.parametrize("k", (0, 3, 6))
def test_f1_opens_the_page_of_the_current_tab(qtbot, win, k):
    win.tabs.setCurrentIndex(k)
    qtbot.wait(50)
    _shown(qtbot, win, lambda: qtbot.keyClick(win, Qt.Key.Key_F1), cours.page_for_tab(cours.TABS[k]).slug)
    assert win.act_course_tab.shortcut().toString() == "F1"


def test_help_menu_opens_the_course(qtbot, win):
    menus = [a.text() for a in win.menuBar().actions()]
    assert menus == ["Fichier", "Affichage", "Aide"]
    aide = [a for a in win.menuBar().actions() if a.text() == "Aide"][0].menu()
    assert [a.text() for a in aide.actions()] == ["Cours", "Cours de l'onglet affiché"]
    _shown(qtbot, win, win.act_course.trigger, "introduction")
    assert win.course_for_current_tab() is False  # F1 on tab 8 itself stays where it is


def test_page_shows_the_examples_and_no_placeholder(qtbot, win):
    _shown(qtbot, win, lambda: win.open_course("identification"), "identification")
    text = win.course.browser.toPlainText()
    assert "{{" not in text and "???" not in text
    assert "Exemple — fichiers démo bruités (R1 = 0,40 Ω)." in text
    assert "1,77 Ω" in text and "2,000 Ω" in text  # noisy value and noise-free value


def test_answers_show_and_hide(qtbot, win):
    _shown(qtbot, win, lambda: win.open_course("identification"), "identification")
    c = win.course
    assert "on mesure 2·R_s" not in c.browser.toPlainText().replace("\n", " ")
    with qtbot.waitSignal(c.page_shown, timeout=TIMEOUT):
        assert c.follow("evlab://reponse/identification/1")
    assert "on mesure 2·R_s" in c.browser.toPlainText().replace("\n", " ")
    assert c.ouvertes["identification"] == {1}
    with qtbot.waitSignal(c.page_shown, timeout=TIMEOUT):
        c.follow("evlab://reponse/identification/1")
    assert "on mesure 2·R_s" not in c.browser.toPlainText().replace("\n", " ")


def test_every_link_routes_to_its_target(qtbot, win):
    c = win.course
    _shown(qtbot, win, lambda: win.open_course(None), "introduction")
    for p in cours.PAGES:
        for url in cours.liens(cours.rendre(p.slug, win.session.motor)):
            kind, target = url.removeprefix("evlab://").split("/", 1)
            if kind == "reponse":
                continue  # tested above
            _shown(qtbot, win, lambda: (win.tabs.setCurrentIndex(mw.COURSE_INDEX), c.show_page(p.slug)), p.slug)
            if kind == "onglet":
                assert c.follow(url)
                assert win.tabs.currentIndex() == cours.TABS.index(target)
            else:
                _shown(qtbot, win, lambda: c.follow(url), target)
    win.tabs.setCurrentIndex(mw.COURSE_INDEX)  # a tab's messages show only while it is visible
    assert not c.follow("evlab://page/nulle")
    assert "Lien sans cible" in win.statusBar().currentMessage()


def test_live_values_follow_the_identified_motor(qtbot, win):
    _shown(qtbot, win, lambda: win.open_course("identification"), "identification")
    text = win.course.browser.toPlainText()
    assert "Moteur utilisé par la chaîne : moteur de référence." in text
    assert win.motor_text == "Moteur : TD5 Ex 1"  # the status bar keeps the motor's own label
    t1 = win.tabs.widget(0)
    t1.load_demo()
    t1.radios["both"].setChecked(True)
    with qtbot.waitSignal(win.course.page_shown, timeout=TIMEOUT):
        with qtbot.waitSignal(t1.identification_done, timeout=TIMEOUT):
            t1.identify()
    text = win.course.browser.toPlainText()
    assert "Moteur utilisé par la chaîne : Identification" in text and "(démo)" in text
    assert "moteur de référence." not in text.split("Avec votre moteur")[1]


def test_search_ignores_accents_and_highlights(qtbot, win):
    c = win.course
    _shown(qtbot, win, lambda: win.open_course("enveloppe"), "enveloppe")
    c.search.setText("DECROCHAGE")  # typed: textChanged → apply_search
    shown = [c.toc.topLevelItem(k).data(0, 0x0101) for k in range(c.toc.topLevelItemCount())
             if not c.toc.topLevelItem(k).isHidden()]
    assert shown == [s for s, _ in cours.rechercher("décrochage")]
    assert "enveloppe" in shown and "glossaire" in shown and len(shown) < len(cours.PAGES)
    hidden = [c.toc.topLevelItem(k).data(0, 0x0101) for k in range(c.toc.topLevelItemCount())
              if c.toc.topLevelItem(k).isHidden()]
    assert set(hidden) == {p.slug for p in cours.PAGES} - set(shown)
    assert len(c.browser.extraSelections()) == c._highlight() > 0
    assert "occurrence(s)" in c.lbl_search.text()
    assert c.apply_search("motinexistant") == [] and c.lbl_search.text() == "Aucune page trouvée"
    c.search.clear()
    assert all(not c.toc.topLevelItem(k).isHidden() for k in range(c.toc.topLevelItemCount()))
    assert c.browser.extraSelections() == []


def test_table_of_contents_jumps_to_sections(qtbot, win):
    c = win.course
    _shown(qtbot, win, lambda: win.open_course("identification"), "identification")
    top = [c.toc.topLevelItem(k) for k in range(c.toc.topLevelItemCount())][1]
    titles = [top.child(k).text(0) for k in range(top.childCount())]
    assert titles == ["Ce que fait cet onglet", "Lois et explications", "Hypothèses", "Avec votre moteur",
                      "Questions pour s'entraîner"]
    groups = top.child(1)
    assert [groups.child(k).text(0) for k in range(groups.childCount())] == \
        ["Essais", "Schéma équivalent", "Couple et puissances", "Ajustement par moindres carrés"]
    with qtbot.waitSignal(c.page_shown, timeout=TIMEOUT):
        c._toc_clicked(groups.child(3))
    assert c.browser.verticalScrollBar().value() > 0
    assert c.browser.textCursor().block().text() == "Ajustement par moindres carrés"
    assert not c.scroll_to("titre absent")


def test_theme_switch_restyles_the_page(qtbot, win):
    _shown(qtbot, win, lambda: win.open_course("bobinage"), "bobinage")
    with qtbot.waitSignal(win.course.page_shown, timeout=TIMEOUT):
        win.set_theme("dark")
    assert theme.palette("dark")["card"] in win.course.browser.styleSheet()
    assert theme.palette("dark")["info"] in win.course.browser.document().defaultStyleSheet()
    with qtbot.waitSignal(win.course.page_shown, timeout=TIMEOUT):
        win.set_theme("light")
    assert theme.palette("light")["card"] in win.course.browser.styleSheet()


def test_tab_bar_fits_the_minimum_window(qtbot):
    w = MainWindow(theme_name="light")
    qtbot.addWidget(w)
    w.resize(*mw.MIN_SIZE)
    w.show()
    qtbot.waitExposed(w)
    bar = w.tabs.tabBar()
    assert sum(bar.tabRect(k).width() for k in range(bar.count())) <= w.tabs.width()
