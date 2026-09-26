---
name: figure-layout-from-existing
description: Turn an existing assembled figure (PDF page, screenshot, Inkscape or Illustrator drawing) into a plotplate layout.yaml. Use when asked to create or recover a figure layout from a PDF, an image or an SVG.
---

# Layout from an existing figure

Goal: a `layout.yaml` whose panel boxes match the figure, obtained from deterministic tools.
Never estimate millimetre coordinates by eye from an image; the tools measure them.
`docs/layout-sources.md` in the plotplate repository explains every source in detail.

## Inputs to get from the user first

- The source: a PDF (best), an image cropped to the figure, or an SVG drawing.
- The target journal and column width (`plotplate journals` lists presets), or the width in mm.
- For a PDF: the page number.
- Which regions form one panel, if panel letters are missing or outlined.

## From a PDF (preferred)

1. `plotplate from-pdf page.pdf --page N -o fig/layout.detected.yaml --journal <preset> --width <name|mm> --paper a4 --axes --guides --wireframe fig/check.png`
   Write the draft as `layout.detected.yaml`, not `layout.yaml`: the drafts of a figure live next to
   each other as `layout.<variant>.yaml`, and `plotplate view fig/` shows them together.
1. Read the command output:
   - `N panels from placed graphics`: exact positions; letters named the panels.
   - `gutter detection`: nothing was placed; boxes are approximate.
   - a coverage note: part of the figure is flattened; compare with the wireframe, and consider
     `--detect`.
   - scale and dpi lines: report panels printed below 100 % scale or below 300 dpi to the user; they
     explain uneven fonts.
1. Read `fig/check.png` with the Read tool: every box must cover its plot and letter.
1. Rename or merge where needed: `plotplate merge fig/layout.detected.yaml S01 S02 --as A`.

## From a screenshot or a flattened PDF

1. `plotplate detect figure.png --width <mm> -o fig/layout.detected.yaml --wireframe fig/check.png`
   (or `plotplate from-pdf … --detect`).
1. Read the wireframe; map segments `S01, S02, …` to panels.
   Tuning: segments merged across a real gutter → lower `--min-gap`; tick-label rows cut off → raise
   `--attach`.
1. `plotplate merge fig/layout.detected.yaml S02 S03 --as A` for each panel (also to rename one).
1. `plotplate tidy fig/layout.detected.yaml --fill-gap 4 --tolerance 1.5`.

## From a drawing

`plotplate svg-import drawing.svg -o fig/layout.yaml`: rectangles in a layer named `panels`, named
after the panels (Inkscape label, or Illustrator layer-panel name exported as SVG id).
To let the user correct boxes: `plotplate svg-export fig/layout.yaml --background fig/check.png`, edit
in Inkscape, then `plotplate svg-import`.

## Spend the white space (optional, but usually worth it)

The boxes are where the old figure put them, so the gutters are uneven and space is wasted.

1. `plotplate optimize fig/layout.detected.yaml --gap 4` writes `fig/layout.optimized.yaml` and
   reports what it changed: the gutters, the share of the figure the panels cover, and each panel's
   factor.
1. Report the notes to the user rather than acting on them alone.
   `--max-stretch` is the user's call: a smaller limit distorts less, and a note says what it would
   buy.
1. It refuses an arrangement that is not a grid (interlocking panels).
   Merge those panels instead.

## Finish

1. Set `journal:`, `style_files:`, and the final `area.height` if it must change.
1. Copy the draft you decided on to `fig/layout.yaml`: that is the one every command uses by default.
1. `plotplate validate fig/layout.yaml` and `plotplate wireframe fig/layout.yaml`; read the wireframe.
1. Axes alignment is optional: add named `guides` and `axes` entries only when the user wants axes
   aligned across panels (`docs/layout-spec.md`).
