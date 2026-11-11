"""Course pages of tab 8 « 8 · Cours »: page list, Markdown files, worked examples, rendering.

The pages are French Markdown files in evlab/docs/cours/ (package data, read with
importlib.resources, so they are found from the source tree and from the PyInstaller
build). Placeholders are filled with numbers from core.cours_valeurs:
  {{ex:clé}}       a worked example (reference motor or démo files)
  {{moteur:clé}}   a live value of the motor the chain uses
An optional format follows a second colon: N significant digits (default 3), fK = K
decimals, i = integer, o = order of magnitude « 10ⁿ », a leading s = explicit sign.
Hidden answers are written
  ??? Voir la réponse
  text
  ???
and shown as a link evlab://reponse/<page>/<n> until opened. Links: evlab://onglet/<tab>,
evlab://page/<page>.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

from evlab.core import cours_valeurs as cv
from evlab.core import identification as ident
from evlab.core.session import MotorParams
from evlab.core.thermal import order_of_magnitude
from evlab.io import demo_data
from evlab.io.cycles import load_cycle
from evlab.io.format import fr, fr_fixed, power_of_ten
from evlab.io.loaders import load_bench_tests, load_load_points, nameplate, reference_motor
from evlab.io.paths import data_dir

PACKAGE = "evlab.docs.cours"
NO_MOTOR = "— identifiez d'abord un moteur (onglet 1)"


@dataclass(frozen=True)
class Page:
    """A course page: file stem, short id (links), title, and the tab it explains (None for the others)."""

    stem: str
    slug: str
    title: str
    tab: str | None = None


PAGES = (
    Page("00_introduction", "introduction", "Introduction"),
    Page("01_identification", "identification", "1 · Identification", "identification"),
    Page("02_enveloppe", "enveloppe", "2 · Enveloppe", "enveloppe"),
    Page("03_rendement", "rendement", "3 · Rendement", "rendement"),
    Page("04_vehicule", "vehicule", "4 · Véhicule & WLTC", "vehicule"),
    Page("05_thermique", "thermique", "5 · Thermique", "thermique"),
    Page("06_bobinage", "bobinage", "6 · Bobinage", "bobinage"),
    Page("07_optimisation", "optimisation", "7 · Optimisation", "optimisation"),
    Page("90_hypotheses", "hypotheses", "Hypothèses et limites"),
    Page("91_glossaire", "glossaire", "Glossaire des symboles"),
    Page("92_notation", "notation", "Notation : cours ↔ application"),
    Page("93_validation", "validation", "Validation"),
    Page("94_bibliographie", "bibliographie", "Bibliographie"),
)
TABS = ("identification", "enveloppe", "rendement", "vehicule", "thermique", "bobinage", "optimisation", "cours")
_PLACEHOLDER = re.compile(r"\{\{(ex|moteur):([a-z0-9_]+)(?::([a-z0-9]+))?\}\}")
_ANSWER = re.compile(r"^\?\?\? Voir la réponse\n(.*?)\n\?\?\?$", re.S | re.M)
LINK = re.compile(r"\]\((evlab://[^)]+)\)")


def page(slug: str) -> Page:
    """The page with this id (ValueError if unknown)."""
    for p in PAGES:
        if p.slug == slug:
            return p
    raise ValueError(f"page de cours inconnue : {slug!r}")


def page_for_tab(tab: str) -> Page:
    """The course page that explains a tab (identification … optimisation)."""
    for p in PAGES:
        if p.tab == tab:
            return p
    raise ValueError(f"aucune page de cours pour l'onglet {tab!r}")


def source(slug: str) -> str:
    """Markdown source of a page (with its placeholders)."""
    return resources.files(PACKAGE).joinpath(page(slug).stem + ".md").read_text(encoding="utf-8")


def _records(bench) -> ident.TestRecords:
    plate = nameplate(bench.meta)
    return ident.TestRecords(dc=bench.dc, t_hot_k=bench.winding_temperature_k, no_load=bench.no_load,
                             locked=bench.locked, pole_pairs=plate.pole_pairs, v_rated=plate.v_phase,
                             f_rated=plate.f, p_mech=None)


def donnees_demo() -> cv.DonneesDemo:
    """The démo files of data/ (noisy), the same files generated without noise, and the démo cycle."""
    d = data_dir()
    bench = load_bench_tests(d / demo_data.BENCH_FILE)
    points = load_load_points(d / demo_data.LOAD_FILE)
    b0_text, l0_text = demo_data.demo_csv_texts(demo_data.DemoSpec(noise=0.0))
    bench0 = load_bench_tests("sans_bruit_demo.csv", text=b0_text)
    points0 = load_load_points("sans_bruit_demo.csv", text=l0_text)
    return cv.DonneesDemo(records=_records(bench), points=points.points, records_sans_bruit=_records(bench0),
                          points_sans_bruit=points0.points, reference=reference_motor(bench.meta),
                          noise=demo_data.NOISE,
                          cycle=load_cycle(d / demo_data.CYCLE_FILE))


@lru_cache(maxsize=1)
def exemples() -> dict[str, float]:
    """Every example number, computed once by core.cours_valeurs (a few seconds: envelope, map, cycle)."""
    return cv.exemples(donnees_demo())


def format_value(value: float | str, spec: str | None) -> str:
    """French display of a placeholder value (see the module docstring for `spec`)."""
    if isinstance(value, str):
        return value
    if value is None or not math.isfinite(value):
        return "—"
    signed = bool(spec) and spec.startswith("s")
    spec = spec[1:] if signed else spec
    if spec == "i":
        text = str(int(round(value)))
    elif spec == "o":
        return power_of_ten(order_of_magnitude(value))
    elif spec and spec.startswith("f"):
        text = fr_fixed(value, int(spec[1:]))
    else:
        text = fr(value, int(spec) if spec else 3)
    if text.startswith("-"):
        text = "−" + text[1:]
    elif signed and value > 0:
        text = "+" + text
    return text


def _fill(text: str, ex: dict, moteur: dict | None, slug: str) -> str:
    def sub(m: re.Match) -> str:
        kind, key, spec = m.groups()
        table = ex if kind == "ex" else (moteur or {})
        if key not in table:
            raise KeyError(f"page {slug} : valeur inconnue {{{{{kind}:{key}}}}}")
        return format_value(table[key], spec)
    return _PLACEHOLDER.sub(sub, text)


def _without_motor(text: str) -> str:
    """Replace the body of « Avec votre moteur » by the no-motor message."""
    return re.sub(r"(## Avec votre moteur\n)(.*?)(?=\n## |\Z)", lambda m: m.group(1) + "\n" + NO_MOTOR + "\n", text, flags=re.S)


def rendre(slug: str, moteur: MotorParams | None, ouvertes: frozenset[int] | set[int] = frozenset(),
           ex: dict | None = None) -> str:
    """Rendered Markdown of a page: numbers filled, answers hidden except those in `ouvertes`."""
    text = source(slug)
    values = cv.valeurs_moteur(moteur)
    if values is None:
        text = _without_motor(text)
    text = _fill(text, exemples() if ex is None else ex, values, slug)
    counter = iter(range(1, 1000))

    def answer(m: re.Match) -> str:
        n = next(counter)
        if n in ouvertes:
            body = "\n".join("> " + line for line in m.group(1).splitlines())
            return f"[▾ Masquer la réponse](evlab://reponse/{slug}/{n})\n\n{body}"
        return f"[▸ Voir la réponse](evlab://reponse/{slug}/{n})"
    return _ANSWER.sub(answer, text)


def n_reponses(slug: str) -> int:
    """Number of hidden answers of a page."""
    return len(_ANSWER.findall(source(slug)))


def liens(text: str) -> list[str]:
    """Every evlab:// link of a rendered page."""
    return LINK.findall(text)


def lien_valide(url: str) -> bool:
    """True if an evlab:// link has a target (a tab, a page, or an answer of an existing page)."""
    parts = url.removeprefix("evlab://").split("/")
    try:
        if parts[0] == "onglet" and len(parts) == 2:
            return parts[1] in TABS
        if parts[0] == "page" and len(parts) == 2:
            page(parts[1])
            return True
        if parts[0] == "reponse" and len(parts) == 3:
            return 1 <= int(parts[2]) <= n_reponses(parts[1])
    except ValueError:
        return False
    return False


# --- table of contents and search (accents and case ignored) -------------------------------------

_HEADING = re.compile(r"^(##|###) (.+)$", re.M)
_SOURCE_NOISE = re.compile(r"\{\{[^}]*\}\}|[*`#|>\[\]]|\(evlab://[^)]*\)")


def titres(slug: str) -> list[tuple[int, str]]:
    """(level 2 or 3, text) of the « ## » and « ### » headings of a page, in order (table of contents)."""
    return [(len(m.group(1)), m.group(2).strip()) for m in _HEADING.finditer(source(slug))]


def replier(text: str) -> str:
    """Lower case without accents, ONE character per character (positions stay valid): « Décrochage » → « decrochage »."""
    out = []
    for c in text:
        base = unicodedata.normalize("NFD", c)[0]
        low = base.lower()
        out.append(low[0] if low else c)
    return "".join(out)


def mots_recherche(query: str) -> list[str]:
    """The distinct folded words of a search (2 characters or more)."""
    seen: list[str] = []
    for w in replier(query).split():
        if len(w) >= 2 and w not in seen:
            seen.append(w)
    return seen


def rechercher(query: str) -> list[tuple[str, int]]:
    """Pages that contain every word of `query` (accents and case ignored), with the number of occurrences."""
    words = mots_recherche(query)
    if not words:
        return []
    out = []
    for p in PAGES:
        text = replier(_SOURCE_NOISE.sub(" ", source(p.slug)))
        counts = [text.count(w) for w in words]
        if all(counts):
            out.append((p.slug, sum(counts)))
    return out
