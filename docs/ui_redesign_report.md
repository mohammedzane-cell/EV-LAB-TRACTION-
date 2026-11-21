# EV-LAB UI redesign — report

Branch `feature/ev-lab-professional-ui`, created from `claude/sleepy-hypatia-nkmuki` at `c5b7492`
(working tree clean, no stash). Local commits only; nothing is pushed or merged.

Scope: the visual and interaction layer (`src/evlab/gui/`, `src/evlab/palette.py`, icons,
stylesheet, documentation tools). `src/evlab/core/` and `src/evlab/io/` are not modified: no
equation, default value, unit or sign convention changes.

## Stage A — audit of the existing interface (at `c5b7492`)

### Architecture

| Layer | Files | Role |
|---|---|---|
| Palette | `src/evlab/palette.py` (no Qt) | one dict of colours per theme (light, dark), data-series colours, WCAG contrast check, matplotlib rcParams; shared with the PDF figures (`io/figures.py`, always light) |
| Theme | `gui/theme.py`, `gui/style.qss`, `gui/icons/<theme>/` | `@role` tokens of the stylesheet replaced from the palette; pyqtgraph defaults and plot styling; QSettings memory |
| Shared widgets | `gui/widgets.py` | French spin box, left scroll panel, card, KPI tile, démo / alert chip, legends moved above plots, flexible plot sizing |
| Shell | `gui/main_window.py` | `QTabWidget` with 8 pill tabs, « ? » help button in each of tabs 1–7, menus Fichier / Affichage / Aide, status bar (motor in use, busy bar), wiring between tabs (envelope → map → vehicle → thermal → optimisation, design → all tabs) |
| Screens | `gui/tab_*.py`, `gui/fem_view.py` | thin views: inputs in `QGroupBox`es of a 300 px scrolling left panel, results in cards (pyqtgraph plots, one matplotlib canvas in tab 3, tables) |
| Background work | `gui/workers.py` | `CoreWorker` on `QThreadPool` with finished / failed / progress signals; tab 7 uses processes |
| Layout QA | `gui/layout_check.py`, `tests/test_gui_layout.py` | overlap, out-of-parent and cut-text checks at 1100×650 … 1920×1080 |

### Usability and visual problems found

1. Generic look: rounded pill tabs, one blue accent, white cards. Nothing says « EV-LAB »: the
   product name appears only in the window title.
2. Navigation: 8 pills of equal weight in one row. The help « ? » buttons are squeezed into the
   pills, and the row is close to overflowing at 1100 px (it was shortened once already).
3. No header: the window never says which workspace you are in, or which motor the chain uses.
   The motor shows only in the status bar, and a tab's own messages replace it there.
4. Inputs: group boxes look the same as result cards, so inputs and results are hard to tell
   apart. Units are spin-box suffixes in the same weight as the value.
5. Plots: there is no data inspection (no crosshair, no readout of x and y with units); only
   pyqtgraph's default right-click menu offers zoom reset and export. Grids are strong, and the
   series colours are the same 4 basic hues on every screen.
6. Tab 3: the matplotlib map has its legend inside the plot area. The loss terms the map
   computes (copper, iron, mechanical, inverter) cannot be seen; only η is drawn.
7. Tab 7: only the feasible evaluations are plotted. Infeasible ones are invisible, so the reader
   cannot see what the constraints remove.
8. Provenance: « démo » chips exist on tabs 1–5 and 7, but the colour of the chip is the only cue.
9. KPI tiles: a large bold value with its unit in the same run, in proportional digits, so
   values in a row do not align.

### Baseline recorded before any change

- `pytest`: 690 passed, 3 skipped (the WLTC files), at `c5b7492`.
- Displayed numbers, all 8 tabs after the demo path: `tools/capture_screenshots.py --numbers`
  → kept as `ui_before/numbers.json`.
- Widget inventory: `tools/gui_inventory.py` (new documentation tool), 151 elements in 8 tabs
  and 8 menu entries → `ui_before/inventory.json`.
- Screenshots of every screen at 1280 × 800: `ui_before/*.png`.

(`ui_before/` is kept outside the repository, in the session scratchpad.)

### Engineering issues observed during the audit (documented, NOT changed)

These belong to the model or the data, not to the interface. None is touched by the redesign.

1. Linear magnetising branch (A33) used in tabs 2, 3 and 7, while the tab 6 FEM with M-19 shows
   saturation starting at the rated magnetising current (B1 ratio 0,900 at 7,07 A).
2. The load-point fit requires cos φ for every point, and it fails on a measured zero torque
   (point-wise normalisation divides by the reading). Seen with the real TP3 files in
   `data/tp3_local/`.
3. The real TP3 2026-27 no-load series extrapolates to negative mechanical losses (−564,6 W), and
   its locked-rotor power is below the stator copper loss. The app refuses both, with English
   core messages behind a French prefix.

## Stage B — design system and shell

- **Identity**: « EV-LAB · ELECTRIC TRACTION RESEARCH STUDIO ». Wordmark with an accent hyphen, and a
  logo drawn for the product: a stator ring whose 4 accent arcs are the 4 poles of the reference
  machine, around a rotor. Product name and subtitle are the only English text; the GUI stays French.
- **Themes**: « Studio graphite » (deep graphite / midnight navy, default) and « Studio clair ».
  The palette keys stay `dark` / `light`, so remembered settings and every
  `MainWindow(theme_name=…)` keep working. One electric-cyan accent marks only the active workspace,
  the primary action and focus.
- **Shell**: sidebar of the 8 workspaces grouped by domain (Machine · Véhicule · Électromagnétisme ·
  Conception · Ressources), custom line icons, « ? » course buttons, Ctrl+1…8, icon rail below
  1440 px (laptops keep their workspace width). A one-line header gives the workspace number, title
  and caption, the motor used by the chain with its démo chip, and « Cours » / « Rapport PDF ». The
  pages stay those of `self.tabs` (bar hidden), so every connection between workspaces is
  untouched.
- **Components** (`widgets.py`): readout tile with a large value and a small muted unit (`text()`
  unchanged for the reports and tests), self-eliding label, section header, divider, chips `demo` /
  `alert` / `source`, plot inspection, empty states. Full reference: `docs/ui_design_system.md`.

## Stage C/D — workspaces and charts

| Area | Change (presentation of existing results only) |
|---|---|
| All plots | crosshair + floating readout: cursor in axis units and the nearest **computed** sample of each named curve (no interpolation); zoom, pan, reset (« A »), export (right-click); empty-state hint with the next action; titles, ticks and axes from the design system |
| 1 · Identification | published motor (R1 with its temperature, p_méc) and the fit's 95 % intervals under the table (until now only in tooltips) |
| 2 · Enveloppe | operating regions numbered on both plots, boundary speeds marked (values from `drive.Envelope`) |
| 3 · Rendement | « Bilan au point »: η, P_out, P_in, I1, f and the five loss terms of `losses.EfficiencyMap` at the best point (from `losses.best_point`) or at the clicked grid point, bars as share of P_in; legend outside the map |
| 4 · Véhicule | motor shaft torque (traction > 0, regeneration < 0) and shaft power next to battery power, from the same `vehicle.DriveResult`, on one time axis |
| 5 · Thermique | shell, tiles and plot styling; démo network still labelled in the group title and chip |
| 6 · Bobinage | slot table readable at laptop widths; FEM window with plot inspection; « résultats FEM pré-calculés » and « géométrie démo » kept |
| 7 · Optimisation | infeasible evaluations drawn (red crosses, counted in the legend) next to the feasible ones and the front; they never move the view (`ignoreBounds`) |
| 8 · Cours | equations in the accent mono; course PDF title page « EV-LAB · Electric Traction Research Studio » |

No formula was added to `gui/`: the new panels read arrays that core already returns. The only
arithmetic is a display proportion (the length of the tab 3 loss bars), which prints no number.

## Stage E/F — regression report

See `docs/ui_redesign_acceptance.md` § 2–4 for the evidence: identical numbers on the demo path in
both themes, the generated preservation checklist (0 missing element), the test results, and the
table of issues found by inspecting the screenshots and fixed.

**Crash found and fixed during stage F.** One full run ended with « Fatal Python error: Segmentation
fault »: Python's garbage collector ran in a CoreWorker thread (building the PDF report) and
finalised Qt objects of the GUI thread there. The same error had been seen once before the
redesign (the course-tab work), but the plot inspection adds reference cycles and makes it more
likely. Fix (`gui/workers.collect_garbage_in_gui_thread`, started by the main window): pyqtgraph's
`GarbageCollector` disables the automatic collection and collects from a 1 s QTimer of the GUI
thread. Memory is reclaimed at most 1 s later; no computation changes (the optimisation's worker
processes are spawned and keep the automatic collection).

Tests changed on purpose (design decisions, no physics):

| Test | Before | After |
|---|---|---|
| `test_gui_theme.py::test_requested_palette_values` | the previous palette values | renamed `test_design_system_palette_values`: graphite and accent values, default theme |
| `test_gui_theme.py::test_stylesheet_has_every_token_replaced` | 8 / 6 / 13 px radii, « Segoe UI », « Inter » | 6 / 4 / 3 px radii, UI and mono stacks |
| `test_gui_theme.py::test_app_starts_with_each_theme` | first 2 font families | the whole UI stack |
| `test_gui_theme.py::test_saved_theme_defaults_to_light` | light default | renamed `…_to_graphite` |
| `test_smoke.py::test_main_window_opens_with_eight_tabs` | old window title | « EV-LAB · Electric Traction Research Studio — ENP Alger, ME3 » |
| `test_gui_cours.py::test_tab_bar_fits_the_minimum_window` | tab bar width | replaced by `test_sidebar_replaces_the_tab_bar_and_fits_the_minimum_window` |
| `test_gui_cours.py::test_course_pdf_has_title_page…` | « EV-Traction Lab » on the title page | « EV-LAB », « ELECTRIC TRACTION RESEARCH STUDIO » |

## Screenshots

`docs/images/` (graphite, the default) and `docs/images/clair/` (light): 00 start window, 01–07 the
workspaces after the demo path, 02b tab 2 with the optimised design loaded, 06b the FEM window,
08 the course (and `08_cours_clair.png`). All at 1280 × 800, so the sidebar shows as its icon rail.
Regenerate with `python tools/capture_screenshots.py` (and `--theme light --out docs/images/clair`).

## Files modified

| File | Change |
|---|---|
| `src/evlab/palette.py` | palettes, roles, default theme, font stacks |
| `src/evlab/gui/style.qss` | rewritten on the design system |
| `src/evlab/gui/theme.py` | new tokens, mono font registration, plot titles and ticks, default theme |
| `src/evlab/gui/glyphs.py` | **new**: icon set and logo |
| `src/evlab/gui/widgets.py` | new components (readout, eliding label, section header, inspection, empty states) |
| `src/evlab/gui/main_window.py` | shell: sidebar, header, `WorkspaceStack`, shortcuts, responsive sidebar |
| `src/evlab/gui/workers.py` | garbage collection in the GUI thread only (crash fix, see stage E/F) |
| `src/evlab/gui/tab_identification.py`, `tab_envelope.py`, `tab_efficiency.py`, `tab_vehicle.py`, `tab_winding.py`, `tab_optimisation.py`, `tab_cours.py`, `fem_view.py`, `cours_pdf.py` | per-screen changes listed above |
| `src/evlab/gui/icons/{dark,light}/*.svg` | control icons in the new palette |
| `tools/gui_inventory.py` | **new**: preservation inventory and diff |
| `tools/capture_screenshots.py` | default theme graphite |
| `tests/test_gui_theme.py`, `tests/test_smoke.py`, `tests/test_gui_cours.py` | see the table above |
| `docs/ui_design_system.md`, `docs/ui_redesign_acceptance.md`, `docs/ui_redesign_report.md` | **new** |
| `README.md`, `docs/user_guide.md`, `docs/demo_script.md`, `docs/images/**` | updated |

Not modified: `src/evlab/core/`, `src/evlab/io/`, `data/`, `packaging/` (launch and build
instructions are unchanged: `python -m evlab`, `packaging\build_windows.bat`).

## Outstanding issues and recommendations

**Needs your approval (outside the agreed scope):**
1. `io/report.py` still titles the session PDF « EV-Traction Lab ». Renaming it is a one-line
   change in `io/`.
2. The FEM |B| frames are PNGs rendered on a white background when FEMM runs (`io/femm_model.py`),
   so they stand out in graphite. A themed re-render needs a change in `io/` and new cached runs.

**Environment:**
3. Live FEMM fails in this container since its restart (Wine abort, Xvfb dies), on the baseline
   code too. When FEMM loses its display, the FEM worker keeps polling, and the application
   cannot quit until it stops (pre-existing; seen as a hung test process at exit).

**Known limits of this redesign:**
4. Windows rendering (Segoe UI Variable, Cascadia Mono, real 125 / 150 % screens) was not seen
   here: QA ran on Linux with Inter / JetBrains Mono and an emulated 150 % scale. Your Windows build
   should be looked at once.
5. The tab 3 map (matplotlib) has click-to-inspect and a tooltip, not the hover crosshair of the
   pyqtgraph plots.
6. Tab 7 shows no convergence history: core does not record one per generation, and none is
   invented.
7. Four pre-existing colour literals remain in GUI code (the redesign added none): the zone
   tints of tab 2, the grey of the feasible evaluations of tab 7, the pastel phase colours of the
   slot table (tab 6) and the legend fallback grey. Moving them to palette roles is a small
   follow-up.
8. Kept on purpose: the QSettings application name (« EV-Traction Lab ») so remembered settings
   survive; the course PDF file name `cours_EV-Traction_Lab.pdf`; the package name `evlab`.

**Recommended next steps:** apply items 1–2 if you approve them; add hover inspection to the
matplotlib map; one review session on Windows at 100 / 150 %; a short keyboard-only walkthrough
(Ctrl+1…8, Tab through each workspace, F1) as an acceptance script for the oral.
