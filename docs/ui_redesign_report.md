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
