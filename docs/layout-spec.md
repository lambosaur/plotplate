# Layout file reference

[← README](../README.md) · [workflow](workflow.md) · [design notes](design-notes.md)

## Scope

This file describes `layout.yaml`, the single source of truth for one figure.
Python, the preview, the Inkscape SVG and the generated LaTeX all read it.

## Coordinates and units

- All lengths are millimetres.
- Font sizes and line widths are points (1/72 inch).
- Page coordinates have their origin at the top-left corner of the figure area. x grows to the right,
  y grows downwards.
- A box is `[x, y, w, h]`: top-left corner, then width and height.
- Sizes are final print sizes.
  LaTeX includes panels at scale 1.0, so a 6 pt label prints at 6 pt.

## Complete example

```yaml
schema: 1
name: fig1                  # also the name of the generated fig1.tex
journal: nature             # bundled preset name, or a path to a preset YAML
style_files: [../style.yaml]  # project-wide style, relative to this file
style:                      # inline overrides, applied last
  font: {small: 5.5}
page:
  width: double             # a number (mm) or a width name from the journal preset
  height: 150
guides:                     # named alignment lines, page coordinates
  x: {left_axis: 11}
  y: {row1_bottom: 46}
mosaic:                     # optional: computes boxes of panels without an explicit box
  rows: [AB, CC, DE]        # one character per cell, "." for an empty cell
  heights: [55, 42, 45]     # relative row heights
  widths: [1, 1]            # relative column widths
  gap: [4, 4]               # [between columns, between rows], mm
panels:
  A:
    axes:
      roc: {left: left_axis, top: 5, right: 44, bottom: row1_bottom}
      prc: {box: [55, 5, 33, 41]}
  B:
    box: [93.5, 0, 89.5, 55]  # explicit box wins over the mosaic
    label: {text: "b", offset: [0, 0]}
  C:
    axes:
      scatter: {left: left_axis, top: 64, right: 181, bottom: 94, ncols: 4, wgap: 9}
  D:
    margins: [11, 4, 2, 6]  # shorthand for one axes named "main": [left, top, right, bottom]
    source: plots/boxplot.py  # optional; default is panel_D_*.py next to the layout
  E:
    label: false            # no letter for this panel
```

## Top-level keys

| key | required | meaning |
| --- | --- | --- |
| `schema` | no (default 1) | file format version |
| `name` | no (default file stem) | figure name, used for `<name>.tex` and the Overleaf folder |
| `journal` | no | journal preset: page widths, maximum height, style limits |
| `style_files` | no | style YAML files merged in order, relative to the layout file |
| `style` | no | inline style overrides |
| `page.width` | yes | mm, or a width name of the journal preset (`single`, `double`…) |
| `page.height` | yes | mm, or `solve` to compute it from the constraints |
| `labels` | no (default `id`) | `id`: the panel key is its letter. `auto`: keys are stable ids and letters are assigned in reading order |
| `guides.x`, `guides.y` | no | named vertical and horizontal lines |
| `mosaic` | no | grid shorthand for panel boxes |
| `constraints` | no | relations between panels, from which boxes are solved ([constraints.md](constraints.md)) |
| `panels` | yes | panel entries, in reading order |

## Identity: page, panels, axes

Three levels, each with its own name:

| level | name | where it comes from | user-facing |
| --- | --- | --- | --- |
| figure | the layout file and `name:` | you | the figure number in the manuscript |
| panel | the panel key (`A`, or `roc_prc` with `labels: auto`) | you, or a letter read from a PDF | the letter, drawn by LaTeX or `plotplate export` |
| plotting area | the axes name (`roc`, `heatmap`, `ax1`) | you, or `plotplate from-pdf --axes` | usually none; add sub-labels in the panel code if needed |

A panel is one matplotlib figure, whatever it contains: one axes, a grid of axes, or a library figure
such as a seaborn clustermap (which is itself several axes).
Its axes entries name the areas you want to place or align; areas you do not name are left to
matplotlib.
Sub-labels inside a panel (A1, A2 or a, b) are text drawn by the panel code, not layout entries; only
panel letters are drawn by LaTeX.

## Panel keys and letters

A panel's key identifies it everywhere: `layout.yaml`, `panels/<key>.pdf`, and the notebook named
`panel_<key>_*.py`.

- `labels: id` (default): the key is also the letter, so `A` is panel A. Simple, but re-lettering a
  figure means renaming keys, notebooks and files.
- `labels: auto`: keys are stable names (`roc_prc`, `heatmap`), and letters follow the reading order
  of the boxes.
  Inserting a panel re-letters the others without renaming anything.
  `label: {text: "x"}` still overrides one panel, and `label: false` leaves a panel unlettered (and
  unlabelled in the reading order).

`plotplate relabel layout.yaml` freezes the current letters as explicit `label` entries.

## Panel entries

| key | meaning |
| --- | --- |
| `box` | `[x, y, w, h]`; required unless the panel appears in `mosaic` |
| `label` | `false`, or `{text, offset}`; default text is the panel name in the preset's case |
| `axes` | named plotting areas, see below |
| `margins` | `[left, top, right, bottom]` inside the box; creates axes `main` |
| `source` | script that draws the panel, for `plotplate build` |

A panel without `axes` or `margins` gets one axes from `panel.subplots()`, placed by constrained
layout inside the box.

## Axes entries

An axes entry is a plotting area: the rectangle of the spines, without tick labels.
Tick labels, axis labels and titles go into the space around it, inside the panel box.

| key | meaning |
| --- | --- |
| `box` | `[x, y, w, h]` |
| `left`, `top`, `right`, `bottom` | edges; each is a number or a guide reference |
| `ref` | `page` (default) or `panel`: origin of the numbers |
| `nrows`, `ncols` | split the area into a grid of axes |
| `width_ratios`, `height_ratios` | relative column widths and row heights of the grid (lengths set `ncols`/`nrows`) |
| `wgap`, `hgap` | space between grid cells, mm |

A guide reference is a guide name with an optional offset: `left_axis`, `row1_bottom-2.5`.
Guides are always page coordinates, also when `ref: panel`.

Two axes in different panels line up exactly when they use the same guide.
This works although each panel is a separate matplotlib figure, because every panel file has exactly
the size of its box.

## Panels spanning rows or columns

Boxes are free rectangles, so any arrangement works, including panels spanning several rows.
With `mosaic`, repeat a letter over the cells it covers; use as many cells as the finest division
needs:

```yaml
page: {width: double, height: 168}
mosaic:                  # tall panel D on the right of A, B, C; E below D
  rows: [AD, BD, CD, CE]
  heights: [45, 40, 39, 35]
  widths: [80, 99]
  gap: [4, 3]
```

A row whose panels do not share column boundaries with the rows above needs a finer grid (for example
six columns, with `AABBCC` above `DDDEEE`), or explicit `box` entries.

## Style

The style merges four layers, later wins:

1. package defaults (`src/plotplate/presets/default_style.yaml`),
1. the journal preset `style`,
1. each file of `style_files`,
1. the layout `style`.

| key | meaning |
| --- | --- |
| `font.family` | font families in order of preference |
| `font.size` | axis labels, legend titles (pt) |
| `font.small` | tick labels, legend entries (pt) |
| `font.large` | axes titles (pt) |
| `font.min` | smaller text is an error |
| `font.max` | larger text is a warning |
| `font.max_spread` | if set, a larger difference between font sizes in one panel is a warning |
| `lines.width`, `lines.axes` | data lines, spines and patch edges (pt) |
| `lines.min` | thinner visible lines are a warning |
| `ticks.length`, `ticks.width`, `ticks.pad` | tick geometry (pt) |
| `panel_label.size`, `.weight`, `.case`, `.offset` | panel letters, drawn by LaTeX |
| `export.formats`, `export.dpi` | files written by `Panel.save` |
| `export.transparent` | save panels without a background, so overlapping panel boxes do not paint over each other |
| `colors` | named colors shared by all panels (`panel.colors`) |
| `color_cycle` | default color cycle: a bundled palette name (`plotplate palettes`) or a list of colors |
| `rc` | raw matplotlib rcParams, applied last |

## Journal presets

`plotplate journals` lists the bundled presets with their verification status.
[journal-specs.md](journal-specs.md) documents every value and its source.

| key | meaning |
| --- | --- |
| `name`, `description`, `applies_to` | identification |
| `sources`, `verified` | where the values come from and how they were checked |
| `page.widths`, `page.max_height` | named column widths and maximum figure height (mm) |
| `style` | style overrides (font limits, panel labels, line widths, export dpi) |
| `deliverable.composite` | the journal wants one file per figure with all panels |
| `deliverable.formats` | accepted final file formats; `plotplate export` warns about others |
| `deliverable.raster_dpi` | default resolution for raster exports |
| `notes` | requirements the package cannot check automatically |

Copy a bundled preset next to your layout and reference it by path to adjust it.
