# The Python API

[← README](../README.md) · [the layout file](layout.md) · [alignment](alignment.md)

This is everything a panel script calls.
The short version: plotplate gives you a matplotlib figure of exactly the right size, and takes it
back when you are done.
What happens in between is your code, unchanged.

## A panel script

```python
import plotplate as pp

layout = pp.Layout.load("layout.yaml")  # the file, or the folder holding it
panel = layout.panel("A")  # KeyError if the layout has no panel A

fig = panel.figure()  # exactly the size of box A, journal style applied
ax = fig.add_subplot()  # ... or plt-style, or gridspec, or seaborn
ax.plot(fpr, tpr)
ax.set_xlabel("False positive rate")

panel.save(fig)  # the files, and the checks
```

There is no plotplate way of plotting.
`panel.figure()` returns a plain `matplotlib.figure.Figure`, and everything that works on one works
here.

| call | what it does |
| --- | --- |
| `pp.Layout.load(path)` | reads a layout file, or the `layout.yaml` of a figure folder |
| `layout.panel("A")` | a handle on one panel. The panel has to exist in the layout: `KeyError` otherwise, because the size has to come from somewhere |
| `panel.figure()` | a figure of exactly the panel's box, with the journal style applied (globally, so legends and titles created later get it too) |
| `panel.save(fig)` | writes `<output_dir>/panels/A.pdf`, `.svg`, `.png` and `A.json`, and runs the checks |
| `panel.context()` | in a notebook: the whole figure with this panel outlined. Writes nothing |

### What `panel.save` does, and why not `plt.savefig`

It writes the three image files with the settings the assembly depends on
(`bbox_inches=None`, `pad_inches=0`, no timestamps), so the file is exactly the size of the box,
byte-stable between runs, and placeable at scale 1.0.

Then it runs the checks, and warns about everything it finds: fonts below the journal's minimum, text
clipped by the panel edge, lines too thin to print, axes that moved off their rectangle.
These are the things a figure cannot show you until it is too late.
`panel.save(fig, strict=True)` raises instead of warning, for a pipeline that should stop.

And it writes `A.json` beside the images: where every visible axes ended up, in page millimetres.
That file is the only input to the alignment check, which is how `plotplate check` can say that two
panels drawn by two different scripts did not line up.

`panel.save(fig, formats=["pdf"])` narrows the formats; `source="panel_A.py"` records what drew it.

### Looking at the whole figure while drawing one panel

```python
panel.context()  # a notebook cell of its own, after save
```

It composes the figure from the panel files on disk — so neighbours appear as they were last saved,
and this panel as you just saved it — and returns an image.
Nothing is written next to the layout.

## When panels must line up with each other

Yes, this works across panels, and it is the only reason the mechanism exists.
Two panels are two separate matplotlib figures drawn by two separate scripts, which never see each
other.
What makes their spines land on the same line is that both are *declared* on it:

```yaml
guides:
  x: {left_axis: 11}        # one line, named once
panels:
  A: {axes: {roc: {left: left_axis, top: 5, right: 44, bottom: 45}}}
  C: {axes: {scatter: {left: left_axis, top: 64, right: 181, bottom: 94}}}
```

```python
ax = panel.axes(fig, "roc")  # creates the axes at that rectangle, in page millimetres
```

`panel.axes` converts the layout rectangle into the fraction of *this* panel's figure that it
occupies, so A's left spine and C's left spine both land at x = 11 mm of the finished figure.

- The name has to be declared in the layout: `panel.axes(fig, "roc")` raises `KeyError` if the panel
  has no `roc` entry.
  It places an axes where the layout says; it cannot invent a rectangle.
- A grid (`ncols: 4`) returns a numpy array of axes, shaped `(nrows, ncols)`.
- Nothing coordinates the two scripts at run time, which is why `plotplate check` measures the result
  afterwards and reports `align-drift` when a spine did not end up where it was declared.

Declaring axes is optional, and worth it only for what has to line up.
A panel without an `axes:` entry is free: use `fig.add_subplot`, `panel.subplots()`, a library's own
figure, anything.

### Does the layout need updating after the panels are drawn?

No. The layout leads and the panels follow: a panel drawn with plain matplotlib stays that way
forever, and nothing in the layout has to learn about its axes.
There is no sync step, and no command writes measured positions back into `layout.yaml` — if the two
ever disagree, that is something to know about, not something to paper over, and `plotplate check` is
what says so (`axes-moved`, `align-drift`).

You promote an axes into the layout when you decide it has to line up with another panel, which is a
decision, not a refresh.
The numbers for it are already measured:

```sh
plotplate check figures/figure_1 --axes
```

```yaml
  B:
    axes:
      heatmap: {left: 110, top: 11, right: 158, bottom: 45}
      row_dendrogram: {left: 101.5, top: 11, right: 109.5, bottom: 45}
      ax1: {left: 97, top: 4, right: 98.8, bottom: 11}  # name me
```

That block is in page millimetres, which is what an `axes:` entry is written in, so pasting it under
`panels:` is copying rather than estimating — including the axes a library created and you never asked
for (seaborn's dendrograms and colourbar, above).

Two things are left to a person, and they are the reasons this is not one command:

- **the names.** `ax1` is positional and says nothing; `roc` is what another panel can be aligned to,
  and what survives a revision that moves the panels around.
  `plotplate check` reports every anonymous axes (`unnamed-axes`) — finding them is mechanical, naming
  them is not.
  The `figure-panel-naming` skill is this job written down for an agent.
- **which edges should be shared.**
  That two panels *happen* to have the same baseline is not the same as deciding they must keep it.
  Writing the shared value as a named guide (`y: {row1_bottom: 45}`) is how you say it on purpose, and
  from then on `plotplate check` verifies it ([alignment.md](alignment.md)).

The cheaper alternative, when a panel only needs a stable name and not a position:
`ax.set_label("roc")` in the panel code.
The measured geometry then carries that name, and an `alignment.yaml` rule can refer to it without the
layout declaring anything.

| call | what it does |
| --- | --- |
| `panel.axes(fig, "roc")` | the declared axes, created at its rectangle |
| `panel.gridspec(fig, "tracks", nrows=3)` | a matplotlib GridSpec filling a declared region, with spans |
| `panel.subplots()` | `(fig, {name: axes})` for every declared axes; one constrained-layout axes when none is declared |
| `panel.fit(fig)` | resize a figure a library made to the panel box |
| `panel.rect(x, y, w, h)` | page mm → figure fraction, for `fig.add_axes` |
| `panel.axes_rect("roc")` | the declared rectangle, in page mm |
| `panel.mark("zero", ax=ax, x=0, y=0)` | remember a data point in page mm, for the alignment file |
| `panel.anchor("key", artist)` | remember an artist's box in page mm |
| `panel.colors`, `panel.figsize`, `panel.size_mm` | the style's named colours, and the box |

## Dos and don'ts

Measured on matplotlib 3.11 with a 120 x 60 mm panel.

| do not | what happens | do instead |
| --- | --- | --- |
| `savefig(..., bbox_inches="tight")` | the file shrank to 61.7 x 50.0 mm: the panel no longer fits its box | `panel.save(fig)` (never trims) |
| `fig.tight_layout()` with axes from `panel.axes` | nothing moves; matplotlib only warns that the axes are incompatible | leave layout-placed axes alone |
| `ax.set_position(...)` or `fig.subplots_adjust(...)` on layout-placed axes | the check reports `axes-moved` (error) | change the axes rectangle in `layout.yaml` |
| `plt.figure(figsize=...)` or `plt.subplots(figsize=...)` | the check reports `figure-size` (error) | `panel.figure()`, `panel.subplots()`, or `panel.fit(fig)` for figures made by a library |
| `fontsize=4` or other explicit small sizes | the check reports `font-too-small` (error) | the style sizes (`font.size`, `small`, `large`) |
| a legend or title created before the style is applied | default 10-12 pt text | create the figure through the panel first; it applies the style globally |

These are fine:

| do | why |
| --- | --- |
| `panel.subplots()` on a panel without `axes` in the layout | constrained layout arranges labels inside the fixed box; a two-line y label passed all checks |
| `fig.tight_layout()` or constrained layout on figures without layout-placed axes | they rearrange within the fixed size; the saved size stays exact |
| several libraries in one panel | axes from `panel.axes` can be added to any figure, including a seaborn clustermap figure |
| `panel.gridspec(...)` inside an axes region | a matplotlib GridSpec positioned in mm, with spans and nested grids |

## Labels are cut off: three fixes

`text-clipped` means some text extends beyond the panel edge.

1. **Panel without layout axes:** use `panel.subplots()` (constrained layout); labels are fitted
   automatically.
1. **Panel with layout axes:** the rectangle leaves too little room for the tick and axis labels.
   Enlarge the margin in `layout.yaml` (move the axes `left`, or the guide it uses), or shorten the
   labels.
   Moving the axes in code is not the fix: it breaks alignment with other panels, and the check
   reports it.
1. **Library figures (clustermap, Marsilea):** reduce label padding or dendrogram sizes, or give the
   main rectangle more room; `place_clustermap` and `fit_marsilea` report how many millimetres are
   missing.

## Recipe 1: free-form content

Layout: a panel with only a `box`.

```python
panel = layout.panel("A")
fig, axes = panel.subplots()  # one axes, constrained layout inside the box
ax = axes["main"]
ax.plot(values)
ax.set_ylabel("A long y label\nover two lines")
panel.save(fig)
```

## Recipe 2: a clustermap and another plot in one panel

A seaborn clustermap creates its own figure, with several axes.
It stays one panel: pin the heatmap to one layout rectangle, and add other axes to the same figure.

```yaml
B:
  box: [93.5, 0, 89.5, 55]
  axes:
    heatmap: {box: [105, 8, 40, 40]}
    box: {box: [155, 8, 26, 40]}
```

```python
panel = layout.panel("B")
with panel.style():
    grid = sns.clustermap(matrix, figsize=panel.figsize, xticklabels=True, yticklabels=True)
    place_clustermap(grid, panel, "heatmap", row_dendrogram_mm=6, col_dendrogram_mm=5, cbar=None)
    box_ax = panel.axes(grid.figure, "box")
    sns.boxplot(data=values, ax=box_ax)
panel.save(grid.figure)
```

Dendrograms and colour strips are placed left of and above the heatmap rectangle; leave room for them
in the layout.

## Recipe 3: stacked tracks with different heights

The layout grid accepts ratios.

```yaml
C:
  axes:
    tracks: {box: [12, 64, 75, 48], height_ratios: [1, 1, 3], hgap: 1.5}
```

```python
fig = panel.figure()
top, middle, bottom = panel.axes(fig, "tracks")[:, 0]
```

## Recipe 4: a gridspec with spans

For arrangements a regular grid cannot express, create a matplotlib GridSpec inside a layout region;
gaps are in mm.

```python
fig = panel.figure()
gs = panel.gridspec(fig, "region", 2, 2, wgap=8, hgap=6, width_ratios=[2, 1])
big = fig.add_subplot(gs[:, 0])  # spans both rows
small_top = fig.add_subplot(gs[0, 1])
small_bottom = fig.add_subplot(gs[1, 1])
```

`gs[i, j].subgridspec(...)` nests further.
Axes made this way are not position-checked; keep the figure's layout engine off (the `panel.figure()`
default).

## Overlapping panel boxes

Panel boxes may overlap: in many published figures a panel's labels reach into the space of its
neighbour.
`plotplate check` reports the overlap as a warning, because it is usually unintended, and because
panels are opaque by default: the panel drawn later paints over the earlier one.

Two ways to handle it:

- **Separate the boxes** (the usual fix): move an edge in `plotplate view`, or let `optimize` give
  every panel its own space.
- **Keep the overlap and make panels transparent**: set `style.export.transparent: true`, so only the
  drawn content covers the neighbour.
  Check the preview: overlapping *content* is still a problem, only empty margins become harmless.

## Structure panel notebooks for later changes

Layouts change: panels move, merge, split.
A consistent structure keeps those changes mechanical:

- One drawing function per layout axes entry, taking the axes and the data:
  `draw_roc(ax, roc)`, `draw_prc(ax, pr)`.
- The notebook only loads data, creates the figure through the panel, calls the functions, and saves.
- For library figures (clustermap, Marsilea), one function creates and places the whole library
  figure.

Moving the PRC curve from panel A to its own panel B then means: one new axes entry in the layout, and
moving one function call to a new notebook.

## Complex compositions

Panels are free rectangles, so rows of different heights and panels spanning several rows or columns
are supported ([layout-spec.md](layout-spec.md#panels-spanning-rows-or-columns)).
Two published-figure arrangements were rebuilt and read back:

| arrangement | `plotplate detect` (a PDF with placed panels) | `plotplate detect` (an image) |
| --- | --- | --- |
| 5 panels: a tall panel beside three stacked panels, one panel below it | all boxes exact, letters named every panel | overlap with the true box 0.96-0.98 |
| 10 panels: a tall panel beside a row of two, a wide panel below, two rows of three with different column boundaries | all boxes exact, letters named every panel | overlap with the true box 0.96-0.98 |

Image detection splits along white gutters, so it needs every panel to be separable by straight cuts
(which covers nearly all journal figures).
Interlocking arrangements where no straight gutter separates panels need a PDF with placed panels, or
boxes moved by hand in `plotplate view`.
