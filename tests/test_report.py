"""io.report: the PDF is created, has 1–3 pages, contains the KPI strings and the démo footer."""

import re

import pytest

from evlab.io.format import fr
from evlab.io.report import build_report, kpi_strings
from fixtures.snapshot import demo_snapshot


@pytest.fixture(scope="module")
def pdf(tmp_path_factory):
    path = tmp_path_factory.mktemp("report") / "rapport.pdf"
    build_report(demo_snapshot(), path)
    return path


def _pages(data: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page(?![s\w])", data))


def test_pdf_created_with_one_to_three_pages(pdf):
    data = pdf.read_bytes()
    assert data[:5] == b"%PDF-" and data.rstrip().endswith(b"%%EOF")
    assert 1 <= _pages(data) <= 3


def test_pdf_contains_the_kpi_strings(pdf):
    pypdf = pytest.importorskip("pypdf")  # [dev] dependency: PDF text extraction
    reader = pypdf.PdfReader(str(pdf))
    assert 1 <= len(reader.pages) <= 3
    text = " ".join(p.extract_text() for p in reader.pages)
    s = demo_snapshot()
    kpi = kpi_strings(s)
    assert set(kpi) >= {"wh_per_km", "distance", "regen", "pmr", "t_max", "base_speed", "p_max", "kw1"}
    for key, value in kpi.items():
        assert value in text, f"{key}: {value!r} missing"
    assert fr(s.drive_result.summary.wh_per_km) == kpi["wh_per_km"].split(" ")[0]
    for title in ("1. Identification", "2. Enveloppe", "3. Véhicule", "4. Thermique", "5. Bobinage",
                  "6. Optimisation", "Hypothèses principales"):
        assert title in text
    assert "Valeurs démo" in text and "réseau thermique" in text
    assert "Groupe test" in text and "06/11/2026" in text


def test_missing_sections_are_reported(tmp_path):
    from dataclasses import replace

    s = replace(demo_snapshot(), pareto=None, drive_result=None, thermal=None, cycle=None, vehicle=None, sizing=None)
    path = build_report(s, tmp_path / "partiel.pdf")
    assert 1 <= _pages(path.read_bytes()) <= 3
    pypdf = pytest.importorskip("pypdf")
    text = " ".join(p.extract_text() for p in pypdf.PdfReader(str(path)).pages)
    assert "Non calculée : lancer l'optimisation" in text
    assert "Non calculé : simuler un cycle" in text
