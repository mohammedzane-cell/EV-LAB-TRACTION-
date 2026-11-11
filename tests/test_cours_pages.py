"""Course pages (tab 8): rendering, template, laws present in core/, example numbers = core, links, answers."""

import importlib
import math
import re
from dataclasses import replace
from importlib import resources

import numpy as np
import pytest

from evlab.core import circuit, drive, losses, optimise, thermal, vehicle, winding
from evlab.core import identification as ident
from evlab.core.session import td5_ex1
from evlab.io import cours, demo_data
from evlab.io.cycles import load_cycle
from evlab.io.loaders import load_bench_tests, load_load_points, nameplate, reference_motor
from evlab.io.paths import data_dir

TAB_PAGES = [p for p in cours.PAGES if p.tab]
PARTS = ("## Ce que fait cet onglet", "## Lois et explications", "## Hypothèses", "## Avec votre moteur",
         "## Questions pour s'entraîner")
LABELS = ("moteur de référence, sans bruit", "fichiers démo bruités (R1 = {{ex:r1_froid:2}} Ω)", "variateur démo", "véhicule démo",
          "réseau démo", "valeurs démo", "bobinage par défaut", "géométrie démo", "classe F",
          "réglages par défaut", "réglage de base")
PLACEHOLDER = re.compile(r"\{\{ex:([a-z0-9_]+)(?::[a-z0-9]+)?\}\}")


# --- rendering, files, template ---------------------------------------------------------------

def test_page_files_match_the_page_list():
    files = sorted(p.name for p in resources.files(cours.PACKAGE).iterdir() if p.name.endswith(".md"))
    assert files == sorted(p.stem + ".md" for p in cours.PAGES)
    assert [p.tab for p in TAB_PAGES] == list(cours.TABS[:7])


@pytest.mark.parametrize("p", cours.PAGES, ids=lambda p: p.slug)
@pytest.mark.parametrize("with_motor", (True, False), ids=("motor", "no_motor"))
def test_every_page_renders_without_placeholders(p, with_motor):
    text = cours.rendre(p.slug, td5_ex1() if with_motor else None)
    assert "{{" not in text and "}}" not in text and "???" not in text
    assert text.startswith("# ")
    if not with_motor and "## Avec votre moteur" in text:
        body = text.split("## Avec votre moteur")[1].split("\n## ")[0]
        assert body.strip() == cours.NO_MOTOR


@pytest.mark.parametrize("p", TAB_PAGES, ids=lambda p: p.slug)
def test_tab_pages_follow_the_template(p):
    src = cours.source(p.slug)
    positions = [src.index(part) for part in PARTS]
    assert positions == sorted(positions)
    laws = src.split("## Lois et explications")[1].split("## Hypothèses")[0]
    groups = re.findall(r"^### (.+)$", laws, re.M)
    assert len(groups) >= 2, "laws grouped under thematic headings"
    blocks = re.split(r"^#### ", laws, flags=re.M)[1:]
    assert blocks
    for b in blocks:
        for part in ("| Symbole | Signification | Unité |", "**Explication.**", "**Ce que ça montre.**",
                     "**Dans l'application.**", "**Exemple**", "**Dans le cours.**"):
            assert part in b, f"{p.slug}: « {b.splitlines()[0]} » lacks {part}"
        first = b.split("\n\n")[1]  # first paragraph after the title
        assert "`" in first, f"{p.slug}: « {b.splitlines()[0]} »: the equation comes first, in plain text"
    assert cours.n_reponses(p.slug) == 3 and src.count("**Q") == 3
    assert src.rstrip().endswith(f"(evlab://onglet/{p.tab})")


def test_identification_groups_are_the_four_requested():
    laws = cours.source("identification").split("## Lois et explications")[1].split("## Hypothèses")[0]
    assert re.findall(r"^### (.+)$", laws, re.M) == ["Essais", "Schéma équivalent", "Couple et puissances",
                                                       "Ajustement par moindres carrés"]


def test_identification_explains_the_two_iron_loss_writings():
    src = cours.source("identification")
    assert "p_fer = 3·V_s²/R_μ" in src and "3·E²/R_μ" in src and "MAS A\n§6.2, p. 96" in src
    assert "identiques quand R_s = 0" in src


def test_no_td_or_tp_citation_and_default_layout_name():
    for p in cours.PAGES:
        src = cours.source(p.slug)
        assert not re.search(r"\bT[DP]\s?\d|\bT[DP]\b", src), p.slug
        assert "TP3" not in src
    assert "disposition par défaut (R1 en premier)" in cours.source("identification")
    assert "disposition par défaut (r1 en premier)" in cours.source("notation").lower()


@pytest.mark.parametrize("p", TAB_PAGES, ids=lambda p: p.slug)
def test_every_example_names_its_data(p):
    src = cours.source(p.slug)
    labels = re.findall(r"^\*\*Exemple\*\* — (.+?)\.(?:\s)", src, re.M | re.S)
    assert len(labels) == src.count("**Exemple**")
    for line in labels:
        assert any(lab in line for lab in LABELS), f"{p.slug}: « {line} »"


def test_noisy_examples_state_r1():
    text = cours.rendre("identification", td5_ex1())
    assert "**Exemple** — fichiers démo bruités (R1 = 0,40 Ω)." in text
    assert "vient du bruit, pas de la méthode" in text


# --- laws listed in « Dans l'application » exist in core/ ----------------------------------------

def _laws(src: str):
    for seg in re.findall(r"\*\*Dans l'application\.\*\*(.*?)(?:\n\n|\Z)", src, re.S):
        for module, names in re.findall(r"`core/(\w+)\.py` :\s*((?:`[\w.]+`(?:[^;`]*?))+)", seg):
            for name in re.findall(r"`([\w.]+)`", names):
                yield module, name


@pytest.mark.parametrize("p", TAB_PAGES, ids=lambda p: p.slug)
def test_every_law_listed_exists_in_core(p):
    found = list(_laws(cours.source(p.slug)))
    assert found
    for module, name in found:
        obj = importlib.import_module(f"evlab.core.{module}")
        for part in name.split("."):
            assert hasattr(obj, part), f"{p.slug}: core/{module}.py has no {name}"
            obj = getattr(obj, part)
        assert callable(obj), f"{module}.{name}"


# --- every example number equals the core result -------------------------------------------------

def _records(b):
    pl = nameplate(b.meta)
    return ident.TestRecords(dc=b.dc, t_hot_k=b.winding_temperature_k, no_load=b.no_load, locked=b.locked,
                             pole_pairs=pl.pole_pairs, v_rated=pl.v_phase, f_rated=pl.f, p_mech=None)


@pytest.fixture(scope="module")
def expected():
    """Every example recomputed here from the core functions and the data files (not via cours_valeurs)."""
    rpm = 30 / math.pi
    m = td5_ex1()
    d = data_dir()
    b = load_bench_tests(d / demo_data.BENCH_FILE)
    lp = load_load_points(d / demo_data.LOAD_FILE)
    b0_text, l0_text = demo_data.demo_csv_texts(demo_data.DemoSpec(noise=0.0))
    b0 = load_bench_tests("x_demo.csv", text=b0_text)
    rec, rec0, ref = _records(b), _records(b0), reference_motor(b.meta)
    cycle = load_cycle(d / demo_data.CYCLE_FILE)
    e = {}

    def chain(r):
        r1c = ident.r1_from_dc(r.dc)
        r1 = r1c * (234.5 + r.t_hot_k - 273.15) / (234.5 + r.dc.temperature_k - 273.15)
        v0 = np.array([t.v_phase for t in r.no_load])
        pm = ident.mechanical_losses(v0, np.array([t.p_total - 3 * r1 * t.i_line**2 for t in r.no_load]))
        nl = min(r.no_load, key=lambda t: abs(t.v_phase - r.v_rated))
        rfe, xme = ident.no_load_branch(nl, r1, pm, method="exact", layout="tp3")
        return r1c, r1, pm, nl, rfe, xme
    r1c, r1, pm, nl, rfe, xme = chain(rec)
    _, r1_0, pm0, _, rfe0, xme0 = chain(rec0)
    rfc, xmc = ident.no_load_branch(nl, r1, pm, method="classical", layout="tp3")
    r2c, xc = ident.locked_rotor(rec.locked, r1, rec.f_rated, method="classical", layout="tp3")
    r2e, xe = ident.locked_rotor(rec.locked, r1, rec.f_rated, r_fe=rfe, x_m=xme, method="exact", layout="tp3")
    r2e0, xe0 = ident.locked_rotor(rec0.locked, r1_0, rec0.f_rated, r_fe=rfe0, x_m=xme0, method="exact", layout="tp3")
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = ident.compare_methods(rec, "both", points=lp.points, layout="tp3", reference=ref, is_demo=True)
    fit, cla = res.motor("fit"), res.motor("classical")
    op02 = circuit.operating_point(cla, 0.02)
    vcc = 0.25 * m.v_phase
    opcc = circuit.operating_point(m, 1.0, v_phase=vcc)
    r2t, xt = ident.locked_rotor(ident.LockedRotorTest(v_phase=vcc, i_line=opcc.i1, p_total=opcc.p_in, f=50.0),
                                 0.0, 50.0, method="classical", layout="tp3")
    ws = 2 * math.pi * 50 / 2
    e.update(dc_u=b.dc.v_dc, dc_i=b.dc.i_dc, dc_t=20.0, r1_froid=r1c, r1_chaud=r1, t_chaud=75.0,
             r1_hausse=100 * ((234.5 + 75) / 254.5 - 1), ref_v=230.0, ref_u=230 * math.sqrt(3), p_mec=pm,
             p_mec_ref=ref.p_mech, p_mec_sans_bruit=pm0, q0=math.sqrt((3 * nl.v_phase * nl.i_line) ** 2 - nl.p_total**2),
             p0=nl.p_total, rf_classique=rfc, xm_classique=xmc, rf_exact=rfe, xm_exact=xme, r2_classique=r2c,
             x_classique=xc, r2_exact=r2e, x_exact=xe, r2_exact_sans_bruit=r2e0, x_exact_sans_bruit=xe0,
             ref_zm_sur_z2=abs(1 / (1 / 230 + 1 / 46j)) / abs(2 + 4j), ref_e_r2_classique=100 * (r2t / 2 - 1),
             ref_e_x_classique=100 * (xt / 4 - 1), ref_i1=circuit.stator_current(m, 0.1),
             ref_cos=circuit.power_factor(m, 0.1), ref_i2=circuit.rotor_current(m, 0.1),
             ref_couple=circuit.torque(m, 0.1), ref_ws=ws, ref_ns=1500.0, ref_w=0.9 * ws, ref_n=1350.0,
             demo_n_g02=op02.omega_mech * rpm, demo_dt_g02=pm / op02.omega_mech, ref_gc=0.5,
             ref_tmax=3 * 2 * 230**2 / (2 * 4 * 2 * math.pi * 50), ref_pfer=690.0, ref_pfer_formule=690.0,
             r2_fit=fit.r2p, r2_ci_bas=res.fit.ci95["r2p"][0], r2_ci_haut=res.fit.ci95["r2p"][1],
             e_r2_classique=100 * (cla.r2p / ref.r2p - 1), demo_ref_r2=2.0, demo_ref_x=4.0, demo_ref_rf=230.0,
             demo_ref_xm=46.0, bruit_pct=2.5, n_vide=8.0)
    # tabs 2 to 7
    dset = drive.demo_settings()
    st = losses.LossSettings(winding_temperature_k=fit.r1_temperature_k)
    env_ref = drive.envelope(m, dset)
    env = drive.envelope(fit, dset)
    tg, wg = losses.default_grid(fit, env, st)
    emap = losses.efficiency_map(fit, tg, wg, dset, st, envelope=env)
    i = len(env.omega) // 2
    eta, tb, wb = losses.best_point(emap)
    ib = np.unravel_index(np.nanargmax(emap.eta), emap.eta.shape)
    veh0 = vehicle.demo_quadricycle()
    siz = vehicle.size_vehicle(fit, env, st, veh0, cycle)
    veh = replace(veh0, gear_ratio=siz.gear_ratio)
    sim = vehicle.simulate(cycle, veh, fit, env, emap, st)
    p = thermal.demo_thermal()
    pc, pf = thermal.cycle_losses(sim, emap)
    th = thermal.simulate(p, pc, pf, n_cycles=10, copper_ref_k=thermal.map_copper_temperature(emap, fit.r1_temperature_k))
    tf, ts = thermal.time_constants(p)
    tw_ss, ts_ss = thermal.steady_state(p, float(np.mean(pc)), float(np.mean(pf)))
    cool = thermal.simulate(p, np.zeros(7200), np.zeros(7200), t0_k=(tw_ss, ts_ss))
    pick = (cool.t >= 1800) & (np.mod(cool.t, 600) == 0)
    tau_fit, _ = thermal.fit_cooling_curve(cool.t[pick], np.array([circuit.copper_resistance(1.0, t) for t in cool.t_w[pick]]),
                                           1.0, 293.15, p.t_ambient_k)
    prob = optimise.Problem(fit, dset, st, veh, cycle, p, "F")
    base = optimise.evaluate(prob, prob.baseline())
    fv = vehicle.road_force(veh, 50 / 3.6, 1.0)
    e.update(ref_v_fn=230.0, ref_v_f25=115.0, ref_v_f100=230.0, ref_x_f100=8.0,
             ref_tbd_fn=float(drive.breakdown_torque(m, 50.0)), ref_tbd_f100=float(drive.breakdown_torque(m, 100.0)),
             ref_en=drive.rated_emf(m), ref_flux_f100=0.5, ref_base=env_ref.base_speed * rpm,
             ref_fin_pc=env_ref.end_constant_power * rpm, ref_pmax=env_ref.p_max, ref_wmax=env_ref.omega_max * rpm,
             ref_t_i_ex=env_ref.torque[i], ref_w_i_ex=env_ref.omega[i] * rpm, ref_f_i_ex=env_ref.f[i],
             ref_g_i_ex=env_ref.slip[i], ref_fr_i_ex=env_ref.slip[i] * env_ref.f[i], ref_flux_max=env_ref.max_flux_ratio,
             i_max=dset.i_max, marge=dset.margin, f_max=dset.f_max,
             demo_r1_tw=losses.stator_resistance(fit, st), demo_tw=75.0, beta=1.5, part_frottements=0.5,
             demo_rf_f100=fit.r_fe * 2**0.5, demo_rf=fit.r_fe, demo_pmec_w0=fit.p_mech,
             demo_pmec_2w0=fit.p_mech * (0.5 * 2 + 0.5 * 4), demo_n0=1500.0, demo_pmec=fit.p_mech,
             inv_p0=50.0, inv_k=2.0, demo_eta_max=100 * eta, demo_t_best=tb, demo_n_best=wb * rpm,
             demo_t_arbre_mid=losses.shaft_torque_limit(fit, env, st)[i], demo_t_em_mid=env.torque[i],
             demo_n_mid=env.omega[i] * rpm,
             **{f"best_{k}": getattr(emap, k)[ib] for k in ("p_cu1", "p_cu2", "p_fe", "p_mech", "p_inv", "p_out", "p_in", "f", "i1")},
             best_eta_bilan=100 * emap.p_out[ib] / emap.p_in[ib],
             veh_m=veh.mass, veh_cxs=veh.cx_s, veh_crr=veh.crr, veh_r=veh.wheel_radius, veh_eta=veh.gear_efficiency,
             ex_v_kmh=50.0, ex_a=1.0, ex_force=fv, ex_couple=vehicle.motor_torque(veh, fv),
             ex_n_mot=vehicle.motor_speed(veh, 50 / 3.6) * rpm, veh_g=siz.gear_ratio, veh_g_max=siz.gear_ratio_max,
             p_rated=siz.rated_power, pmr=siz.pmr, classe=float(siz.wltc_class), marge_cycle=siz.min_margin,
             cycle_km=sim.summary.distance_m / 1000, cycle_wh=sim.summary.wh_per_km, cycle_regen=sim.summary.regen_percent,
             cycle_wh_total=sim.summary.energy_j / 3600, t_0_50=vehicle.acceleration_time(veh, fit, env, st, 50 / 3.6),
             th_cw=p.c_w, th_cs=p.c_s, th_rws=p.r_ws, th_rsa=p.r_sa, th_ta=25.0, tau_rapide_min=tf / 60,
             tau_lent_min=ts / 60, tau_essai_min=tau_fit / 60, essai_n=float(np.count_nonzero(pick)), essai_debut_min=30.0,
             p_cuivre_moy=np.mean(pc), p_fer_moy=np.mean(pf), tw_permanent=tw_ss - 273.15, ts_permanent=ts_ss - 273.15,
             tw_max=th.summary.t_max - 273.15, tw_moy=th.summary.t_mean - 273.15, marge_classe=th.summary.margin,
             vie_h=th.summary.life_hours, t_classe_ex=155.0, t_moins_10=145.0, vie_classe=20000.0,
             vie_moins_10=40000.0, vie_plus_10=10000.0,
             k_n=1.1, k_n2=1.21, r2_kn=fit.r2p * 1.21, x_kn=fit.x_leak * 1.21, r2_k1=fit.r2p, x_k1=fit.x_leak,
             base_wh=base.wh_per_km, base_t050=base.t_0_50, base_tw=base.t_winding_max - 273.15, base_i=base.i_cycle_max,
             base_flux=base.flux_max, base_marge=base.min_margin, t_limite=135.0, flux_limite=1.10,
             budget=1500.0, generations=24.0, evals_point=1500.0, penalite=1e6)
    # tab 6 and validation
    w7 = winding.Winding(36, 4, 3, 7)  # y = 9 values are checked against the CLAUDE.md references below
    _, fa = winding.phase_mmf(w7, "A", turns_per_coil=10)
    f1 = winding.mmf_spectrum(w7, fa, normalise=False)[1]
    rf1 = np.mean(winding.rotating_field(w7, 50.0, 1.0, turns_per_coil=10).fundamental_amplitude)
    f1_6a = np.mean(winding.rotating_field(w7, 50.0, 6.0, turns_per_coil=10).fundamental_amplitude)
    kc = winding.carter_factor(2 * math.pi * 0.065 / 36, 0.0025, 0.0005)
    e.update(w_q=3.0, w_tau=9.0, w_alpha=20.0, w_y=7.0, kd1=0.9598, kp1_y7=0.9397, kw1_y7=0.9019, kw5_y7=-0.0378,
             kw7_y7=-0.1359, kw1_y9=0.9598, kw5_y9=0.2176, kw7_y9=0.1774,
             h5_y7=100 * 0.0378 / 5 / 0.9019, h7_y7=100 * 0.1359 / 7 / 0.9019, n_phase=120.0,
             f_phase_max=float(np.max(fa)), f1_phase=f1, f_tournant=rf1, rapport_tournant=rf1 / f1, w_flux=0.01, w_nc=10.0,
             emf=4.44 * 50 * 120 * winding.winding_factor(w7, 1) * 0.01, p_vitesse=2.0,
             pas_dentaire_mm=2 * math.pi * 65 / 36, ouverture_mm=2.5, entrefer_mm=0.5, i_crete=6.0, f1_6a=f1_6a,
             carter=kc, b_lisse=4e-7 * math.pi * f1_6a / 0.0005, b_entrefer=4e-7 * math.pi * f1_6a / (kc * 0.0005),
             ref_gc_closed=0.5, ref_gc_num=circuit.breakdown(m)[0], ref_tmax_num=circuit.breakdown(m)[1],
             r20_75=(234.5 + 75) / 254.5, wltc_22=1.0, wltc_22p=2.0, wltc_34=2.0, wltc_34p=3.0)
    return e


def _keys_used() -> set[str]:
    return {k for p in cours.PAGES for k in PLACEHOLDER.findall(cours.source(p.slug))}


def test_every_example_number_equals_the_core_result(expected):
    ex = cours.exemples()
    used = _keys_used()
    assert used <= set(ex), sorted(used - set(ex))
    assert used <= set(expected), f"examples not checked: {sorted(used - set(expected))}"
    for k in sorted(used):
        tol = 1e-3 if k.startswith(("kd", "kp", "kw", "h5", "h7")) else 2e-3 if k == "emf" else 1e-9
        assert ex[k] == pytest.approx(float(expected[k]), rel=tol, abs=1e-12), k


# --- formatting, links, answers ------------------------------------------------------------------

def test_format_value():
    assert cours.format_value(0.40058, "2") == "0,40"
    assert cours.format_value(126.289, "4") == "126,3"
    assert cours.format_value(-22.88, "s3") == "−22,9" and cours.format_value(1.1, "s2") == "+1,1"
    assert cours.format_value(1.0, "i") == "1" and cours.format_value(13_726_078.0, "o") == "10⁷"
    assert cours.format_value(0.123456, "f2") == "0,12" and cours.format_value("—", None) == "—"
    assert cours.format_value(float("nan"), None) == "—"


def test_every_link_has_a_target():
    for p in cours.PAGES:
        for url in cours.liens(cours.rendre(p.slug, td5_ex1())):
            assert cours.lien_valide(url), f"{p.slug}: {url}"
    for bad in ("evlab://onglet/nulle", "evlab://page/nulle", "evlab://reponse/identification/9", "evlab://x"):
        assert not cours.lien_valide(bad)


def test_answers_are_hidden_until_opened():
    closed = cours.rendre("identification", td5_ex1())
    assert closed.count("[▸ Voir la réponse](evlab://reponse/identification/") == 3
    assert "on\nmesure 2·R_s" not in closed and "> Entre deux bornes" not in closed
    opened = cours.rendre("identification", td5_ex1(), ouvertes={1})
    assert "> Entre deux bornes d'un stator en étoile" in opened and "[▾ Masquer la réponse]" in opened
    assert opened.count("[▸ Voir la réponse]") == 2


def test_unknown_page_and_tab_are_refused():
    with pytest.raises(ValueError, match="inconnue"):
        cours.page("nulle")
    with pytest.raises(ValueError, match="aucune page"):
        cours.page_for_tab("cours")
    assert cours.page_for_tab("bobinage").slug == "bobinage"


def test_unknown_placeholder_is_reported():
    with pytest.raises(KeyError, match="valeur inconnue"):
        cours._fill("{{ex:nulle}}", {}, None, "test")


# --- table of contents and search ---------------------------------------------------------------

def test_titles_for_the_table_of_contents():
    t = cours.titres("identification")
    assert t[0] == (2, "Ce que fait cet onglet") and (3, "Essais") in t
    assert all(level in (2, 3) for level, _ in t)
    assert not any("####" in text for _, text in t)


def test_folding_keeps_one_character_per_character():
    for s in ("Décrochage", "ÉTOILE à 75 °C", "R_μ ∥ jX_μ", "œuvre ß"):
        assert len(cours.replier(s)) == len(s)
    assert cours.replier("Décrochage À") == "decrochage a"
    assert cours.mots_recherche("  Décrochage décrochage x VF ") == ["decrochage", "vf"]


def test_search_ignores_accents_and_case():
    with_accents = cours.rechercher("décrochage")
    assert with_accents == cours.rechercher("DECROCHAGE") and with_accents
    assert ("enveloppe", max(c for _, c in with_accents)) in with_accents
    assert all(n > 0 for _, n in with_accents)
    both = {s for s, _ in cours.rechercher("carter entrefer")}
    assert both == {s for s, _ in cours.rechercher("carter")} & {s for s, _ in cours.rechercher("entrefer")}
    assert cours.rechercher("") == [] and cours.rechercher("x") == []  # words of 1 letter are ignored
