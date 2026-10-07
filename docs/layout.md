# The layout file

[← README](../README.md) · [the Python API](python-api.md) · [design notes](design-notes.md)

`layout.yaml` is the single source of truth for one figure: its size, its panels, and the rules they
follow.
The Python API, the viewer, the checks and the generated LaTeX all read it, and nothing else
configures a figure.

Every key a layout may hold is listed in `src/plotplate/schema.py`, which is also what checks the
file: a key plotplate cannot read is refused by name, with the nearest legal one suggested.

## The levels

| level | what it is | who defines it |
| --- | --- | --- |
| **page** | the physical sheet: paper size, margins, room for the caption | optional `page:` section |
| **area** | the figure's own box, the thing the manuscript calls "Figure 1" | `area: {width, height}` |
| **panel** | one matplotlib `Figure`, saved as one file, carrying one letter | `panels:` entries |
| **axes** | a plotting area inside a panel | `axes:` entries, or named in the panel code |

A panel *is* a matplotlib figure: `savefig` writes exactly one panel.
A `SubFigure` cannot be saved on its own, and libraries such as seaborn's clustermap always create
their own figure, which is why "one panel = one figure = one file" is the rule here, and why there is
no level between panel and axes.

## Where these words come from

Most of them are borrowed, so that a layout file can be read by someone who has never seen plotplate.
One is ours, and a few are borrowed words that mean something slightly different elsewhere.

| this project | matplotlib | LaTeX | Illustrator / Inkscape | journal guidelines |
| --- | --- | --- | --- | --- |
| page | - | the page (`\paperwidth`) | document, page | page size |
| margins | - | the body, `geometry` margins | margins | margins |
| **area** | `Figure` | the `\includegraphics` box | artboard, canvas | "the figure" |
| panel | `Figure` (one per file) | a `subfigure` | an object group | **panel** (`a`, `b`, `c`...) |
| axes | **`Axes`** | - | - | a plot, a chart |
| axis guide | - | - | - | - |
| page guide | - | - | **guide** (a non-printing line) | - |
| gutter | `wspace`, `hspace` | `\columnsep` | gutter (between columns) | space between panels |
| caption | - | `\caption` | - | caption, or **legend** |

- **area** is the only word invented here.
  The candidates were taken: "figure" is what matplotlib calls a panel *and* what the manuscript calls
  the whole thing, "page" is the sheet, and "artboard" belongs to a drawing program.
  So the figure's own box is the *area*.
- **axes**, in matplotlib and here, is one whole plot, not the two lines through the origin.
  This trips up everyone once; matplotlib's own documentation says as much.
- **gutter** in bookbinding is the inner margin of a page; here it is only the space between two
  panels, as in a column layout.
- a **page guide** is the drawing program's guide: a line you put on the sheet to arrange things
  against.
  An **axis guide** is the other thing plotplate calls a guide, and it is a reference: an axes can be
  *placed at* it ([alignment.md](alignment.md#three-kinds-of-line-and-when-they-disagree)).
- **caption** is LaTeX's word; most life-science journals say *legend* for the same text. plotplate
  never typesets it, it only keeps room for it (`page.caption`).

## Coordinates and units

- All lengths are millimetres.
- Font sizes and line widths are points (1/72 inch).
- Page coordinates have their origin at the top-left corner of the figure area. x grows to the right,
  y grows downwards.
- A box is `[x, y, w, h]`: top-left corner, then width and height.
- Sizes are final print sizes.
  LaTeX includes panels at scale 1.0, so a 6 pt label prints at 6 pt.

| system | unit | origin | used by |
| --- | --- | --- | --- |
| sheet | mm | top-left of the paper | the page view, caption fit |
| **layout** | mm | top-left of the **area** | everything in `layout.yaml`, `geometry` in panel files, `alignment.yaml` |
| figure fraction | 0-1 | bottom-left of the panel | matplotlib (`add_axes`, `get_position`) |
| data | your units | your axes | your plotting code |

Layout millimetres are the common currency: panel boxes, axes rectangles, guides, measured geometry
and alignment rules all live there, which is what lets panels drawn by different scripts be compared.

## File names, and several layouts for one figure

The layout of a figure is `layout.yaml`, in the figure's own folder.
Alternatives live next to it as `layout.<variant>.yaml` (`layout.detected.yaml`,
`layout.optimized.yaml`, `layout.poster.yaml`), share the same panels, and are all offered by
`plotplate view`; see [layout.md](layout.md#file-names-and-several-layouts-for-one-figure).
Commands accept the folder as well as the file.

## Complete example

```yaml
schema: 1
name: figure_1              # also the name of the generated figure_1.tex
journal: nature             # bundled preset name, or a path to a preset YAML
style_files: [../style.yaml]  # project-wide style, relative to this file
style:                      # inline overrides, applied last
  font: {small: 5.5}
page:                       # the sheet the figure is printed on (optional, but checked)
  paper: a4                 # a4, letter, or [width, height] in mm
  margins: {left: 13.5, right: 13.5, top: 25, bottom: 25}
  caption: 25               # space kept under the figure for its caption
area:                       # the figure itself: what the panel coordinates are relative to
  width: double             # a number (mm) or a width name from the journal preset
  height: 150               # or `solve`, with a `constraints:` section
gutter: 4                   # millimetres between panels: one number for the whole figure
code_dir: code              # where the panel scripts are (default: beside this file)
output_dir: output          # where a build writes (default: beside this file)
guides:                     # named alignment lines, page coordinates
  x: {left_axis: 11}
  y: {row1_bottom: 46}
mosaic:                     # optional: computes boxes of panels without an explicit box
  rows: [AB, CC, DE]        # one character per cell, "." for an empty cell
  heights: [55, 42, 45]     # relative row heights
  widths: [1, 1]            # relative column widths
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
    source: plots/boxplot.py  # optional; default is panel_D_*.py inside code_dir
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
| `area.width` | yes | mm, or a width name of the journal preset (`single`, `double`…); `page.width` in older layouts |
| `area.height` | yes | mm, or `solve` to compute it from the constraints |
| `page` | no (a4 assumed) | the physical sheet: `paper` (a4, letter, `none`, or `[w, h]`), `margins`, `caption` (mm), `outlines` (mark the panel boxes on the page view) |
| `gutter` | no (default 4) | millimetres between panels: one number, or `[horizontal, vertical]`. The mosaic computes the boxes with it, and the optimizer holds every gutter at it |
| `code_dir` | no (default `.`) | folder holding the panel scripts, relative to the layout |
| `output_dir` | no (default `.`) | folder for everything a build writes, relative to the layout |
| `labels` | no (default `id`) | `id`: the panel key is its letter. `auto`: keys are stable ids and letters are assigned in reading order. `false`: no letters at all |
| `notes` | no | free text, for whatever the file should say to its next reader |
| `guides.x`, `guides.y` | no | named vertical and horizontal lines an axes can be placed against |
| `page_guides.x`, `page_guides.y` | no | unnamed lines to arrange panels against; drawn across the whole sheet |
| `mosaic` | no | grid shorthand for panel boxes |
| `constraints` | no | relations between panels, from which boxes are solved ([layout.md](layout.md#constraints-boxes-computed-not-typed)) |
| `panels` | yes | panel entries, in reading order |

## Identity: page, panels, axes

Three levels, each with its own name:

| level | name | where it comes from | user-facing |
| --- | --- | --- | --- |
| figure | the layout file and `name:` | you | the figure number in the manuscript |
| panel | the panel key (`A`, or `roc_prc` with `labels: auto`) | you, or a letter read from a PDF | the letter, drawn by LaTeX or `plotplate export` |
| plotting area | the axes name (`roc`, `heatmap`, `ax1`) | you, or `plotplate detect --axes` | usually none; add sub-labels in the panel code if needed |

### The panel key is an id; the letter is what the reader sees

They are two different things, and only one of them is yours to change freely:

| | the key | the letter |
| --- | --- | --- |
| written | the mapping key under `panels:` | `label: {text: b}`, or the key itself with `labels: id` |
| used by | `panels/<key>.pdf`, the code that draws the panel, `alignment.yaml`, `plotplate check` | nothing: it is only drawn |
| change it | while the panel has no file yet; after that with `plotplate merge <layout> <key> --as <new>`, renaming the panel code with it | whenever you like, in the layout or in `plotplate view` |

So a figure whose panels must carry letters in an unconventional order does not renumber its keys:

```yaml
labels: auto              # keys are ids, letters are handed out in reading order...
panels:
  survival:  {box: [...], label: {text: c}}   # ... except where you say otherwise
  cohort:    {box: [...], label: {text: a}}
  qc:        {box: [...], label: {text: b}}
```

`labels: auto` is worth setting as soon as the keys mean something (`survival`, `qc`, or the `S01`,
`S02` that detection produces): the letters then follow the boxes, and an explicit `label.text` wins
over the automatic one wherever the reading order is not what you want.
With the default `labels: id` the key *is* the letter, which is convenient for a figure whose panels
are simply A, B, C, and is why `plotplate view` refuses to change the key of a panel that has already
been drawn: that key is the name of its file.

A panel is one matplotlib figure, whatever it contains: one axes, a grid of axes, or a library figure
such as a seaborn clustermap (which is itself several axes).
Its axes entries name the areas you want to place or align; areas you do not name are left to
matplotlib.
Sub-labels inside a panel (A1, A2 or a, b) are text drawn by the panel code, not layout entries; only
panel letters are drawn by LaTeX.

## Panel letters

Panel letters are **never drawn inside a panel file**.
They are stamped on the assembled figure — by the generated LaTeX, and identically by
`plotplate build` / `export` — at the millimetre the layout gives ([latex.md](latex.md)):

```latex
\put(0.00,150.00){\makebox(0,0)[lt]{{\fontsize{8pt}{8pt}\selectfont\sffamily\bfseries a}}}%
```

Two consequences worth knowing:

- **They take no space.** `subcaption` / `subfigure`, the usual LaTeX way, puts `(a)` on a line of its
  own under each panel and makes the figure taller, so the panels have to shrink to compensate.
  Here the letter sits over the panel's own margin — the strip that holds the tick labels — and the
  assembled figure is exactly the size `area:` says.
- **One setting, three renderers.**
  `panel_label` in the style sets size, weight, case, offset, `format` (`"({letter})"` for `(a)`) and `latex_font`
  (the LaTeX font commands, `\sffamily` by default).
  The generated LaTeX carries them on each letter rather than defining anything, and the preview and
  the export read the same settings, so what you see is what compiles.

What journals actually require is case, weight and font — not a clearance in millimetres.
The bundled presets record it per journal (`plotplate journals`): Nature lower-case bold 8 pt, Science
and PLOS upper-case bold, Cell upper-case bold, Genome Research upper-case bold 12 pt; each with its
source in `presets/journals/`.
The offset defaults to the panel box's top-left corner; move it with `label: {offset: [x, y]}` (mm)
when a panel's content reaches into that corner, as an image panel does.

## Page guides

```yaml
page_guides:            # layout millimetres, like everything else
  x: [91.5]             # a vertical line down the middle of the figure
  y: [62, 128]          # two horizontal ones
```

Scaffolding for the author: no axes is ever placed against a page guide, and deleting one moves no
panel.
What it does do is stop `plotplate optimize` — panels never grow across a page guide, and a band
between two of them stays open ([optimize.md](optimize.md#page-guides-are-hard-stops)).
`plotplate view` draws them across the whole sheet, margins included (the way a guide dragged off a
ruler behaves in a drawing program), and panels stick to them while being dragged, which is what they
are for: putting two panels in different rows on the same line.

Add, move and remove them on the page with `plotplate view`, or write them here by hand.
They scale with the figure (`plotplate detect --width`), and they travel with the layout that declares
them.
A layout with no `page_guides:` is shown with four — the margins of the sheet, which are the lines a
figure is arranged against first; they become part of the file as soon as you save.
A guide that ends up outside the sheet is dropped rather than stored where nothing can reach it.
For lines an axes is actually *placed against*, use named `guides:` instead — the difference is in
[alignment.md](alignment.md#three-kinds-of-line-and-when-they-disagree).

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
area: {width: double, height: 168}
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
| `panel_label.format`, `.latex_font` | `"({letter})"` for (a) (b); the LaTeX font commands (`\sffamily`, `\fontspec{Arial}`) |
| `export.formats`, `export.dpi` | files written by `Panel.save` |
| `export.transparent` | save panels without a background, so overlapping panel boxes do not paint over each other |
| `colors` | named colors shared by all panels (`panel.colors`) |
| `color_cycle` | default color cycle: a bundled palette name (see `presets/palettes.yaml`) or a list of colors |
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

## Constraints: boxes computed, not typed

Typed numbers stop being true as soon as something changes.
Switch a figure from Nature (183 mm) to Cell (174 mm) and every box needs editing; the gaps drift, and
the near-misses `plotplate check --near` reports appear.
Relations survive those edits: state them once, and the boxes follow.

The solver is Cassowary, from `kiwisolver`, which matplotlib already installs, so this costs no new
dependency.

### Example

```yaml
area: {width: double, height: solve}   # solve: computed from the rules below
constraints:
  defaults: {gap: 4}
  rules:
    - row: {panels: [A, B], top: 0, height: 55, equal: true, fill: true}
    - row: {panels: [C], height: 42, fill: true}
    - row: {panels: [D, E], height: 45, equal: true, fill: true}
    - gap: {below: A, above: C}
    - gap: {below: C, above: D}
panels: {A: {}, B: {}, C: {}, D: {}, E: {}}
```

This gives the demo figure exactly: `A [0, 0, 89.5, 55]`, `B [93.5, 0, 89.5, 55]`,
`C [0, 59, 183, 42]`, and a page height of 150 mm (55 + 4 + 42 + 4 + 45).
Change `area.width` to 174 and the panels become 85 mm wide, with the gaps still 4 mm.

### Rules

Shorthands, which expand into the primitives below:

| rule | meaning |
| --- | --- |
| `row: {panels: […], gap, equal, fill, top, bottom, height, left, right, width}` | panels left to right, sharing top and bottom; `equal` gives them equal widths; `fill` spans the page; `top`/`bottom`/`height` apply to the row, `left`/`right` to its ends |
| `column: {panels: […], …}` | the transpose: top to bottom, sharing left and right |

Primitives:

| rule | meaning |
| --- | --- |
| `align: {edge: left\|right\|top\|bottom, of: [A, B, …]}` | those panels share that edge |
| `equal: {what: width\|height, of: [A, B, …]}` | same size in that direction |
| `gap: {after: A, before: B, value: 4}` | horizontal space between two panels |
| `gap: {below: A, above: C, value: 4}` | vertical space |
| `size: {panel: A, width: 60, height: 40}` | fixed size |
| `aspect: {panel: B, ratio: 1.6}` | width = ratio × height |
| `pin: {panel: A, left: 0, bottom: page}` | an edge at a number, or at the page edge |

Every rule takes `strength: required` (default), `strong`, `medium` or `weak`.
A preference bends when it conflicts with a required rule, which is how you say "prefer these equal,
but the page width wins".

`defaults: {gap: 4}` sets the gap used by rules that do not give one.

### Explicit boxes still work

A panel with a `box` is pinned, and the rules position the others around it.
That is the way to fix one panel (a photograph at its native aspect, say) and let the rest follow.

### Diagnostics

- **Conflicts** raise an error naming the constraint that could not be added.
- **Too few rules** are reported by `plotplate check` as `under-constrained`, listing the panels that
  took the minimum size or the whole page.
- `plotplate resolve layout.yaml -o frozen.yaml` writes the solved boxes as plain numbers and drops
  the `constraints` section, when you want to stop solving and edit by hand.

### Constraints, guides and the optimizer

Constraints compute boxes from relations you wrote; [`plotplate optimize`](optimize.md) computes them
from boxes that already exist, by spending the white space between them.
Use the optimizer on a draft read back from an old figure, and constraints for the figure you
maintain.
An optimized layout is plain numbers, so writing constraints afterwards is how you keep the result
alive through the next change of journal.

Three mechanisms, at different levels:

| level | file | what it does |
| --- | --- | --- |
| panel boxes | `constraints` in `layout.yaml` | computes where panels sit |
| axes inside panels | `guides` in `layout.yaml` | shared coordinates for plotting areas across panels |
| verification | `alignment.yaml` | measures what the drawn panels actually did ([alignment.md](alignment.md)) |

Constraints do not replace the guides: they place panel boxes, while guides place the axes inside
them.
Both end up as numbers the panel code reads.

## Older layouts

Layouts that use `page: {width, height}` for the figure box keep working: when there is no `area:`
section, `page:` is read as the box, exactly as before.
