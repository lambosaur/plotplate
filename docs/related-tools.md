# Related tools

[← README](../README.md) · [design notes](design-notes.md) ·
[journal specifications](journal-specs.md)

## Scope

Every tool that was considered for this package, whether it was adopted or not, and why.
Some were read and run; others were only read about — the **looked at** column says which, so that a
verdict can be re-opened with the right amount of scepticism.

| looked at | means |
| --- | --- |
| run | installed and used on real data here |
| source | source code or paper read |
| page | project page, README or article read |

## Used here

| tool | what it solves | how it is used | looked at |
| --- | --- | --- | --- |
| [matplotlib](https://matplotlib.org) | drawing | every panel is one `Figure`, saved at its exact size | run |
| [kiwisolver](https://github.com/nucleic/kiwi) | Cassowary constraint solving (already a matplotlib dependency) | `constraints:` and the `optimize` grid solve | run |
| [PyMuPDF](https://pymupdf.readthedocs.io) | PDF reading and composition | `detect` placements, previews, page rendering | run |
| [Marsilea](https://marsilea.readthedocs.io/en/stable/) | composable annotated heatmaps | optional, for panel *content*, through `fit_marsilea` | run |
| seaborn figure-level plots | clustermap, jointplot, pairplot | optional, through `panel.fit` / `place_clustermap` | run |
| LaTeX `graphicx` + `picture` | final assembly | panels placed at millimetre positions, scale 1.0 | run |
| Inkscape / Illustrator | a last cosmetic touch | optional, on `plotplate export -o touch-up.svg` | run |

## Styling matplotlib for journals

All of these solve *style* (fonts, ticks, colours, sizes), which is one `style:` section here.
None of them size a panel to a millimetre box or assemble a figure, so none is a dependency; what they
encode is worth reading, and in one case worth copying.

| tool | what it is | verdict | looked at |
| --- | --- | --- | --- |
| [SciencePlots](https://github.com/garrettj403/SciencePlots) | the best-known set of `.mplstyle` sheets for papers | not a dependency; its colour cycles are bundled as palettes (see below). Its ~400 forks are mostly extra sheets and were not audited | source |
| [sciplotlib](https://github.com/Timothysit/sciplotlib) | style sheets (Nature Reviews, Economist…), helpers such as `set_bounds`, **and** a YAML/GUI multi-panel composer | the closest overlap of this list, on composition as well as style; its composer positions panels on a grid rather than sizing each panel to a box in millimetres, which is the thing this package exists to do. Not evaluated hands-on | page |
| [peerstyle](https://libraries.io/pypi/peerstyle) | journal style presets (IEEE, Nature), 300 dpi export, curved line labels | v0.1.3, one contributor, no adoption yet: too young to depend on. The curved-label idea is a panel-content trick, orthogonal to layout | page |
| [nature-plot-style](https://github.com/hoanglongcao/nature-plot-style) | a `set_nature_style()` function plus Nature-ish palettes | a single function, not a package to depend on; the same ground is covered by `presets/journals/nature.yaml`, which cites the official guide line by line | page |
| [proplot / ultraplot](https://proplot.readthedocs.io) | a matplotlib wrapper with its own layout engine | replaces matplotlib's API for panel content, and its layout works in inches inside one figure; conflicts with one-panel-one-file | page |

## Composing multi-panel figures

The alternatives to "one file per panel, assembled by LaTeX at scale 1.0".

| tool | what it is | verdict | looked at |
| --- | --- | --- | --- |
| matplotlib `subfigures` / one big `Figure` | the built-in way | seaborn's figure-level functions and Marsilea cannot draw into a `SubFigure`, and one script per figure grows unmanageable | run |
| [figurefirst](https://github.com/FlyRanch/figurefirst) | layouts drawn in Inkscape, axes created from SVG rectangles | the closest existing idea, and an influence; targets a single figure for the whole page, and is not actively maintained | source |
| [svgutils](https://github.com/btel/svg_utils) | compose SVG panels in Python | fine for an SVG-only pipeline; LaTeX assembly was chosen so the manuscript's own engine places the panels | page |
| [patchworklib](https://github.com/ponnhide/patchworklib) | `ggplot`-style composition of matplotlib axes with operators | composes by relative arrangement, not by a millimetre layout the journal fixed | page |
| [pylustrator](https://github.com/rgerum/pylustrator) | drag panels in a matplotlib window, writes the code back | same goal as `plotplate view`, inside one figure; the edits land in the plotting script rather than in a layout file | page |
| PGF backend (text typeset by LaTeX) | exact font match with the manuscript | slower and more fragile; system fonts (Arial) were chosen instead | page |
| `subcaption` / `subfigure` for panel letters | the usual LaTeX way | adds a line under each panel, so the figure grows and the panels shrink; letters are stamped with `\put` instead | run |

## Reading a layout back from an existing figure

This package reads **placed graphics** from a PDF (exact, no vision) and falls back to a deterministic
XY-cut on rasters.
The machine-learning alternatives all solve a neighbouring problem — splitting
*published raster figures* for literature mining — and were not adopted; a `--detector` hook can take
boxes from any of them if a raster-only figure with touching panels ever matters.

| tool | what it is | verdict | looked at |
| --- | --- | --- | --- |
| [SODA](https://github.com/source-data/soda_image_segmentation) (SourceData / EMBO) | object detection + a multimodal LLM to split compound figures and match captions | ships no weights, 4 commits, no adoption; the open issue is someone asking for weights, unanswered | source |
| [CompFigSep](https://github.com/GaetanLepage/compound-figure-separator) | Detectron-based panel segmentation, label recognition and caption splitting | a 2020 master's project (ExaMode), weights in the repository, unmaintained since | page |
| SimCFS ([2107.08650](https://arxiv.org/abs/2107.08650), [2208.14357](https://arxiv.org/abs/2208.14357)) | compound-figure separation trained on simulated figures to avoid bounding-box labels | the method of record for this task; would mean bundling torch to recover boxes that the source PDF already states exactly | source |
| EXSCLAIM! ([2103.10631](https://arxiv.org/abs/2103.10631)) | materials-science pipeline: extract, separate, caption-annotate | a literature-mining pipeline, not a layout tool; reports no separation accuracy | source |

## Getting the *data* back out of a plot

Different problem, deliberately out of scope: this package recovers **geometry** (where the panels and
axes are), never the numbers inside them.
If the numbers are what you need:

| tool | what it is |
| --- | --- |
| [WebPlotDigitizer](https://automeris.io) | calibrate the axes of a plot image, extract the series; the standard tool, used in the [nicologiso walkthrough](https://www.nicologiso.com/tech/extracting-data-from-pdf-tables-and-plots/) |
| [a matplotlib + numpy digitiser](https://www.pantelisliolios.com/digitize-scientific-plots-python/) | ~100 lines: click two reference lengths, then click along the curve |
| [Camelot](https://camelot-py.readthedocs.io) / Excalibur | tables out of PDFs (lattice and stream), into pandas |

## Guidance and specifications

| source | what it gives | how it is used |
| --- | --- | --- |
| [Nature's figure specifications](https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/) | the official widths, fonts, formats | quoted line by line in `presets/journals/nature.yaml`; see [journal-specs.md](journal-specs.md) |
| [Plotivy's 2025 Nature guide](https://plotivy.app/blog/nature-journal-figure-guidelines-2025) | a readable digest (89 / 120–136 / 183 mm, 5–7 pt text, 8 pt bold `a b c`, 300–600 dpi) | a useful cross-check of the preset, which it agrees with; a commercial product's blog, so the official page stays the source |
| [the `nature-figure` agent skill](https://skills.rest/skill/nature-figure) | instructions for an agent to plan and draw a figure with matplotlib or ggplot2 | the same shape as the skills shipped here (`plotplate skills`), but it writes plotting code; this package's skills drive deterministic tools instead |

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
Use one with `style.color_cycle: tol-bright` or `plotplate.palette("tol-bright")`; They are listed in
`src/plotplate/presets/palettes.yaml`.

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

`figures/figure_1/variants/panel_B_marsilea.py` in the demo (`plotplate demo figure`) draws panel b
this way.

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

## Where the decisions live

The tables above say what was considered.
[design-notes.md](design-notes.md) says what was decided and why, including the ones that are about
method rather than about a package: a grid solve instead of bin packing or integer programming,
deterministic detection instead of model vision, and LaTeX assembly instead of Python composition.
