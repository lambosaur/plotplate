# Alignment across panels

[← README](../README.md) · [the layout file](layout.md) · [the Python API](python-api.md)

Each panel is a separate matplotlib figure, so nothing inside panel B can see panel A. What makes a
figure look deliberate, though, is shared lines across panels: one baseline under a row, one left
spine down a column.

## Declare it, and it is checked for you

A guide is a number in the layout.
Two axes declared on the same number are a promise:

```yaml
guides:
  x: {left_axis: 11}      # left spine of A/roc, C/scatter, D/main
  y: {row1_bottom: 45}    # bottom spine of A/roc, A/prc and B heatmap
panels:
  A: {axes: {roc: {left: left_axis, top: 5, right: 44, bottom: row1_bottom}}}
  C: {axes: {scatter: {left: left_axis, top: 64, right: 181, bottom: 94}}}
```

Because a guide is a number and not a measurement of another panel, panels can be drawn in any order
and each one on its own: panel B's heatmap can sit on `row1_bottom` before panel A exists.
When a guide moves, `plotplate build` reruns every panel that uses it.

`plotplate check` then verifies the promise against what the panels actually measured, and reports
`align-drift` with the millimetres when they disagree:

```text
[error] align-drift: bottom is declared at 45 mm for 3 axes, and came out 1.80 mm apart
        (tolerance 0.3): A.prc 45.00, A.roc 45.00, B.heatmap 46.80
```

Nothing has to be written down for this: the contract is the layout, and the measurement is in the
panel files.
It matters because matplotlib can still move a spine after the fact — a colorbar takes room, a long
tick label pushes the axes in — and a 1.8 mm step in a baseline is visible in print and invisible on
screen.

`plotplate detect` proposes guides from an existing figure, by finding edges that several panels
already share.

## What each panel reports

`panel.save` measures the figure and writes `geometry` into `panels/<panel>.json`:

```json
"geometry": {
  "axes": {
    "roc": {"box_edges": {"left": 11.0, "right": 44.0, "top": 5.0, "bottom": 45.0},
            "spines": ["left", "bottom"]}
  },
  "marks": {"zero": {"x": 12.0, "y": 43.18}}
}
```

- Every visible axes is included, also the ones a library created (a clustermap's `heatmap`,
  `row_dendrogram`, `cbar`).
- Names come from the layout (`roc`, `heatmap`), from `ax.set_label("name")` for axes made in code,
  and otherwise `ax1`, `ax2`… in reading order, which does not change between runs.
  `plotplate check` reports the anonymous ones, since a name is what a rule can refer to.
- `spines` says which edges are actually drawn, so a check can report "this edge has no spine; the
  axes edge was used".
- Coordinates are page millimetres, comparable across panels.

Legends and colorbars are recorded automatically (`A.roc.legend`), and anything else can be registered
from the panel code:

```python
panel.mark("zero", ax=ax, x=0, y=0)  # a data point, stored in page mm
panel.anchor("key", legend)  # the box of any artist
```

## `alignment.yaml`: for what no rectangle can say

Declared axes cover most of it.
A file is needed when the thing that must line up is not a rectangle you placed: a mark in data
coordinates, a legend edge, a library's own axes.
Put it next to the layout and `plotplate check` reads it:

```yaml
tolerance: 0.2            # mm, default for every rule
rules:
  - match: mark           # left | right | top | bottom | mark
    of: [D.zero, E.zero]
  - match: bottom
    of: [A.roc, B.heatmap.legend]
    tolerance: 0.1
```

A broken rule is an error, with every value and the deviation in millimetres, and `plotplate check`
exits non-zero, so it can gate a build.

## Working loop

1. Declare the obvious alignments as guides in the layout.
1. Draw the panels; each one records its geometry.
1. `plotplate check` gives the numbers.
1. Fix in the layout, not in the panel code: move the guide or the axes rectangle, then
   `plotplate build`.
   Moving an axes in code breaks the alignment with every other panel on that line, and the check says
   so (`axes-moved`).

An agent can run the same loop: the numbers come from the JSON files, so nothing is estimated by eye.
