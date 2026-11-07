"""A4 French PDF report of the session (reportlab), built from a Snapshot.

Sections: title block (group, date); 1 identification; 2 envelope and efficiency;
3 cycle and KPIs; 4 thermal summary; 5 winding factors; 6 optimisation; an
assumptions box; a footer on every page saying which values are démo.
Every number comes from core/ through the Snapshot; this module only formats
(decimal comma) and lays out. Figures are drawn with matplotlib (io.figures).
Fonts: DejaVu Sans from matplotlib's data (Ω, η, ν, superscripts), no new dependency.
"""

from __future__ import annotations

import io
import math
import os
from pathlib import Path

import matplotlib
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from evlab.core import losses
from evlab.core import optimise as op
from evlab.core import thermal
from evlab.core import winding as wd
from evlab.io import figures
from evlab.io.format import fr, fr_fixed, fr_pct
from evlab.io.notes import R1_ZERO_NOTE
from evlab.io.snapshot import Snapshot

T_ZERO_C = 273.15
RPM = 60.0 / (2.0 * math.pi)
FONT, FONT_B = "DejaVuSans", "DejaVuSans-Bold"
SUPERSCRIPT = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")
_fonts_done = False


def _register_fonts() -> None:
    global _fonts_done
    if _fonts_done:
        return
    ttf = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
    pdfmetrics.registerFont(TTFont(FONT, os.path.join(ttf, "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont(FONT_B, os.path.join(ttf, "DejaVuSans-Bold.ttf")))
    registerFontFamily(FONT, normal=FONT, bold=FONT_B, italic=FONT, boldItalic=FONT_B)  # <b> in paragraphs
    _fonts_done = True


def _styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle("base", fontName=FONT, fontSize=8.5, leading=11, alignment=TA_LEFT)
    return {
        "base": base,
        "title": ParagraphStyle("title", parent=base, fontName=FONT_B, fontSize=15, leading=19),
        "sub": ParagraphStyle("sub", parent=base, fontSize=9.5, textColor=colors.HexColor("#555555")),
        "h": ParagraphStyle("h", parent=base, fontName=FONT_B, fontSize=10.5, leading=14, spaceBefore=6,
                            spaceAfter=3, textColor=colors.HexColor("#1b4fa8")),
        "small": ParagraphStyle("small", parent=base, fontSize=7.5, leading=9.5),
        "box": ParagraphStyle("box", parent=base, fontSize=7.5, leading=9.8),
    }


def _table(rows: list[list[str]], widths: list[float], bold_last: bool = False) -> Table:
    t = Table(rows, colWidths=[w * cm for w in widths], hAlign="LEFT")
    style = [
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTNAME", (0, 0), (-1, 0), FONT_B),
        ("FONTSIZE", (0, 0), (-1, -1), 7.8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef1f6")),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#9aa4b5")),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#d9dce1")),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    if bold_last:
        style.append(("FONTNAME", (0, -1), (-1, -1), FONT_B))
    t.setStyle(TableStyle(style))
    return t


def _image(fig, width_cm: float) -> Image:
    w, h = fig.get_size_inches()
    img = Image(io.BytesIO(figures.png_bytes(fig)), width=width_cm * cm, height=width_cm * cm * h / w)
    img.hAlign = "LEFT"
    return img


def _vt(x: float, pct: float | None) -> str:
    return fr(x) + (f" ({fr_pct(pct)})" if pct is not None else "")


def kpi_strings(s: Snapshot) -> dict[str, str]:
    """The KPI strings printed in the report (also used by the tests)."""
    out = {}
    if s.envelope is not None:
        e = s.envelope
        out["base_speed"] = f"{fr_fixed(e.base_speed * RPM, 0)} tr/min"
        out["p_max"] = f"{fr(e.p_max / 1000)} kW"
    if s.drive_result is not None:
        sm = s.drive_result.summary
        out["wh_per_km"] = f"{fr(sm.wh_per_km)} Wh/km"
        out["distance"] = f"{fr(sm.distance_m / 1000)} km"
        out["regen"] = f"{fr_fixed(sm.regen_percent, 1)} %"
    if s.sizing is not None:
        out["pmr"] = f"{fr(s.sizing.pmr)} W/kg"
    if s.thermal is not None:
        out["t_max"] = f"{fr_fixed(s.thermal.summary.t_max - T_ZERO_C, 1)} °C"
    out["kw1"] = fr_fixed(wd.winding_factor(s.winding, 1), 4)
    return out


def _footer(s: Snapshot):
    demo = s.demo_items()
    text = ("Valeurs démo : " + " ; ".join(demo)) if demo else "Aucune valeur démo : données d'essai réelles"

    def draw(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont(FONT, 6.8)
        canvas.setFillColor(colors.HexColor("#b3261e") if demo else colors.HexColor("#555555"))
        y = 1.0 * cm
        lines, line = [], ""
        for word in text.split(" "):
            if pdfmetrics.stringWidth(line + " " + word, FONT, 6.8) > 15.5 * cm:
                lines.append(line)
                line = word
            else:
                line = (line + " " + word).strip()
        lines.append(line)
        for k, ln in enumerate(lines[:3]):
            canvas.drawString(2.0 * cm, y + (len(lines[:3]) - 1 - k) * 8.5, ln)
        canvas.setFillColor(colors.HexColor("#555555"))
        canvas.drawRightString(A4[0] - 2.0 * cm, y, f"EV-Traction Lab · page {doc.page}")
        canvas.restoreState()

    return draw


def _assumptions(s: Snapshot) -> list[str]:
    d, st, th = s.drive_settings, s.loss_settings, s.thermal_params
    items = [
        f"Circuit en Γ, schéma « {'TP3 (R1 en tête)' if s.motor.layout == 'tp3' else 'bornes'} » (A1) ; "
        f"source : {s.motor.source}.",
        f"Loi V/f + défluxage : boost {fr(d.boost)} V, marge {fr_fixed(100 * d.margin, 0)} % du couple de décrochage, "
        f"courant max {fr(d.i_max)} A, fréquence max {fr(d.f_max)} Hz (A16–A18).",
        f"Pertes fer de Steinmetz β = {fr(st.beta)} (A19) ; mécaniques {fr(s.motor.p_mech)} W à Ω_s, "
        f"part frottements {fr_fixed(100 * st.friction_share, 0)} % (A20)"
        + (f" ; onduleur {fr(st.inverter_fixed_w)} W + {fr(100 * st.inverter_fraction)} % (démo, A21)."
           if st.inverter else " ; pertes onduleur exclues."),
    ]
    if s.vehicle is not None:
        v = s.vehicle
        items.append(f"Véhicule{' (démo)' if v.is_demo else ''} : m = {fr(v.mass)} kg, Cx·S = {fr(v.cx_s)} m², "
                     f"Crr = {fr(v.crr)}, r = {fr(v.wheel_radius)} m, ηg = {fr_fixed(100 * v.gear_efficiency, 0)} %, "
                     f"auxiliaires {fr(v.aux_power)} W (A22) ; 0–50 km/h sans inertie tournante (A30).")
    items.append(f"Réseau thermique{' (démo)' if th.is_demo else ''} : C = {fr(th.c_w)} / {fr(th.c_s)} J/K, "
                 f"R = {fr(th.r_ws)} / {fr(th.r_sa)} K/W, ambiante {fr_fixed(th.t_ambient_k - T_ZERO_C, 0)} °C (A26) ; "
                 "durée de vie par la règle des 10 K : ordre de grandeur seulement (A28).")
    items += [f"{n}." for n in s.notes]
    items.append("Liste complète et justification des hypothèses : docs/assumptions.md.")
    return items


def build_report(s: Snapshot, path: str | Path) -> Path:
    """Write the PDF report of the snapshot to `path` and return it."""
    _register_fonts()
    st = _styles()
    path = Path(path)
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=2.0 * cm, rightMargin=2.0 * cm,
                            topMargin=1.6 * cm, bottomMargin=2.2 * cm, title="EV-Traction Lab — rapport",
                            author=s.group)
    kpi = kpi_strings(s)
    story = [Paragraph("EV-Traction Lab — rapport de laboratoire virtuel", st["title"]),
             Paragraph(f"{s.group} · {s.date.strftime('%d/%m/%Y')} · ME3 Machines électriques, ENP Alger", st["sub"]),
             Spacer(1, 6)]

    # 1 identification
    story.append(Paragraph("1. Identification du schéma équivalent", st["h"]))
    head = ["Méthode", "R1 (Ω)", "Rf (Ω)", "Xm (Ω)", "X fuites (Ω)", "R'2 (Ω)"]
    rows = [head]
    ic = s.identification
    if ic is not None:
        if ic.reference is not None:
            r = ic.reference
            rows.append([f"Référence ({r.source})", fr(r.r1), fr(r.r_fe), fr(r.x_m), fr(r.x_leak), fr(r.r2p)])
        labels = {"classical": "Formules classiques", "fit": "Optimisation (moindres carrés)"}
        for row in ic.shown:
            mm, err = ic.motor(row), ic.errors[row]
            rows.append([labels[row], fr(mm.r1)] + [_vt(getattr(mm, n), err[n])
                                                     for n in ("r_fe", "x_m", "x_leak", "r2p")])
    else:
        m = s.motor
        rows.append([f"Moteur de la session ({m.source})", fr(m.r1), fr(m.r_fe), fr(m.x_m), fr(m.x_leak), fr(m.r2p)])
    story.append(_table(rows, [5.2, 1.6, 2.4, 2.4, 2.4, 2.4], bold_last=ic is not None))
    story.append(Paragraph(f"Moteur utilisé par toute la chaîne : {s.motor.source} — V = {fr(s.motor.v_phase)} V, "
                           f"f = {fr(s.motor.f_rated)} Hz, p = {s.motor.pole_pairs}.", st["small"]))

    # 2 envelope and efficiency
    story.append(Paragraph("2. Enveloppe couple–vitesse et carte de rendement", st["h"]))
    e = s.envelope
    story.append(_image(figures.envelope_and_map(s.motor, e, s.emap), 17.0))
    eta, tb, wb = losses.best_point(s.emap)
    story.append(Paragraph(
        f"Vitesse de base {kpi['base_speed']}, fin de puissance constante "
        f"{fr_fixed(e.end_constant_power * RPM, 0)} tr/min, P max {kpi['p_max']}, couple à vitesse max "
        f"{fr(e.torque_at_max_speed)} N·m. Rendement max {fr_fixed(100 * eta, 1)} % à {fr(tb)} N·m, "
        f"{fr_fixed(wb * RPM, 0)} tr/min.", st["small"]))

    # 3 cycle
    story.append(Paragraph("3. Véhicule sur cycle", st["h"]))
    if s.drive_result is not None and s.cycle is not None:
        res, sz = s.drive_result, s.sizing
        story.append(_image(figures.cycle_figure(s.cycle, res), 17.0))
        sm = res.summary
        rows = [["Indicateur", "Valeur"],
                ["Classe WLTC (rapport puissance / masse)", f"classe {sz.wltc_class} ({kpi['pmr']})"],
                ["Rapport de réduction G", fr(s.vehicle.gear_ratio)],
                ["Distance", kpi["distance"]],
                ["Énergie batterie", f"{fr(sm.energy_j / 3600)} Wh"],
                ["Consommation", kpi["wh_per_km"]],
                ["Énergie récupérée", kpi["regen"]],
                ["Points hors enveloppe", str(sm.n_outside)]]
        story.append(_table(rows, [8.0, 5.0]))
    else:
        story.append(Paragraph("Non calculé : simuler un cycle dans l'onglet 4.", st["base"]))

    # 4 thermal
    sec = [Paragraph("4. Thermique", st["h"])]
    if thermal.stator_copper_missing(s.motor):
        sec.append(Paragraph(f"<font color='#b3261e'>{R1_ZERO_NOTE}.</font>", st["base"]))
    if s.thermal is not None:
        ts = s.thermal.summary
        fast, slow = thermal.time_constants(s.thermal_params)
        life = thermal.order_of_magnitude(ts.life_hours)
        rows = [["Indicateur", "Valeur"],
                [f"T max bobinage ({s.n_thermal_cycles} cycles enchaînés)", kpi["t_max"]],
                ["T moyenne bobinage (dernier cycle)", f"{fr_fixed(ts.t_mean - T_ZERO_C, 1)} °C"],
                [f"Marge à la classe {ts.insulation_class} "
                 f"({fr_fixed(thermal.INSULATION_CLASSES[ts.insulation_class], 0)} °C)", f"{fr_fixed(ts.margin, 1)} K"],
                ["Durée de vie de l'isolation (ordre de grandeur)",
                 "≈ 10" + str(int(round(math.log10(life)))).translate(SUPERSCRIPT) + " h"],
                ["Constantes de temps", f"{fr(fast / 60)} min et {fr(slow / 60)} min"]]
        sec.append(_table(rows, [8.0, 5.0]))
    else:
        sec.append(Paragraph("Non calculé : simuler un cycle dans l'onglet 4.", st["base"]))
    story.append(KeepTogether(sec))

    # 5 winding
    w = s.winding
    full = wd.Winding(z=w.z, poles=w.poles, m=w.m, y=w.tau)
    sec = [Paragraph(f"5. Bobinage : Z = {w.z}, 2p = {w.poles}, q = {w.q}, τ = {w.tau}, pas y = {w.y}", st["h"])]
    rows = [["ν", "kd", f"kp (y = {w.tau})", f"kw (y = {w.tau})", f"kp (y = {w.y})", f"kw (y = {w.y})"]]
    for nu in (1, 5, 7, 11, 13):
        rows.append([str(nu)] + [fr_fixed(v, 4).replace("-", "−") for v in (
            wd.distribution_factor(w, nu), wd.pitch_factor(full, nu), wd.winding_factor(full, nu),
            wd.pitch_factor(w, nu), wd.winding_factor(w, nu))])
    wt = _table(rows, [1.2, 2.4, 2.6, 2.6, 2.6, 2.6])
    wt.setStyle(TableStyle([("ALIGN", (0, 0), (0, -1), "CENTER")]))
    sec.append(wt)
    story.append(KeepTogether(sec))

    # 6 optimisation
    sec = [Paragraph("6. Optimisation de conception", st["h"])]
    pr = s.pareto
    if pr is not None and pr.front:
        best = min(pr.front, key=lambda x: x.wh_per_km)
        ch = op.kpi_changes(pr.baseline, best)
        b = pr.baseline

        def change(key):
            v, unit = ch[key]
            return "—" if not math.isfinite(v) else (fr_pct(v) if unit == "%" else f"{fr_fixed(v, 1)} K")

        rows = [["", "Base", "Optimum", "Écart"],
                ["Consommation (Wh/km)", fr(b.wh_per_km), fr(best.wh_per_km), change("wh_per_km")],
                ["0–50 km/h (s)", fr(b.t_0_50), fr(best.t_0_50), change("t_0_50")],
                ["T max bobinage (°C)", fr_fixed(b.t_winding_max - T_ZERO_C, 1),
                 fr_fixed(best.t_winding_max - T_ZERO_C, 1), change("t_winding_max")],
                ["Rapport G", fr(b.design.gear_ratio), fr(best.design.gear_ratio), ""],
                ["Boost V/f (V)", fr(b.design.boost), fr(best.design.boost), ""],
                ["Marge (%)", fr_fixed(100 * b.design.margin, 0), fr_fixed(100 * best.design.margin, 0), ""],
                ["Rebobinage k_N", fr_fixed(b.design.k_n, 3), fr_fixed(best.design.k_n, 3), ""]]
        sec.append(Table([[_table(rows, [3.7, 1.7, 1.9, 1.7]), _image(figures.pareto_figure(pr), 7.6)]],
                         colWidths=[9.2 * cm, 7.8 * cm], style=[("VALIGN", (0, 0), (-1, -1), "TOP"),
                                                                ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        sec.append(Paragraph(f"Optimum : point du front de consommation minimale. {len(pr.log)} évaluations, "
                             f"{len(pr.front)} points sur le front (évolution différentielle, balayage "
                             "ε-contrainte).", st["small"]))
    else:
        sec.append(Paragraph("Non calculée : lancer l'optimisation dans l'onglet 7.", st["base"]))
    story.append(KeepTogether(sec))

    # assumptions box
    box = [Paragraph("<b>Hypothèses principales</b>", st["box"])]
    box += [Paragraph(f"• {txt}", st["box"]) for txt in _assumptions(s)]
    frame = Table([[box]], colWidths=[17.0 * cm], style=[
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#9aa4b5")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f6f7f9")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 4)])
    story += [Spacer(1, 6), KeepTogether([frame])]

    footer = _footer(s)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return path
