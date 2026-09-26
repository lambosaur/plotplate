# Alignment across panels

[← README](../README.md) · [workflow](workflow.md) · [layout reference](layout-spec.md)

## Scope

This file describes how panels drawn by different notebooks end up visually aligned, and how that
alignment is checked with numbers instead of by eye.

## The problem

Each panel is a separate matplotlib figure, so nothing inside panel B can "see" panel A. What makes a
figure look deliberate, though, is shared lines across panels: one baseline under a row, one left
spine down a column.

Two mechanisms cover it, and they work in opposite directions:

| mechanism | direction | file | answers |
| --- | --- | --- | --- |
| **constraints** | input: they place panels | `layout.yaml` | "these two panels have equal widths, 4 mm apart" ([constraints.md](constraints.md)) |
| **guides** | input: they place things | `layout.yaml` | "put the bottom spine of these axes at y = 45 mm" |
| **alignment rules** | output: they measure what happened | `alignment.yaml` + `panels/<panel>.json` | "do these features actually coincide, and by how much do they differ?" |

Guides alone are enough when every aligned feature is an axes rectangle you placed.
Rules are needed when the feature is not a placed rectangle: a library figure's heatmap, a bar
baseline, a boxplot without spines.

## Guides: declaring shared lines

```yaml
guides:
  x: {left_axis: 11}      # left spine of A/roc, C/scatter, D/main
  y: {row1_bottom: 45}    # bottom spine of A/roc, A/prc and B heatmap
panels:
  A:
    axes:
      roc: {left: left_axis, top: 5, right: 44, bottom: row1_bottom}
```

A guide is a number in the layout, not a measurement of another panel, so:

- panels can be written in any order, and each one on its own;
- panel B's heatmap can sit on `row1_bottom` before panel A exists;
- when a guide moves, `plotplate build` reruns every panel that uses it.

`plotplate from-pdf --axes --guides` proposes guides from an existing figure, by finding edges that
several panels already share.

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
- `plotplate features layout.yaml` prints them all, so a reference for `alignment.yaml` can be copied
  rather than guessed.
- `spines` says which edges are actually drawn, so a check can report "this edge has no spine; the
  axes edge was used".
- Coordinates are page millimetres, comparable across panels.

Legends and colorbars are recorded automatically (`A.roc.legend`), and any other artist can be
registered with `panel.anchor("key", artist)`.

For features that are not an axes edge, register a point in the panel code:

```python
panel.mark("zero", ax=ax, x=0, y=0)  # data coordinates of that axes
panel.anchor("key", legend)  # the box of any artist
panel.page_point(ax, x=0, y=0)  # the same conversion, returned to you
```

## Alignment rules: checking the result

`alignment.yaml`, next to the layout:

```yaml
tolerance: 0.2            # mm, default for every rule
rules:
  - match: left           # left | right | top | bottom | mark
    of: [A.roc, C.scatter1, D.main]
  - match: bottom
    of: [A.roc, A.prc, B.heatmap]
    tolerance: 0.1
  - match: mark
    of: [D.zero, E.zero]
```

```sh
plotplate features layout.yaml               # every feature you can refer to, with its coordinates
plotplate align layout.yaml                  # uses alignment.yaml if present
plotplate align layout.yaml --near 1.0       # without rules: what is nearly aligned
plotplate preview layout.yaml --rules        # draws the rule lines across the page
```

- A broken rule is an error, with every value and the deviation in millimetres:
  `left of 3 features differs by 0.75 mm (tolerance 0.2): A.roc 11.00, C.scatter1 11.00, D.main 11.75`.
- `--near` lists features of different panels that are close but not equal.
  Those are the ones that look like mistakes in print; exact matches are not reported.
- `plotplate align` exits non-zero when a rule is broken, so it can gate a build.

## Working loop

1. Declare the obvious alignments as guides in the layout.
1. Draw the panels; each one records its geometry.
1. `plotplate align` (rules) or `plotplate align --near` (discovery) to see the numbers.
1. Fix in the layout, not in panel code: move the guide or the axes rectangle, then `plotplate build`.
1. `plotplate preview --rules` to look at the result with the lines drawn.

An agent can run the same loop: the numbers come from the JSON files, so no visual estimation is
involved.
