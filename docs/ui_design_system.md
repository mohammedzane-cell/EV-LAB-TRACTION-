# EV-LAB design system

**EV-LAB · ELECTRIC TRACTION RESEARCH STUDIO.** A computational laboratory for induction-motor
traction: one identified motor, one chain of models. The interface should read like a precise
instrument: a deep graphite foundation, one electric-cyan accent that marks *where you are and what
acts*, quiet rules, and data drawn as measurements.

The rules below hold for every workspace and for any future module. Source of truth:
`src/evlab/palette.py` (colours and font stacks, no Qt), `src/evlab/gui/style.qss` (component
styles, `@token`s replaced by `gui/theme.py`), `src/evlab/gui/widgets.py` (components) and
`src/evlab/gui/glyphs.py` (icons, logo).

## 1. Principles

1. **Physics first.** The interface only shows what `core/` computes. No decorative number, fake
   status or hardware indicator. Provenance (démo / synthétique / référence) is always visible.
2. **One accent, one meaning.** Electric cyan marks the active workspace, the primary action, the
   focus and the identity of readouts. It is never a data-series colour.
3. **Inputs are quiet, results are lit.** Input sections sit in the left panel, with an
   accent-ticked title; results are raised panels, readout tiles and plots.
4. **Charts are instruments.** Explicit units, subtle grids, legends outside the data, a crosshair
   that reads the plotted samples, never interpolated values.
5. **French GUI, decimal comma, SI inside.** Conversions only at the edge (CLAUDE.md). The product
   name and subtitle are the only English text.

## 2. Colour tokens

Two themes with the same roles. « Studio graphite » (`dark`) is the default; « Studio clair »
(`light`) carries the same identity on a light workspace. The PDF figures always use the light
palette (they are printed). Every text pair in `TEXT_PAIRS` is tested for a contrast ≥ 4,5:1.

| Role | Graphite | Clair | Use |
|---|---|---|---|
| `surface` | `#0A0F15` | `#E4E9EF` | sidebar, header, menu bar, status bar |
| `bg` | `#0E141B` | `#EDF0F4` | workspace base |
| `card` | `#141C26` | `#FFFFFF` | panels, input sections, tables |
| `input` | `#0F161E` | `#FFFFFF` | fields |
| `tab` | `#18212C` | `#E8ECF1` | secondary surface: table headers, secondary buttons |
| `hover` | `#1C2733` | `#E2E8EF` | hover |
| `border` / `divider` | `#243142` / `#1B2531` | `#CDD5DF` / `#E1E6EC` | panel edges / inner rules |
| `text` / `muted` | `#E3E9F1` / `#8F9DB0` | `#111923` / `#556274` | text / labels, units, captions |
| `primary` (accent) | `#22C3D6` | `#0A6E7B` | active state, primary action, focus |
| `primary_hover`, `_pressed`, `_disabled` | `#4FD3E2`, `#149BAD`, `#1C4A52` | `#085C67`, `#064C55`, `#9FC6CC` | accent states |
| `on_primary` | `#031317` | `#FFFFFF` | text on the accent |
| `accent_soft` / `selection` | `#0F3640` / `#103844` | `#D9F1F4` / `#D3EEF2` | active nav row, selections, progress |
| `demo_*` | amber `#2B2212` / `#F0C36A` | `#FFF3D6` / `#7A4E00` | démo / synthetic provenance |
| `alert_*` | `#33191B` / `#FF8F87` | `#FDECEC` / `#A8231B` | errors, out-of-model warnings |
| `success`, `note`, `info` | `#48D597`, `#E9B15F`, `#7AB6FF` | `#17703A`, `#7F4B07`, `#1F5FBF` | states in text |
| `plot_bg`, `plot_fg`, `grid` | `#0F161E`, `#A9B6C6`, `#1F2A37` | `#FFFFFF`, `#384352`, `#DDE3EA` | plots |

**Data series** (`SERIES`, the same in both themes and in the PDF, so a quantity keeps its
colour everywhere): blue `#2F6FDB`, green `#2E9E5B`, orange `#E08A1E`, red `#D64541`, light
blue, dark green, brown, grey. Red is reserved for limits and envelopes, grey for context
(dominated or base points). The accent cyan is never a series.

## 3. Typography

Stacks (first available font wins), defined in `palette.py`:

| Stack | Fonts | Use |
|---|---|---|
| UI `@font` | Segoe UI Variable Text → Segoe UI → Inter | all text |
| Display `@display` | Segoe UI Variable Display → Segoe UI Semibold → Inter Display → Inter | wordmark, workspace title, readout values |
| Mono `@mono` | Cascadia Mono → JetBrains Mono → Consolas → DejaVu Sans Mono (registered from matplotlib) | workspace index, crosshair readout |

Readout values use **tabular figures** (`tnum`, `ReadoutLabel`), so the tiles of a row line up. They are
not enabled application-wide: spin boxes size themselves on their widest value, and tabular digits
would widen them and squeeze the labels of the 300 px input panels.

| Level | Size | Weight | Colour |
|---|---|---|---|
| Wordmark « EV-LAB » | 15 pt display | 600 | text, hyphen in the accent |
| Subtitle | 6,5 pt, letter-spaced 1,2 px, 2 lines | 600 | muted |
| Workspace title (header) | 15 pt display | 600 | text; index « 01 » in mono, accent |
| Workspace caption | 9 pt | 400 | muted |
| Panel title (`#cardTitle`) | 10,5 pt | 600 | text |
| Input section title (`QGroupBox`) | 10 pt | 600 | text, 2 px accent tick |
| Section header (`#sectionHeader`) | 8 pt capitals, letter-spaced | 600 | muted |
| Body, labels, values | 10 pt | 400 | text |
| Units | spin-box suffix; in tiles 55 % of the value size | 400 | muted |
| Readout value (`#kpiValue`) | 17 pt display | 600 | text |
| Chart ticks and axis labels | 8,5 pt | 400 | `plot_fg` |
| Chart readout (`#plotReadout`) | 8 pt mono | 400 | muted |
| Help, hints | 8,5–9 pt | 400 | muted |
| Course equations | monospace in the accent colour (`page_html`) | 400 | accent |

## 4. Layout

| Element | Value |
|---|---|
| Spacing scale | 2 · 4 · 8 · 10 · 12 · 14 · 18 px |
| Sidebar | 224 px, or 60 px compact (icons) below 1440 px of window width (laptops) or on request |
| Header | 8 px vertical padding, title line and caption, actions on the right |
| Workspace margins | 10 px sides, 8 px top |
| Left input panel | fixed width per workspace (300 px for most), scrolls vertically, never sideways |
| Control height | 18 px content + padding (≈ 26 px), primary buttons 26 px minimum |
| Radii | 3 px chips · 4 px controls and tiles · 6 px panels and input sections |
| Lines | 1 px borders and rules; accent marks 2 px (nav, section title) or 3 px (readout tile, warning) |
| Plots | expand with the window, minimum height 120 px (matplotlib canvas 260 px); legend above, readout below |
| Minimum window | 1100 × 650 px; maximised start below 1440 × 900 (laptops, 150 % scaling) |

## 5. Components

| Component | API | Look |
|---|---|---|
| Sidebar navigation | `MainWindow.nav_buttons`, `help_buttons` | groups Machine · Véhicule · Électromagnétisme · Conception · Ressources; row = glyph + « 01 » + name; active row: soft accent fill, 2 px accent edge; « ? » opens the course page; Ctrl+1…8 |
| Workspace header | `ws_index`, `ws_title`, `ws_caption`, `motor_context`, `motor_demo` | workspace number, title, caption; motor of the chain and its démo chip; actions « Cours », « Rapport PDF » |
| Input section | `QGroupBox` in `scroll_panel(...)` | card surface, title with an accent tick |
| Parameter field | `french_spin(lo, hi, decimals, unit, value)` | right-aligned value, unit as suffix, decimal comma, accent focus ring |
| Panel | `card(title)` → (frame, body, header) | raised card, title left, chips or actions right |
| Section header | `section_header(text)` | small capitals, letter-spaced, muted |
| Divider | `divider()` | 1 px rule |
| Readout tile | `KpiTile(title, unit)`, `set_value(text)` | muted title, large value, unit smaller and muted (`ReadoutLabel`: `text()` stays « value unit »), 3 px accent edge |
| Provenance chip | `chip(text, kind)`; kinds `demo`, `alert`, `source`; `set_demo_chip(lbl, labels)` | 3 px radius tag; the tooltip lists what is démo |
| Warning | `QLabel` with `role="warning"` | alert surface, 3 px alert edge |
| Text roles | `role` = `muted`, `hint`, `success`, `error`, `note`, `info` | colour only |
| Buttons | `QPushButton`; `role="primary"` (one per workspace: the main computation), default (secondary), `role="ghost"` | accent fill / secondary surface / text-only |
| Tables | `QTableWidget` | quiet inner rules, headers in muted 8,5 pt on the secondary surface |
| Chart panel | `external_legends(root)`, `flexible_plots(root)`, `inspect_plots(root)` | legend row above, plot, readout row below; crosshair; zoom, pan, « A » (reset), right-click export |
| Icons | `glyphs.icon(name, colour, size, active)`, `glyphs.logo(...)` | 24-grid line glyphs, 1,6 px strokes, round ends; rendered for the screen's pixel ratio |

## 6. Charts

- Axis labels carry the unit in parentheses: « Vitesse (tr/min) », « Couple (N·m) ».
- Grid: both axes, alpha 0,25, in the `grid` colour; plot background `plot_bg`.
- Legends never cover data: `external_legends` moves each one above its plot.
- **Inspection**: the crosshair follows the cursor; the readout gives the cursor in the axis units,
  then the nearest *computed* sample of each named curve (no interpolation, no recomputation).
  Zoom (wheel), pan (drag), reset (« A »), export to PNG, SVG or CSV (right-click → Export…).
- Provenance: curves from démo data say so in their legend name (« points d'essai (démo) »), and
  the panel carries the démo chip.
- matplotlib (tab 3 map, PDF figures): `theme.mpl_rc(name)` from the same palette; the PDF is
  always light.

## 7. Adding a module

1. Inputs in `QGroupBox`es inside `scroll_panel(left)`; one primary button.
2. Results in `card(...)` panels; readouts in `KpiTile`s; démo provenance with `set_demo_chip`.
3. Plots as `pg.PlotWidget` with unit-bearing axis labels and named curves; the main window applies
   legends, sizing, inspection and theme to every plot of every tab.
4. A new workspace: add its class to `TAB_CLASSES`, a caption to `CAPTIONS`, a glyph to
   `glyphs.WORKSPACE_GLYPHS` and its index to a `NAV_GROUPS` entry.
5. Colours only by role (`theme.color(role)` or `@role` in style.qss); no hex value in a tab.
