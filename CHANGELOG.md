# Changelog

Notable changes per release.
Versions follow [semantic versioning](https://semver.org); before 1.0 the layout file format may still
change, and when it does, `schema:` is bumped and the old form keeps loading.

## 0.2.1 — 2026-10-05

### Fixed

- `<name>-figure.tex` included `panels/<name>.tex`, where no such file is written: the panels file
  sits next to the layout. The copy written beside the layout includes `<name>.tex`, the copy
  `plotplate bundle` writes keeps the path the manuscript needs, and a comment says the path is
  relative to whatever LaTeX compiles.
- `plotplate export` reported a missing or wrongly sized panel as a *warning* while refusing to write
  the file. It is an error, says so, and points at the new flag.

### Added

- `plotplate preview --page-outlines`: the panel boxes are drawn on the page view only, so the figure
  itself stays clean. `--outlines` is unchanged and applies to the figure.
- `plotplate export --allow-missing`: write a draft with empty boxes where panels are missing, for
  showing work in progress. Each hole is reported as a warning; the default still refuses.

## 0.2.0 — 2026-10-02

The LaTeX output, reworked after using it on a real manuscript: two files instead of one, and nothing
defined in either.

### Changed

- The generated `<name>.tex` defines nothing at all: the letters carry their font inline, where it
  used to be a `\providecommand`.
  The file is a picture box, one `\includegraphics` per panel and one `\makebox` per letter — nothing
  to know about before pasting it into a manuscript.
  The letters' appearance is set in the layout's `panel_label`, which also drives the preview and the
  export.

### Added

- `<name>-figure.tex`: the figure environment, the placement, the caption and the label — the parts
  that belong to the text.
  Written once with a placeholder caption and **never overwritten**, so what is edited by hand
  survives every rebuild.
  It includes `<name>.tex`, which holds the panels and stays generated, so the manuscript needs one
  line per figure.
  It also lists, commented out, one `\phantomsubcaption` line per panel: uncomment them and
  `\ref{fig:7a}` prints `7a`, `\subref` prints `a`.
  That is `subcaption` doing the one job `subfigure` was being used for — no plotplate macro, and no
  space taken, verified by compiling with and without the lines and finding the caption in the same
  place.
- `plotplate bundle` copies the composed figure as `<name>.pdf` beside the panels, and prints the line
  to paste into the manuscript.

### Fixed

- The LaTeX tests found no engine when run through the pixi environment, so they always skipped; they
  now look for `tectonic` beside the interpreter too.

## 0.1.0 — 2026-10-02

First tagged release: the whole path from an existing figure to a journal-ready one works, on the demo
and on real material.

### The model

- A figure is a **page** (the sheet) holding an **area** (the figure itself) of **panels** (one
  matplotlib `Figure`, one file) of **axes**.
  Everything is in millimetres from the area's top-left corner, and panels are assembled by LaTeX at
  scale 1.0, so a panel is printed at the size it was drawn ([coordinates.md](docs/coordinates.md)).
- `layout.yaml` places panels explicitly, from a `mosaic:` shorthand, or by solving `constraints:`
  with Cassowary ([layout-spec.md](docs/layout-spec.md), [constraints.md](docs/constraints.md)).
- Several layouts of one figure live side by side as `layout.<variant>.yaml`.

### Recovering a layout from an existing figure

- `plotplate from-pdf` reads the **placed graphics** of a PDF page: exact positions, no computer
  vision, with `--axes` and `--guides` to recover plotting areas and shared edges.
- `plotplate detect` falls back to a deterministic XY-cut for screenshots and flattened pages.
- `plotplate svg-import` / `svg-export` round-trip through Inkscape or Illustrator; panels are matched
  by label, then by the ids plotplate wrote, so every save format survives.
- `plotplate merge`, `tidy`, `relabel`, `diff` clean up and compare drafts; `diff` also writes a
  revision plan.

### Spending the space

- `plotplate optimize` recovers the grid behind the boxes, makes every gutter the same, and gives the
  rest back to the panels, within a distortion limit it picks itself
  ([optimize.md](docs/optimize.md)).
- Panels can be frozen, held to their aspect ratio, or given their own limit in the layout's
  `optimize:` section; `--json` and `--dry-run` make it usable by an agent.
- Page guides are hard stops: panels never grow across one, and a band between two of them stays open.

### Looking at it, and editing it

- `plotplate view` serves a local page: the figure on its sheet, panel boxes, axes, guides, alignment
  rules, measured geometry and every layout variant, each toggleable, re-read on every request.
- `plotplate view --edit` drags and resizes panels with magnets (neighbours, guides, and one gutter
  away from them), adds and moves page guides, locks panels, adds, renames and renumbers them, runs
  the optimizer on what is on screen, and saves the result as `layout.<name>.yaml` — never over the
  layout you maintain.
  Undo and redo throughout.

### Drawing and delivering

- `Panel` places axes in millimetres, fits seaborn and Marsilea figures into a box, and records
  measured geometry for alignment checks.
- `plotplate build` runs the panel scripts, previews, generates the LaTeX and checks the result;
  `plotplate align` reports misalignment in millimetres.
- `plotplate bundle` / `export` produce an Overleaf folder or a journal deliverable; presets for
  Nature, Science, Cell, PLOS, Genome Research, NAR and a generic A4, each citing its source.
- Panel letters are stamped at absolute millimetres, so they take no space, and one `panel_label`
  style drives LaTeX, the preview and the viewer alike.

### For agents

- Six skills ship inside the package (`plotplate skills --list|--paths|--json|--print`, or copied into
  a project with `--dest`).
- `plotplate doctor` reports the environments in play; `plotplate --version` the version.

### Fixed before the release

- The demo's `layout.yaml` and `alignment.yaml` were missing from built wheels (stale package-data
  patterns).
  `tests/test_packaging.py` now builds a wheel and fails if anything is left out.
- `plotplate tidy --width` did not scale axes written as edges, which broke `from-pdf --width`.
