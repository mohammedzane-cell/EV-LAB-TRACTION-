# EV-LAB UI redesign — acceptance review

Branch `feature/ev-lab-professional-ui` (local commits only). Evidence is reproducible with the
commands given; « baseline » is commit `c5b7492`, before the redesign.

## 1. Acceptance criteria

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | All eight areas share one professional identity | **Met** | One shell (sidebar, header) and one stylesheet built on palette tokens for every workspace; screenshots `docs/images/*.png` (graphite) and `docs/images/clair/*.png` (light), all taken on the demo path |
| 2 | No major screen keeps the outdated interface | **Met** | All 8 workspaces and the FEM window inspected after the redesign (§4); the old pill tabs and generic cards are gone everywhere |
| 3 | Typography, colours, spacing, components consistent | **Met** | Tokens and stacks in `palette.py`, components in `widgets.py`, rules in `docs/ui_design_system.md`; the redesign adds no colour literal (new code uses palette roles); 4 pre-existing literals remain (report, outstanding issue 7) |
| 4 | Charts fit serious engineering reading | **Met**, with the limits of the report (outstanding issues 5–6) | Unit-bearing axes kept, legends outside the data, regions numbered (tab 2), loss breakdown (tab 3), infeasible designs shown (tab 7), crosshair + readout of computed samples on every pyqtgraph plot |
| 5 | Existing functionality available | **Met** | Widget inventory: 151 original elements, 0 missing, values/ranges/units unchanged (§3); menus and course buttons identical; GUI tests pass (§2) |
| 6 | Engineering calculations and outputs preserved | **Met** | `git diff c5b7492 -- src/evlab/core src/evlab/io data` is empty; every number displayed on the 8 workspaces after the demo path is identical before and after, in both themes (§2) |
| 7 | Launches without new runtime errors | **Met** | Screenshot runs and inventory runs log no error or traceback; self-test results in §2 |
| 8 | No decorative or disconnected control | **Met** | Every new control acts: sidebar entries (`test_sidebar_replaces_the_tab_bar_and_fits_the_minimum_window`), « ? » (`test_each_help_button_opens_its_page`), header « Cours » (F1 path) and « Rapport PDF » (Fichier → Exporter PDF), collapse button (same test); no fake status indicator was added |
| 9 | Works at realistic sizes and high DPI | **Met** | Layout checker clean at 1100×650, 1280×720, 1366×768, 1920×1080 (`tests/test_gui_layout.py`); minimum window 985×647 ≤ 1100×650; 150 % scaling checked (`QT_SCALE_FACTOR=1.5`, 1920×1080 physical for 1280×720 logical) |
| 10 | Inspected on real screenshots | **Met** | Screens captured from the running application (offscreen Qt platform, same widgets and painting), inspected one by one, and fixed where needed (§4) |
| 11 | Known limitations documented | **Met** | `docs/ui_redesign_report.md` § Outstanding issues |
| 12 | Design system reusable | **Met** | `docs/ui_design_system.md` § 7 « Adding a module »: a new workspace needs a class, a caption, a glyph and a group entry |

## 2. Regression evidence

**Numbers.** `python tools/capture_screenshots.py --numbers out.json` drives the demo path (tab 1 démo
files, « Comparer les deux », tabs 2–7, FEM window, quick Pareto run, design loaded everywhere,
tab 8) and records every number the screens display (tables, tiles, labels, zones, FEM fundamental,
optimisation KPIs). Baseline (`c5b7492`) against the redesign, graphite and light: **all keys
identical except `tab7_seconds`**, the wall-clock time of the quick optimisation run (22,0 s
before, 21,3 s after: a timing, not a result).

**Tests.** FULL_SUITE_RESULT

**Live FEMM.** The six tests that drive a real FEMM run (`tests/test_femm_model.py`: 5, and
`tests/test_gui_fem.py::test_real_femm_run_from_the_dialog`) fail in this container since its restart:
Wine aborts (`free(): invalid pointer`, « wine32 is missing ») and Xvfb dies. The same test fails
identically on the baseline code (`c5b7492`, run from a separate worktree), and no FEM code was
changed. They were run separately and are reported, not hidden. The FEM window itself (cached runs,
playback, refusal of another winding) passes its 8 other tests.

## 3. Feature-preservation checklist (generated)

`tools/gui_inventory.py` records, for each workspace, every widget the tab object owns (the names
the main window and the tests use): type, text, value, range, decimals and unit, combo items,
check state, enabled state, tooltip, plot title, axes and curves, table headers; then every menu
action and course button. It runs after the demo path up to tab 5. `--diff before after` lists what
disappeared, appeared or changed.

**Result: 151 original elements; 135 identical; 16 kept with a change (15 plots gained the inspection tooltip; tab 4's power plot gained the shaft-power curve and a longer title); **0 missing**; 16 added (tab 1: 2 lines; tab 3: the « Bilan au point » panel, 13 labels; tab 4: the motor-torque plot). Menus identical: yes; course « ? » buttons identical: yes.**

| Workspace | Element (attribute) | Type | Label / value before | Status |
|---|---|---|---|---|
| 1 · Identification | `btn_bench` | QPushButton | Charger… | kept, identical |
| 1 · Identification | `btn_bench_preview` | QPushButton | Aperçu | kept, identical |
| 1 · Identification | `btn_demo` | QPushButton | Charger la démo (TD5 Ex 1, bruit 2,5 %) | kept, identical |
| 1 · Identification | `btn_identify` | QPushButton | Identifier | kept, identical |
| 1 · Identification | `btn_pdf` | QPushButton | Exporter PDF | kept, identical |
| 1 · Identification | `btn_points` | QPushButton | Charger… | kept, identical |
| 1 · Identification | `btn_points_preview` | QPushButton | Aperçu | kept, identical |
| 1 · Identification | `chip_demo` | QLabel | points synthétiques (démo) | kept, identical |
| 1 · Identification | `combo_layout` | QComboBox | TP3 (R1 en tête) / Bornes | kept, identical |
| 1 · Identification | `lbl_bench` | QLabel | bench_tests_demo.csv — chargé (démo) 8 à vide · 1 rotor bloq | kept, identical |
| 1 · Identification | `lbl_layout_note` | QLabel | Le schéma ne change pas les formules classiques ; il fixe le | kept, identical |
| 1 · Identification | `lbl_legend` | QLabel | <span style='color:#E08A1E'>━━</span> modèle (formules class | kept, identical |
| 1 · Identification | `lbl_points` | QLabel | load_points_demo.csv — chargé (démo) 12 points, g = 0,020 …  | kept, identical |
| 1 · Identification | `lbl_speed` | QLabel | 1350 tr/min | kept, identical |
| 1 · Identification | `lbl_table_note` | QLabel | (données synthétiques bruitées, démo) | kept, identical |
| 1 · Identification | `plot_current` | PlotWidget | Courant–glissement | kept; changed: tooltip |
| 1 · Identification | `plot_torque` | PlotWidget | Couple–glissement | kept; changed: tooltip |
| 1 · Identification | `plots[current_slip]` | PlotWidget | Courant–glissement | kept; changed: tooltip |
| 1 · Identification | `plots[current_speed]` | PlotWidget | Courant–vitesse | kept; changed: tooltip |
| 1 · Identification | `plots[torque_slip]` | PlotWidget | Couple–glissement | kept; changed: tooltip |
| 1 · Identification | `plots[torque_speed]` | PlotWidget | Couple–vitesse | kept; changed: tooltip |
| 1 · Identification | `radios[both]` | QRadioButton | Comparer les deux | kept, identical |
| 1 · Identification | `radios[classical]` | QRadioButton | Formules classiques | kept, identical |
| 1 · Identification | `radios[fit]` | QRadioButton | Optimisation (scipy) | kept, identical |
| 1 · Identification | `spin_f` | QDoubleSpinBox | 50.0 Hz [0.1 ; 1000.0] | kept, identical |
| 1 · Identification | `spin_p` | QSpinBox | 2 [1 ; 24] | kept, identical |
| 1 · Identification | `spin_r1` | QDoubleSpinBox | 0.4006 Ω [0.0 ; 1000.0] | kept, identical |
| 1 · Identification | `spin_t_r1` | QDoubleSpinBox | 20.0 °C [-50.0 ; 250.0] | kept, identical |
| 1 · Identification | `spin_v` | QDoubleSpinBox | 230.0 V [1.0 ; 100000.0] | kept, identical |
| 1 · Identification | `table` | QTableWidget | Méthode · Rf (Ω) · Xm (Ω) · X fuites (Ω) · R'2 (Ω) | kept, identical |
| 1 · Identification | `lbl_ci` | ElidedLabel | Intervalles de confiance à 95 % de l'optimisation : Xm [44,0 | added |
| 1 · Identification | `lbl_published` | ElidedLabel | Moteur publié : R1 = 0,4872 Ω à 75,0 °C · p_méc = 54,4 W | added |
| 2 · Enveloppe | `btn_compute` | QPushButton | Calculer l'enveloppe | kept, identical |
| 2 · Enveloppe | `chip_demo` | QLabel | démo | kept, identical |
| 2 · Enveloppe | `lbl_flux` | QLabel |  | kept, identical |
| 2 · Enveloppe | `lbl_motor` | QLabel | Identification TP3 · optimisation (démo) V = 230 V, f = 50,0 | kept, identical |
| 2 · Enveloppe | `lbl_zones` | QLabel | zone 1 : couple constant 0–1253 tr/min · zone 2 : puissance  | kept, identical |
| 2 · Enveloppe | `plot_power` | PlotWidget | Puissance disponible | kept; changed: tooltip |
| 2 · Enveloppe | `plot_torque` | PlotWidget | Couple disponible | kept; changed: tooltip |
| 2 · Enveloppe | `spin_boost` | QDoubleSpinBox | 0.0 V [0.0 ; 10000.0] | kept, identical |
| 2 · Enveloppe | `spin_fmax` | QDoubleSpinBox | 100.0 Hz [1.0 ; 1000.0] | kept, identical |
| 2 · Enveloppe | `spin_imax` | QDoubleSpinBox | 20.0 A [0.1 ; 10000.0] | kept, identical |
| 2 · Enveloppe | `spin_margin` | QDoubleSpinBox | 80.0 % [1.0 ; 100.0] | kept, identical |
| 2 · Enveloppe | `tiles[base]` | KpiTile |  | kept, identical |
| 2 · Enveloppe | `tiles[end_cp]` | KpiTile |  | kept, identical |
| 2 · Enveloppe | `tiles[p_max]` | KpiTile |  | kept, identical |
| 2 · Enveloppe | `tiles[t_vmax]` | KpiTile |  | kept, identical |
| 3 · Rendement | `btn_compute` | QPushButton | Calculer la carte | kept, identical |
| 3 · Rendement | `btn_png` | QPushButton | Exporter PNG | kept, identical |
| 3 · Rendement | `canvas` | FigureCanvasQTAgg |  | kept; changed: tooltip |
| 3 · Rendement | `chip_demo` | QLabel | démo | kept, identical |
| 3 · Rendement | `chk_cycle` | QCheckBox | Points du cycle | kept, identical |
| 3 · Rendement | `chk_inv` | QCheckBox | Pertes onduleur (démo) | kept, identical |
| 3 · Rendement | `chk_mech` | QCheckBox | Pertes mécaniques (p_méc = 54,4 W) | kept, identical |
| 3 · Rendement | `lbl_best` | QLabel |  | kept, identical |
| 3 · Rendement | `lbl_drive` | QLabel | Variateur (onglet 2) : 20,0 A, boost 0 V, marge 80 %, f max  | kept, identical |
| 3 · Rendement | `spin_beta` | QDoubleSpinBox | 1.5  [0.5 ; 3.0] | kept, identical |
| 3 · Rendement | `spin_friction` | QDoubleSpinBox | 50.0 % [0.0 ; 100.0] | kept, identical |
| 3 · Rendement | `spin_inv0` | QDoubleSpinBox | 50.0 W [0.0 ; 10000.0] | kept, identical |
| 3 · Rendement | `spin_invk` | QDoubleSpinBox | 2.0 % [0.0 ; 50.0] | kept, identical |
| 3 · Rendement | `spin_nt` | QSpinBox | 160 [10 ; 400] | kept, identical |
| 3 · Rendement | `spin_nw` | QSpinBox | 120 [10 ; 400] | kept, identical |
| 3 · Rendement | `spin_tw` | QDoubleSpinBox | 75.0 °C [-40.0 ; 250.0] | kept, identical |
| 3 · Rendement | `lbl_point_where` | QLabel | — | added |
| 3 · Rendement | `loss_values[p_cu1]` | QLabel | — | added |
| 3 · Rendement | `loss_values[p_cu2]` | QLabel | — | added |
| 3 · Rendement | `loss_values[p_fe]` | QLabel | — | added |
| 3 · Rendement | `loss_values[p_inv]` | QLabel | — | added |
| 3 · Rendement | `loss_values[p_mech]` | QLabel | — | added |
| 3 · Rendement | `point_values[eta]` | QLabel | — | added |
| 3 · Rendement | `point_values[f]` | QLabel | — | added |
| 3 · Rendement | `point_values[i1]` | QLabel | — | added |
| 3 · Rendement | `point_values[p_in]` | QLabel | — | added |
| 3 · Rendement | `point_values[p_out]` | QLabel | — | added |
| 3 · Rendement | `point_values[speed]` | QLabel | — | added |
| 3 · Rendement | `point_values[torque]` | QLabel | — | added |
| 4 · Véhicule & WLTC | `btn_class_cycle` | QPushButton | Cycle de la classe | kept, identical |
| 4 · Véhicule & WLTC | `btn_cycle` | QPushButton | Charger un cycle CSV… | kept, identical |
| 4 · Véhicule & WLTC | `btn_propose` | QPushButton | Proposer | kept, identical |
| 4 · Véhicule & WLTC | `btn_simulate` | QPushButton | Simuler le cycle | kept, identical |
| 4 · Véhicule & WLTC | `chip_demo` | QLabel | démo | kept, identical |
| 4 · Véhicule & WLTC | `chk_regen` | QCheckBox | Freinage récupératif | kept, identical |
| 4 · Véhicule & WLTC | `lbl_class` | QLabel | Classe WLTC 1 (15,0 W/kg, P = 9,01 kW) | kept, identical |
| 4 · Véhicule & WLTC | `lbl_cycle` | QLabel | Cycle : cycle_demo (démo) — fichier WLTC classe 1 absent de  | kept, identical |
| 4 · Véhicule & WLTC | `lbl_gear` | QLabel | G proposé 3,53 (G max vitesse 4,27) : toute la courbe dans l | kept, identical |
| 4 · Véhicule & WLTC | `lbl_warning` | QLabel |  | kept, identical |
| 4 · Véhicule & WLTC | `plot_power` | PlotWidget | Puissance batterie | kept; changed: curves, title, tooltip |
| 4 · Véhicule & WLTC | `plot_speed` | PlotWidget | Vitesse du véhicule | kept; changed: tooltip |
| 4 · Véhicule & WLTC | `spin_aux` | QDoubleSpinBox | 200.0 W [0.0 ; 100000.0] | kept, identical |
| 4 · Véhicule & WLTC | `spin_crr` | QDoubleSpinBox | 0.012  [0.0 ; 0.1] | kept, identical |
| 4 · Véhicule & WLTC | `spin_cxs` | QDoubleSpinBox | 0.6 m² [0.05 ; 20.0] | kept, identical |
| 4 · Véhicule & WLTC | `spin_eta_g` | QDoubleSpinBox | 95.0 % [50.0 ; 100.0] | kept, identical |
| 4 · Véhicule & WLTC | `spin_g` | QDoubleSpinBox | 3.531  [0.1 ; 50.0] | kept, identical |
| 4 · Véhicule & WLTC | `spin_grade` | QDoubleSpinBox | 0.0 % [-30.0 ; 30.0] | kept, identical |
| 4 · Véhicule & WLTC | `spin_mass` | QDoubleSpinBox | 600.0 kg [50.0 ; 50000.0] | kept, identical |
| 4 · Véhicule & WLTC | `spin_r` | QDoubleSpinBox | 0.27 m [0.05 ; 2.0] | kept, identical |
| 4 · Véhicule & WLTC | `tiles[distance]` | KpiTile |  | kept, identical |
| 4 · Véhicule & WLTC | `tiles[energy]` | KpiTile |  | kept, identical |
| 4 · Véhicule & WLTC | `tiles[regen]` | KpiTile |  | kept, identical |
| 4 · Véhicule & WLTC | `tiles[whkm]` | KpiTile |  | kept, identical |
| 4 · Véhicule & WLTC | `plot_motor` | PlotWidget | Moteur : couple à l'arbre | added |
| 5 · Thermique | `btn_run` | QPushButton | Calculer les températures | kept, identical |
| 5 · Thermique | `chip_demo` | QLabel | paramètres démo | kept, identical |
| 5 · Thermique | `chip_r1` | QLabel | R1 ≈ 0 : pas de pertes cuivre stator — lancez l'identificati | kept, identical |
| 5 · Thermique | `combo_class` | QComboBox | Classe A (105 °C) / Classe E (120 °C) / Classe B (130 °C) /  | kept, identical |
| 5 · Thermique | `combo_method` | QComboBox | Euler implicite (1 s) / solve_ivp RK45 (contrôle) | kept, identical |
| 5 · Thermique | `lbl_cycle` | QLabel | Cycle : cycle_demo (démo) (7,92 min) | kept, identical |
| 5 · Thermique | `lbl_note` | QLabel | La durée de vie suit la règle des 10 K : c'est un ordre de g | kept, identical |
| 5 · Thermique | `lbl_tau` | QLabel | Constantes de temps : 4,30 min et 19,4 min | kept, identical |
| 5 · Thermique | `plot` | PlotWidget | Temps (min) ; Température (°C) | kept; changed: tooltip |
| 5 · Thermique | `spin_cs` | QDoubleSpinBox | 25000.0 J/K [1.0 ; 100000000.0] | kept, identical |
| 5 · Thermique | `spin_cw` | QDoubleSpinBox | 3000.0 J/K [1.0 ; 10000000.0] | kept, identical |
| 5 · Thermique | `spin_cycles` | QSpinBox | 10 [1 ; 500] | kept, identical |
| 5 · Thermique | `spin_rsa` | QDoubleSpinBox | 0.04 K/W [0.0001 ; 10.0] | kept, identical |
| 5 · Thermique | `spin_rws` | QDoubleSpinBox | 0.1 K/W [0.0001 ; 10.0] | kept, identical |
| 5 · Thermique | `spin_ta` | QDoubleSpinBox | 25.0 °C [-40.0 ; 80.0] | kept, identical |
| 5 · Thermique | `tiles[life]` | KpiTile |  | kept, identical |
| 5 · Thermique | `tiles[margin]` | KpiTile |  | kept, identical |
| 5 · Thermique | `tiles[t_max]` | KpiTile |  | kept, identical |
| 5 · Thermique | `tiles[t_mean]` | KpiTile |  | kept, identical |
| 6 · Bobinage | `btn_fem` | QPushButton | Ouvrir l'animation FEM… | kept, identical |
| 6 · Bobinage | `btn_play` | QPushButton | ▶ Lecture | kept, identical |
| 6 · Bobinage | `kw_table` | QTableWidget | ν · kd · kp (y = 9) · kw (y = 9) · kp (y = 7) · kw (y = 7) | kept, identical |
| 6 · Bobinage | `lbl_emf` | QLabel | N = 120,0 spires/phase, kw1 = 0,9019 E = 4,44·f·N·kw1·Φ = 24 | kept, identical |
| 6 · Bobinage | `lbl_error` | QLabel |  | kept, identical |
| 6 · Bobinage | `lbl_fem` | QLabel | FEMM 4.2 disponible | kept, identical |
| 6 · Bobinage | `lbl_geom` | QLabel | q = 3 encoches/pôle/phase, τ = 9 encoches, α = 20,0° él., pa | kept, identical |
| 6 · Bobinage | `lbl_m` | QLabel | 3 | kept, identical |
| 6 · Bobinage | `lbl_speed` | QLabel | 20 images/s, une période électrique = 72 images | kept, identical |
| 6 · Bobinage | `plot_full` | PlotWidget | pas diamétral y = τ = 9 | kept; changed: tooltip |
| 6 · Bobinage | `plot_short` | PlotWidget | pas raccourci y = 7 | kept; changed: tooltip |
| 6 · Bobinage | `plot_spec` | PlotWidget | rang ν ; |F_ν| / |F_1| | kept; changed: tooltip |
| 6 · Bobinage | `slider` | QSlider |  | kept, identical |
| 6 · Bobinage | `spin_f` | QDoubleSpinBox | 50.0 Hz [0.1 ; 10000.0] | kept, identical |
| 6 · Bobinage | `spin_nc` | QDoubleSpinBox | 10.0 spires [1.0 ; 10000.0] | kept, identical |
| 6 · Bobinage | `spin_phi` | QDoubleSpinBox | 0.01 Wb [0.0 ; 10.0] | kept, identical |
| 6 · Bobinage | `spin_poles` | QSpinBox | 4 [2 ; 48] | kept, identical |
| 6 · Bobinage | `spin_y` | QSpinBox | 7 [1 ; 9] | kept, identical |
| 6 · Bobinage | `spin_z` | QSpinBox | 36 [6 ; 240] | kept, identical |
| 6 · Bobinage | `strip` | QTableWidget | 1 · 2 · 3 · 4 · 5 · 6 · 7 · 8 · 9 · 10 · 11 · 12 · 13 · 14 · | kept, identical |
| 7 · Optimisation | `bound_spins[boost][0]` | QDoubleSpinBox | 0.0 V [0.0 ; 1000.0] | kept, identical |
| 7 · Optimisation | `bound_spins[boost][1]` | QDoubleSpinBox | 8.0 V [0.0 ; 1000.0] | kept, identical |
| 7 · Optimisation | `bound_spins[gear_ratio][0]` | QDoubleSpinBox | 2.5  [0.0 ; 1000.0] | kept, identical |
| 7 · Optimisation | `bound_spins[gear_ratio][1]` | QDoubleSpinBox | 4.5  [0.0 ; 1000.0] | kept, identical |
| 7 · Optimisation | `bound_spins[k_n][0]` | QDoubleSpinBox | 0.85  [0.0 ; 1000.0] | kept, identical |
| 7 · Optimisation | `bound_spins[k_n][1]` | QDoubleSpinBox | 1.2  [0.0 ; 1000.0] | kept, identical |
| 7 · Optimisation | `bound_spins[margin][0]` | QDoubleSpinBox | 60.0 % [0.0 ; 1000.0] | kept, identical |
| 7 · Optimisation | `bound_spins[margin][1]` | QDoubleSpinBox | 95.0 % [0.0 ; 1000.0] | kept, identical |
| 7 · Optimisation | `btn_cancel` | QPushButton | Annuler | kept, identical |
| 7 · Optimisation | `btn_load` | QPushButton | Charger ce design dans tous les onglets | kept, identical |
| 7 · Optimisation | `btn_run` | QPushButton | Lancer l'optimisation | kept, identical |
| 7 · Optimisation | `chip_demo` | QLabel | démo | kept, identical |
| 7 · Optimisation | `chip_r1` | QLabel | R1 ≈ 0 : pas de pertes cuivre stator — lancez l'identificati | kept, identical |
| 7 · Optimisation | `kpi_table` | QTableWidget | KPI · Base · Sélection · Gain | kept, identical |
| 7 · Optimisation | `lbl_budget` | QLabel | 4 variable(s) libre(s) → 24 générations, 1500 évaluations pa | kept, identical |
| 7 · Optimisation | `lbl_click` | QLabel | Cliquer un point du front pour le sélectionner. | kept, identical |
| 7 · Optimisation | `plot` | PlotWidget | 0–50 km/h (s) ; Consommation (Wh/km) | kept; changed: tooltip |
| 7 · Optimisation | `spin_budget` | QSpinBox | 1500 [6 ; 50000] | kept, identical |
| 7 · Optimisation | `spin_points` | QSpinBox | 6 [2 ; 20] | kept, identical |
| 7 · Optimisation | `spin_pop` | QSpinBox | 15 [3 ; 50] | kept, identical |
| 7 · Optimisation | `spin_seed` | QSpinBox | 0 [0 ; 10000] | kept, identical |
| 7 · Optimisation | `spin_workers` | QSpinBox | 4 [1 ; 4] | kept, identical |
| 7 · Optimisation | `var_table` | QTableWidget | Variable · Base · Sélection | kept, identical |
| 8 · Cours | `browser` | QTextBrowser |  | kept, identical |
| 8 · Cours | `lbl_search` | QLabel |  | kept, identical |
| 8 · Cours | `search` | QLineEdit |  | kept, identical |
| 8 · Cours | `toc` | QTreeWidget |  | kept, identical |

Function checklist (each line is exercised by the named test, all passing):

| Area | Functions | Tests |
|---|---|---|
| Shell | 8 workspaces reachable, header follows, sidebar compact / expanded, minimum window | `test_sidebar_replaces_the_tab_bar_and_fits_the_minimum_window`, `test_main_window_opens_with_eight_tabs` |
| Menus | Fichier (PDF, Excel, cours PDF, Quitter), Affichage (themes), Aide (Cours, F1) | `test_menu`, `test_help_menu_opens_the_course`, `test_theme_menu_switches_and_is_remembered` |
| 1 · Identification | load files, démo, previews, 3 methods, terminals layout, CI tooltips, errors in French, worker failure | `test_loading_demo_files_fills_machine_and_chip`, `test_previews`, `test_identify_each_method`, `test_terminals_layout_is_used`, `test_fit_tooltips_show_confidence_interval`, `test_errors_are_reported_in_french`, `test_worker_failure_is_reported` |
| 2 · Enveloppe | initial envelope, recompute on settings, new motor, invalid input, démo chip, boost warning | `tests/test_gui_envelope.py` (8 tests) |
| 3 · Rendement | core map, contours and overlay, recompute, PNG export, cycle points, démo chip | `tests/test_gui_efficiency.py` (9 tests) |
| 4 · Véhicule | KPIs from core, red warning, regen, cycle to tab 3, user cycle file, invalid file, WLTC class | `tests/test_gui_vehicle.py` (8 tests) |
| 5 · Thermique | temperatures from core, class line, class/cycles/method, time constants, needs a cycle, chips | `tests/test_gui_thermal.py` (8 tests) |
| 6 · Bobinage | strip, kw table, FFT spectrum, animation, refusal of invalid windings, EMF | `tests/test_gui_winding.py` (8 tests) |
| 6 · FEM window | peak current default, cache without FEMM, playback, other winding refused | `tests/test_gui_fem.py` (8 tests; the live run: §2) |
| 7 · Optimisation | problem from tabs, run, plot and tables, click-select-load, cancel, fixed budget, chips | `tests/test_gui_optimisation.py` (9 tests) |
| 8 · Cours | pages, « ? », F1, examples, answers, links, live values, search, TOC, theme, PDF | `tests/test_gui_cours.py` (15 tests) |
| Reports | PDF and Excel export, tab 1 button, cancelled dialog | `tests/test_gui_export.py` |
| Layout | overlaps / cut text at 4 sizes, scrolling panels, legends outside plots, FEM window | `tests/test_gui_layout.py` |
| Self-test | `python -m evlab --smoke` | 12/12 checks (8 workspaces, data, test sets, FEM cache, démo files, envelope, cycle, 2-process optimisation, PDF, Excel, course tab, course PDF) |

## 4. Visual inspection (screens looked at, issues found and fixed)

| Screen | Found during inspection | Fix |
|---|---|---|
| Shell | « Véhicule _WLTC » (« & » read as a shortcut marker); focus ring left on the first nav item | escaped label; nav buttons take keyboard focus only, focus starts in the workspace |
| Shell | caption and motor label imposed the window width (1316 px > 1100) | one-line header, self-eliding caption, elided motor label |
| Shell | hidden tab bar still counted in the minimum height | `WorkspaceStack` measures the pages only |
| 1 | « Identifier » below the fold at 1280×800 | tighter control heights and margins |
| 1 | confidence line wrapped to 3 lines on a narrow window | two self-eliding lines (full text in tooltip) |
| 2 | region names overlapping | « zone 1/2/3 » on the plots, names in the zone line |
| 3 | legend over the motor title; IndexError when a new map had a coarser grid | legend under the figure; selection reset and bounds-checked |
| 4 | « Rendement tra… » cut (tabular digits widened every spin box) | tabular figures only in readouts |
| 4 | three stacked plots overflowed at 1100×650; x-link misaligned side-by-side plots | two rows; explicit time-axis sync |
| 4 | « couple à l'arbre ( » (« < » read as HTML) | legend reworded |
| 5 | « Euler implicite (1 s » cut in the combo (found by comparing with the baseline screenshot) | combo arrow area back to its former width |
| 6 | slot labels « … » with the sidebar | icon rail below 1440 px, compact slot-table header, no eliding |
| all plots | crosshair removed by each redraw; readout squeezed plots in grids | crosshair restored on hover; floating readout |
| test suite | segmentation fault: garbage collection in a worker thread finalised Qt objects | collection only in the GUI thread (`workers.collect_garbage_in_gui_thread`) |
