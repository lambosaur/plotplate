# Changelog

Notable changes per release.
Versions follow [semantic versioning](https://semver.org); before 1.0 the layout file format may still
change, and when it does, `schema:` is bumped and the old form keeps loading.

## 0.4.1 — 2026-10-07

### Changed

- **`page.png` is written at 300 dpi instead of 200**, and `page: {dpi: 600}` sets it to anything
  else.
  It is the rendering a build leaves to look at, so it has to survive being zoomed into: an A4 sheet
  is 2481 x 3508 pixels at 300 dpi, and 4961 x 7016 at 600, which costs 1.1 MB and under half a
  second.
  `page.pdf` beside it is vector and has no resolution at all — that is the file to open for a detail,
  or to print.

## 0.4.0 — 2026-10-07

Half the surface area. 28 commands become 16, ~90 flags become ~35, and what a figure *is* moves out
of the command line and into `layout.yaml`, where it is versioned with the figure.

The four commands you need, in the order you need them:

```sh
plotplate detect figure.pdf        # draft a layout from a figure that exists
plotplate optimize layout.yaml     # spend the white space between the panels
plotplate view figures/figure_1    # move the boxes by hand
plotplate build layout.yaml        # draw the panels, place them, check them
```

### Migration

| before | now |
| --- | --- |
| `from-pdf page.pdf` | `detect page.pdf` — one command for a PDF or an image, dispatching on the extension |
| `tidy draft.yaml --fill-gap 4` | nothing: `detect` fills the space and rounds the numbers itself |
| `preview layout.yaml` | `build layout.yaml` |
| `latex layout.yaml` | nothing: `build` writes the `.tex` files |
| `bundle <figure> <dest>` | `latex <figure> <dest>` — it *is* the LaTeX hand-off |
| `validate`, `align`, `features` | `check` — one report for geometry, panel files and alignment |
| `svg-export` / `svg-import` | `view` for editing a layout; `export -o touch-up.svg` for a last cosmetic pass |
| `relabel` | `panels.<key>.label: {text: A}` in the layout |
| `palettes` | `src/plotplate/presets/palettes.yaml` |
| `fonts --rebuild` | `doctor --rebuild-fonts` |
| `optimize --gap 4` | `gutter: 4` in the layout |
| `optimize --max-stretch 1.2 --freeze A` | `optimize: {max_stretch: 1.2, panels: {A: {freeze: true}}}` |
| `preview --page a4 --page-outlines` | `page: {paper: a4, outlines: true}` |
| `build --sources code/` | `code_dir: code` |
| `view --edit` | `view` — the viewer is the editor; it still writes nothing until you save |

### Changed

- **One gutter per figure.** `gutter: 4` (or `[horizontal, vertical]`) replaces `mosaic.gap` *and*
  `optimize.gap`, which were the same number in two places.
  Both are still read, and `check` says what to rename.
- **A build leaves one picture, not two.** `page.{pdf,png,svg}` — the figure at its real size on its
  sheet — is what a build writes and what you look at; `page.png` went from 100 to 200 dpi.
  `figure.{pdf,png,svg}` is gone: `plotplate export -o <file>` writes the cropped figure when one file
  is what you need, and it now also accepts `.svg`, which links the panel SVGs so Inkscape can open it
  with every panel still editable.
- **`code_dir:`** says where the panel scripts are, so a figure folder can keep its code in one place.
  Jupytext percent-format `.py` files run as they are.
- `detect` always draws its wireframe over the figure it read (`--background` is gone), always reads
  axes rectangles and shared edges, and always rounds the draft to a few numbers.
  A draft with overlapping boxes is still written: that is the detector pointing at something.
- `plotplate --help` lists the commands in four groups, by when you need them.

### Added

- **The layout file is checked against the keys that exist.**
  A key plotplate cannot read is refused by name, with the nearest legal one suggested
  (`gutters: unknown key; did you mean "gutter"?`).
  Before, a misspelled key was silently ignored and the feature simply did not work.
  `src/plotplate/schema.py` is the one table that lists every key, and every command reports a broken
  file in one line instead of a traceback.
- **`plotplate check --axes`** prints the axes the panels actually drew, in page millimetres, as
  `axes:` entries ready to paste into the layout — including the ones a library created and you never
  asked for.
  Promoting a freely drawn axes into a declared one is then copying rather than estimating; the names,
  and which edges should be shared, stay a decision.
- **Alignment is checked with no file to write.**
  Every axes edge the layout declares at the same coordinate is a promise, and `plotplate check`
  verifies it against what the panels measured (`align-drift`, in millimetres).
  `alignment.yaml` stays for what no rectangle can express — a mark in data coordinates, a legend
  edge, a library's own axes.

### Fixed

- **`plotplate latex` uploaded a placeholder caption.** `bundle` regenerated `<name>-figure.tex`
  instead of copying the one you edited, so the caption you wrote never reached Overleaf.
  It now copies your file and rewrites only the `\input{}` path.
- `snap` (the rounding inside `detect`) moved panel boxes without moving the guides and axes edges
  declared on them, which could push an axes outside its panel; everything moves together now, and the
  figure's own width and height move with it.

### Documentation

- `docs/workflow.md` is gone.
  It was 456 lines, about 200 of which repeated the README, it disagreed with it about which version
  to install, and two of its recipes exited 1.
  What was only in it now has a home: [docs/view.md](docs/view.md) is the viewer.
- [docs/layout.md](docs/layout.md) is the one reference for the file: the vocabulary and its picture,
  every key, guides, constraints — merged from `coordinates.md`, `layout-spec.md` and
  `constraints.md`.
- [docs/python-api.md](docs/python-api.md) is new, and answers what `panel.figure`, `panel.axes` and
  `panel.save` actually do.
  It leads with plain matplotlib, because declaring axes is for panels that must line up with each
  other, not for every panel.
- The README is 163 lines instead of 286, and says how to install once instead of twice.

## 0.3.0 — 2026-10-05

For figure folders that keep several layouts and build into one place.
Three breaking changes, all about *where* files go; nothing about how a figure is drawn.

### Changed

- **No command writes `layout.yaml`.** `resolve`, `tidy`, `merge` and `relabel` used to overwrite the
  layout they were given; they now write `layout.resolved.yaml`, `layout.tidied.yaml`,
  `layout.merged.yaml`, `layout.relabeled.yaml` — the pattern `optimize` already followed.
  `--as NAME` picks another name (`--variant NAME` for `merge`, whose `--as` names the merged panel),
  `--in-place` restores the old behaviour, and a command given its own output writes back to it, so
  `merge … && merge …` chains instead of losing the first merge.
- **A created layout is named after where it came from**: `detect` and `from-pdf` write
  `layout.detected.yaml`, `svg-import` `layout.svg.yaml`, `new` `layout.new.yaml`, in the folder you
  point at (`-o` may now be a folder, and is no longer required).
  An existing file is not replaced without `--force`, `--as` or `-o`.
- **The composed outputs are renamed**: `preview.{pdf,png,svg}` → `figure.{pdf,png,svg}` and
  `preview-page.{pdf,png}` → `page.{pdf,png,svg}`.
  `bundle` still reads `preview.pdf` when there is no `figure.pdf`, so a folder built by 0.2 still
  bundles.

### Added

- [docs/latex.md](docs/latex.md): everything about the manuscript side in one place — the two files,
  what is in them, referencing a panel, the SVG question — instead of a quarter of `workflow.md`.
  The README now opens with the whole tool on one screen, and its documentation index is a table of
  questions rather than a list of files.
- `plotplate bundle` without a destination fills `<output_dir>/overleaf/`, so the upload folder is
  under the same ignorable directory as the rest.
  A second argument still names another destination, which is what a promotion script uses.
- `output_dir:` in the layout: one folder for everything a build writes — `panels/`, the composed
  figure, the page view, the panels' `.tex`, the wireframe.
  The layout files and `<name>-figure.tex` stay beside the layout, because they are sources.
  Default unchanged (`.`).
- `preview: {page: a4, outlines: true}` in the layout: `plotplate build` writes the page view every
  time, and the outlines mark that view only — `figure.png` stays the figure itself.
- The page view is written as SVG too, with its text kept as text.
- `layout.yaml` may be a **symlink** to the layout in use.
  Commands follow it and write through it rather than over it, and a file that appears twice under two
  names (the link and its target) is listed once by `plotplate view`.

## 0.2.1 — 2026-10-05

### Fixed

- `<name>-figure.tex` included `panels/<name>.tex`, where no such file is written: the panels file
  sits next to the layout.
  The copy written beside the layout includes `<name>.tex`, the copy `plotplate bundle` writes keeps
  the path the manuscript needs, and a comment says the path is relative to whatever LaTeX compiles.
- `plotplate export` reported a missing or wrongly sized panel as a *warning* while refusing to write
  the file.
  It is an error, says so, and points at the new flag.

### Added

- `plotplate preview --page-outlines`: the panel boxes are drawn on the page view only, so the figure
  itself stays clean.
  `--outlines` is unchanged and applies to the figure.
- `plotplate export --allow-missing`: write a draft with empty boxes where panels are missing, for
  showing work in progress.
  Each hole is reported as a warning; the default still refuses.

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
