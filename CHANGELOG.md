# Changelog

Notable changes per release.
Versions follow [semantic versioning](https://semver.org); before 1.0 the layout file format may still
change, and when it does, `schema:` is bumped and the old form keeps loading.

## Unreleased

### Added

- `plotplate latex --panel-refs` / `plotplate bundle --panel-refs`, for a manuscript that references a
  single panel: the `.tex` then also lists the letters it stamped and defines
  `\plotplatePanelLabels{<figure label>}`, called after `\caption`, so that `\ref{fig:7a}` prints `7a`
  and links to the figure.
  Off by default — without it the file stays what it was: a picture box, one `\includegraphics` per
  panel, one letter each, and no other definition.
  An optional argument covers other naming conventions (`\plotplatePanelLabels[:panel-]{fig7}` gives
  `fig7:panel-a`), and `cleveref` keeps the letter (`\cref` prints "fig. 7a").
  Verified by compiling a document with two figures, `hyperref` and `cleveref`.
- `<name>-figure.tex`: the figure environment, the placement, the caption and the label, written once
  with a placeholder caption and never overwritten, so what is edited by hand survives every rebuild.
  It includes `<name>.tex`, which holds the panels and stays generated.
  The manuscript then needs one line per figure.
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
