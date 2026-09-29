# Design notes

[← README](../README.md) · [layout reference](layout-spec.md) · [workflow](workflow.md)

## Scope

This file records why the package works the way it does, what it does not do yet, and the open
questions.

## Problem

Panels were exported from analysis notebooks at sizes chosen for on-screen readability.
Assembling them in LaTeX meant rescaling or cropping each one.
Rescaling changes font sizes panel by panel, so the figure looks heterogeneous.
Fixing that by hand in Inkscape is slow and does not survive a data update.

## Decisions

| decision | reason |
| --- | --- |
| One `layout.yaml` per figure is the source of truth. | Python, preview, SVG and LaTeX cannot drift apart. |
| A panel is one matplotlib figure, not one axes. | Composite plots (clustermap, jointplot, ROC+PRC) stay single units. One notebook per panel stays simple. |
| Panels are saved at exactly their box size and included at scale 1.0. | Font sizes and line widths are then true print sizes, and checks on the figure are checks on the print. |
| Alignment across panels uses named guides and absolute axes rectangles. | It gives gridspec-like alignment across separately exported figures. |
| LaTeX draws panel letters. | Letters stay consistent and editable in the manuscript, and panel files stay reusable. |
| `plotplate export` also writes one composite file per figure. | Cell, BMC, PLOS and Science want all panels in one file for production (see [journal-specs.md](journal-specs.md)). |
| Checks measure text at the export resolution. | At screen resolution, font hinting shortens small text by up to ~10 %, which hid a clipped label. |
| The preview composes the panel PDFs with the same placement as LaTeX. | You can check the figure locally without Overleaf. A test compiles the snippet with Tectonic (XeTeX) and compares pixels. |
| PDF import reads placed graphics from the page's drawing instructions. | Positions are exact, letters name panels, and the placement scale explains uneven legacy figures. No model is needed. |
| Screenshot import uses a deterministic XY-cut, not model vision. | An agent only names and merges segments, and tools compute all coordinates. The wireframe overlay verifies the result. |
| `plotplate` is a standalone tool (pipx/uv); outputs go next to the given layout. | Works in any repository without copying a skeleton; the installation holds no user files. |
| The demo ships inside the package (`plotplate demo`). | Users of a tool installation can run it; the repository has one copy, and README images are generated from it. |
| One demo case, not several. | The walkthrough is the example; awkward arrangements (pinwheel, inset, overflow) are a regression fixture in `tests/fixtures/`, because they are something to handle, not something to copy. |
| Variants of a figure are files named `layout.<variant>.yaml` in the same folder. | A draft, its optimization and the maintained layout are the same figure: they share the panels, and a name is enough to keep them apart. No registry, no index file. |
| `plotplate optimize` recovers a grid and solves boundaries, instead of packing boxes freely. | A grid is what a reader sees in a multi-panel figure, and keeping it means the arrangement (and the alignment) survives. Free packing would need integer programming and would reorder panels, which is the author's decision, not the tool's. |
| The optimizer's limit is a distortion factor, and what the limit costs is reported. | How much a panel may grow changes how the figure reads, so the tool states the trade-off (`--max-stretch 1.48 would fill it`) rather than choosing it. |
| An explicitly requested size is an error when unreachable; the current size bends. | A number the user typed is a promise; the default is only a default. |
| All files are tracked on every branch (`main`, `dev`, features). | Git cannot keep per-branch file sets maintainably, and installations never include development files. |
| Undo keeps snapshots of the whole editing state, not a list of what each action did. | A page's worth of edits is a few numbers per panel, so a snapshot is cheap and can never drift from the state it is meant to restore; a drag records one, at the moment it starts. |
| A panel locked on the page is `optimize.panels.<name>.freeze`. | The page refuses to drag it and the optimizer refuses to resize it: one promise written once, rather than a viewer state that disappears when the tab closes. A locked panel stays selectable, or there would be no way back. |
| The page renames panels as one permutation, and writes them in reading order. | Renumbering moves several names at once (the new panel becomes `C` while `C` becomes `D`), which no sequence of single renames can do without colliding with itself. |
| A panel can be renamed on the page only until it has been drawn. | A panel's name is the name of its file and of the code that draws it. Until `panels/<name>.pdf` exists there is nothing to orphan; after that, renaming is a change to the figure's code, which `plotplate merge --as` and `plotplate diff` handle. |
| Page guides are hard stops for the optimizer, and a band between two of them is not a gutter. | Otherwise the only way to keep space empty would be to fight the optimizer after every run. The stop is stated on the grid's shared edges, so it holds back the panels beside the guide without forbidding a panel that already spans it. |
| Page guides are unnamed numbers, separate from `guides:`. | A guide an axes is placed against is a reference and needs a name; a line you arrange panels against is scaffolding, and naming it would suggest something depends on it. Deleting a page guide can never break a layout. |
| The page's *arrange* button answers with boxes and writes nothing. | The optimizer is the same code the command runs, so the button cannot drift from it; and its result arriving as an edit (not a file) keeps one rule in the editor: only *save* writes. |
| Boxes are brought back inside the figure before being optimized. | A box dragged over the edge is a mistake, not an arrangement. Optimized as it stands, it pulls the grid boundary out with it and squashes every other panel to make the total fit. |
| The viewer can move boxes (`--edit`), but only saves `layout.<name>.yaml`. | Nudging a box is the commonest edit there is, and a round trip through a drawing program costs more than the edit. Writing back the maintained `layout.yaml` would replace its comments, `mosaic:` and journal widths with numbers, so the page saves a variant and the author copies it over. |
| Inkscape SVG import only updates boxes. | Drawing tools are good for geometry. Style, guides and grid settings stay in YAML. |
| Text is kept as text (PDF Type 42, SVG `fonttype: none`). | Journals require editable, embedded fonts. |
| Journal presets record sources and a `verified` note. | Guidelines change, and several pages could not be fetched directly. |

## Alternatives considered

- **Bin packing / integer programming for the optimizer** (letting a panel move to another row, or
  swapping panels to fill a hole).
  It changes the meaning of the figure, needs a solver plotplate does not ship, and has no obvious
  objective: "fewer wasted millimetres" competes with "panel A must stay first".
  The grid model keeps the arrangement and reports what the limits left unused.
- **figurefirst** (layouts drawn in Inkscape, axes created from SVG rectangles).
  The closest existing idea.
  It targets a single matplotlib figure for the whole page, which conflicts with the
  one-panel-one-figure decision.
  It is also not actively maintained.
- **One matplotlib figure with subfigures for the whole page.**
  Seaborn figure-level functions (clustermap) cannot draw into a subfigure.
  One script per figure grows too large.
- **PGF backend, text typeset by XeLaTeX.**
  It gives an exact font match with the manuscript, but it is slower and more fragile.
  You chose system fonts (Arial) instead.
- **svgutils / patchworklib composition in Python as the final output.**
  You chose LaTeX assembly for the final figure.
  The preview covers the Python-side need.

## Revisions

Rearranging a figure touches the layout and the notebooks together, so the deterministic and the
judgement parts are separated:

| part | where |
| --- | --- |
| what changed between two layouts (moved, merged, split, added, removed), and which notebooks are affected | `plotplate diff`, which matches panels by key or by box overlap and writes a plan |
| stable identity across re-lettering | panel keys, with `labels: auto` assigning letters by reading order |
| deciding the new arrangement, moving drawing functions, keeping constraints | the `figure-layout-revision` and `figure-layout-refine` skills (agent, plan-first) |

Alignment across panels stays explicit: named guides, which a refinement proposes and the user
approves.
There is no automatic "make it look aligned" step, because which edges should align is a design
decision.

## Identity and alignment

- Three levels of name: the figure (layout file), the panel (key, with the letter as display) and the
  plotting area (axes name).
  A panel is always one matplotlib figure, so a seaborn clustermap (several axes) is one panel with
  named areas inside it.
- Alignment across panels only exists through page coordinates, because panels are separate figures:
  named guides are that mechanism.
- `plotplate from-pdf --axes --guides` recovers both levels from an existing figure: plotting areas
  from the rectangles matplotlib paints, guides from edges shared by several panels.

## Constraints and compound-figure separation (2026-09-25)

| decision | reason |
| --- | --- |
| Panel boxes can be solved from constraints (`kiwisolver`, Cassowary). | Relations survive edits that numbers do not: a journal switch keeps the gaps fixed and re-solves the widths, and near-misses cannot appear. kiwisolver ships with matplotlib, so it costs no dependency. |
| CVXPY was not adopted. | It buys objectives ("maximise panel area subject to..."), which no current feature needs, at the price of heavy solvers. Revisit only if layout becomes an optimisation rather than a set of relations. |
| Machine-learning compound-figure separation (SimCFS, EXSCLAIM!, SODA) was not adopted. | Those models split *published raster figures* for literature mining. Our inputs are the sources: PDFs carry exact placements, and gutter detection scores 0.96-0.98 IoU on realistic arrangements. Bundling torch and hunting for weights (SODA ships none) would buy accuracy only on figures that are raster-only *and* have touching panels. A `--detector` hook can accept boxes from such a model if that case ever matters. |

## Known limitations

- Guides do not round-trip through SVG.
  Import replaces guide references of edited axes with numbers.
- The screenshot detector needs a clean white background and gutters of at least `--min-gap` mm.
  Panels that touch each other come out as one segment.
- `place_clustermap` supports the default clustermap arrangement (dendrograms left and top).
- Text overlap is a bounding-box test, so rotated labels can produce false positives.
- `--axes` only works for vector panels; raster panels (PNG) keep no shapes to read.
- `plotplate build` runs panel scripts as plain Python, without a Jupyter kernel.
  Notebook-only display calls return `None` there.
- The NAR preset is not verified from journal text (see
  [journal-specs.md](journal-specs.md#nucleic-acids-research)).
- Genome Research gives no column widths, so its layouts need an explicit `page.width`.
- `plotplate from-pdf` records clipped `\includegraphics` (trim, clip) at their unclipped size.
- Illustrator and Inkscape PDF exports were not tested (no licence or package available here);
  [layout-sources.md](layout-sources.md) states the expected behaviour.
- The page's editing is panel boxes only: no axes, no guides, no undo beyond *revert*, and no editing
  of a layout the server did not read (it always saves a full variant).
- `plotplate diff` reports geometry and keys; it does not read notebook content, so an agent (or the
  user) decides how drawing code moves.
- Panel letters in the LaTeX output use the font commands of `panel_label.latex_font` (`\sffamily` by
  default, so the document's sans); set it to `\fontspec{Arial}` under XeLaTeX, or redefine
  `\plotplatePanelLabel`, to match `plotplate export` exactly.
- The letter is stamped with `\put`, not set with `subcaption`/`subfigure`: it takes no space, so the
  assembled figure is exactly the size the layout says.
  `subfigure` would add a line under each panel and shrink the panels to compensate.

## Integration with project-meta

Planned order, as agreed:

1. This package, proven on the synthetic demo (done), then on one real PARNET figure (start with
   `plotplate from-pdf` on the Overleaf PDF).
1. A Copier question in project-meta, for example
   `has_figures`, which generates `figures/style.yaml`, a `figures/_template/` folder (layout, one
   panel notebook, README), the pixi dependency, the skills, and a `build-figures` task.
1. The same template applied to `parnet--paper`.

Nothing in project-meta or PARNET has been changed so far.

## Open questions

- The name: `plotplate` / `plotplate` was a placeholder.
  Free on PyPI: figplate, panelfit, plotplate, figlay, figboard, platefig, figfit, mmfig.

- Should `plotplate` apply a revision plan mechanically (rename keys, rename `panels/*` files,
  scaffold new notebooks), leaving only content moves to the agent?

- Where should the package be hosted (GitHub organization, name) so that figures repositories can pin
  a tag?

- Should panel notebooks also be paired `.ipynb` files, as in the project-meta notebook convention, or
  stay `.py` only?

- Which real PARNET figure should be the pilot, and where is its screenshot?

- NAR: can you get the figure section of the NAR author instructions (logged-in browser), so the
  preset can be verified?

- Should `text-near-edge` (text within 0.5 mm of the panel edge) become a warning?
  It would catch labels that touch the neighbouring panel's gap.
