# Related tools

[← README](../README.md) · [design notes](design-notes.md) ·
[journal specifications](journal-specs.md)

## Scope

This file compares existing tools with this package, and says how to combine them.
SciencePlots and Marsilea were evaluated hands-on on 2026-09-14 (source code read, Marsilea run on the
demo data).

## Summary

| tool | what it solves | overlap | verdict |
| --- | --- | --- | --- |
| [SciencePlots](https://github.com/garrettj403/SciencePlots) | matplotlib style sheets for papers | style only (fonts, ticks, colours) | do not depend on it; its colour cycles are bundled here as palettes |
| [Marsilea](https://marsilea.readthedocs.io/en/stable/) | composable annotated heatmaps and similar multi-axes plots | none; it draws panel content | good fit for complex heatmap panels, through `fit_marsilea` |
| seaborn figure-level plots | clustermap, jointplot, pairplot | none; panel content | supported through `panel.fit` and `place_clustermap` |

## SciencePlots

MIT licence, about 9,200 GitHub stars, active in 2026.

What it is: a set of `.mplstyle` files (`science`, `nature`, `ieee`, colour cycles, language fonts)
activated with `plt.style.use(...)`.

What it does not do: page layout, exact panel sizes, cross-panel alignment, or any check of the
result.

Conflicts with this package, from its style files:

- The base `science` style sets `savefig.bbox: tight`, which changes the saved size of every figure.
  Panels must keep exactly their box size.
- It sets `text.usetex: True`, which needs a LaTeX installation and typesets text in TeX fonts.
  Journals ask for editable Arial or Helvetica text.
- It turns minor ticks on and draws ticks on all four sides; Science's own guidelines ask for no minor
  ticks.
- Its `nature` style lists `DejaVu Sans` before Arial in `font.sans-serif`, so Arial is not used when
  both are installed.
- Its `nature` figure size is 3.3 in (84 mm); Nature's single column is 89 mm.

What is worth reusing: the colour-blind-safe colour cycles by Paul Tol.
They are bundled here (`tol-bright`, `tol-muted`, `tol-high-contrast`) together with the Wong palette
shown in Nature's guide.
Use one with `style.color_cycle: tol-bright` or `plotplate.palette("tol-bright")`;
`plotplate palettes` lists them.

## Marsilea

MIT licence, active in 2026, version 0.8.1 tested.

What it is: a declarative library for composable visualizations on top of matplotlib.
A main canvas (for example a `Heatmap`) gets side plots, labels, dendrograms, and legends attached on
its four sides.
It covers heatmaps, oncoprints, UpSet plots, sequence logos and single-cell style plots, which are
otherwise hard to build.

How it sizes figures: the main canvas has a width and height in inches, and each attached element adds
its measured size.
The figure size is the result of this sum, and its own `save()` uses `bbox_inches="tight"`.
This is the opposite of a fixed panel box, but the two are compatible: `render(figure=...)` draws into
a given figure, and `set_margin` controls the space around the content.

`fit_marsilea` bridges the two models:

1. It renders a first time to measure the space used around the main canvas.
1. It renders a second time with the main canvas and margins computed so the figure is exactly the
   panel box.
1. With `main=`, it also places the main canvas exactly on a layout rectangle, so a heatmap edge can
   align with other panels.
   When the surrounding labels and legends do not fit, it raises an error with the missing millimetres
   per side.

```python
import marsilea as ma
import marsilea.plotter as mp

from plotplate.marsilea_helpers import fit_marsilea


def build(width_in: float, height_in: float) -> ma.Heatmap:
    board = ma.Heatmap(matrix, width=width_in, height=height_in, cmap="RdBu_r", label="r")
    board.add_right(mp.Labels(row_names, fontsize=6, padding=0), pad=0.01)
    board.add_dendrogram("left", size=0.25)
    board.add_legends("right", pad=0.03)
    return board


board = fit_marsilea(build, panel, main="heatmap")
panel.save(board.figure)
```

`fig1/variants/panel_B_marsilea.py` in the demo (`plotplate demo <folder>`) draws panel b this way.

Findings from the evaluation:

- Marsilea measures label sizes in pixels at the figure resolution.
  At screen resolution (100 dpi) a 6 pt label measured about 8.4 mm long, against 9.0 mm in the
  printed PDF, so labels were clipped.
  `fit_marsilea` therefore lays out at the export resolution.
  The same effect had hidden a clipped label from this package's own checks, which now also measure at
  the export resolution.
- Pinning the heatmap to the demo layout needed two adjustments, both found by the tools: label
  padding set to 0, and the shared guide `row1_bottom` moved up by 1 mm.
- Marsilea sets its own font sizes for labels unless given `fontsize`; pass
  `layout.style["font"]["small"]` to stay consistent with the other panels.

## Other tools (not re-evaluated here)

See [design-notes.md](design-notes.md#alternatives-considered) for figurefirst, matplotlib subfigures,
the PGF backend, and svgutils/patchworklib, and why each was not adopted as the core mechanism.
