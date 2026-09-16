# Panel recipes

[← README](../README.md) · [workflow](workflow.md) · [layout reference](layout-spec.md)

## Scope

This file shows how to write panel code for common situations, what to avoid, and how complex compositions are handled.
Every recipe below was run as written; the results passed all checks.

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

1. **Panel without layout axes:** use `panel.subplots()` (constrained layout); labels are fitted automatically.
1. **Panel with layout axes:** the rectangle leaves too little room for the tick and axis labels.
   Enlarge the margin in `layout.yaml` (move the axes `left`, or the guide it uses), or shorten the labels.
   Moving the axes in code is not the fix: it breaks alignment with other panels, and the check reports it.
1. **Library figures (clustermap, Marsilea):** reduce label padding or dendrogram sizes, or give the main rectangle more room; `place_clustermap` and `fit_marsilea` report how many millimetres are missing.

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

Dendrograms and colour strips are placed left of and above the heatmap rectangle; leave room for them in the layout.

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

For arrangements a regular grid cannot express, create a matplotlib GridSpec inside a layout region; gaps are in mm.

```python
fig = panel.figure()
gs = panel.gridspec(fig, "region", 2, 2, wgap=8, hgap=6, width_ratios=[2, 1])
big = fig.add_subplot(gs[:, 0])  # spans both rows
small_top = fig.add_subplot(gs[0, 1])
small_bottom = fig.add_subplot(gs[1, 1])
```

`gs[i, j].subgridspec(...)` nests further.
Axes made this way are not position-checked; keep the figure's layout engine off (the `panel.figure()` default).

## Overlapping panel boxes

Panel boxes may overlap: in many published figures a panel's labels reach into the space of its neighbour.
`plotplate validate` reports the overlap as a warning, because it is usually unintended, and because panels are opaque by default: the panel drawn later paints over the earlier one.

Two ways to handle it:

- **Separate the boxes** (the usual fix): move an edge, or run `plotplate tidy --fill-gap 4` to give every panel its own space.
- **Keep the overlap and make panels transparent**: set `style.export.transparent: true`, so only the drawn content covers the neighbour.
  Check the preview: overlapping *content* is still a problem, only empty margins become harmless.

## Structure panel notebooks for later changes

Layouts change: panels move, merge, split.
A consistent structure keeps those changes mechanical:

- One drawing function per layout axes entry, taking the axes and the data: `draw_roc(ax, roc)`, `draw_prc(ax, pr)`.
- The notebook only loads data, creates the figure through the panel, calls the functions, and saves.
- For library figures (clustermap, Marsilea), one function creates and places the whole library figure.

Moving the PRC curve from panel A to its own panel B then means: one new axes entry in the layout, and moving one function call to a new notebook.

## Complex compositions

Panels are free rectangles, so rows of different heights and panels spanning several rows or columns are supported ([layout-spec.md](layout-spec.md#panels-spanning-rows-or-columns)).
Two published-figure arrangements were rebuilt and read back:

| arrangement | `plotplate from-pdf` (placed panels) | `plotplate detect` (image) |
| --- | --- | --- |
| 5 panels: a tall panel beside three stacked panels, one panel below it | all boxes exact, letters named every panel | overlap with the true box 0.96-0.98 |
| 10 panels: a tall panel beside a row of two, a wide panel below, two rows of three with different column boundaries | all boxes exact, letters named every panel | overlap with the true box 0.96-0.98 |

Image detection splits along white gutters, so it needs every panel to be separable by straight cuts (which covers nearly all journal figures).
Interlocking arrangements where no straight gutter separates panels need `plotplate from-pdf` or a drawing (`plotplate svg-import`).
