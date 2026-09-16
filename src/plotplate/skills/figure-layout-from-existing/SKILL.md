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

1. `plotplate from-pdf page.pdf --page N -o fig/layout.yaml --journal <preset> --width <name|mm> --fill-gap 4 --wireframe fig/check.png`
1. Read the command output:
   - `N panels from placed graphics`: exact positions; letters named the panels.
   - `gutter detection`: nothing was placed; boxes are approximate.
   - a coverage note: part of the figure is flattened; compare with the wireframe, and consider `--detect`.
   - scale and dpi lines: report panels printed below 100 % scale or below 300 dpi to the user; they explain uneven fonts.
1. Read `fig/check.png` with the Read tool: every box must cover its plot and letter.
1. Rename or merge where needed: `plotplate merge fig/layout.yaml S01 S02 --as A`.

## From a screenshot or a flattened PDF

1. `plotplate detect figure.png --width <mm> -o fig/layout.yaml --wireframe fig/check.png` (or `plotplate from-pdf … --detect`).
1. Read the wireframe; map segments `S01, S02, …` to panels.
   Tuning: segments merged across a real gutter → lower `--min-gap`; tick-label rows cut off → raise `--attach`.
1. `plotplate merge fig/layout.yaml S02 S03 --as A` for each panel (also to rename a single segment).
1. `plotplate tidy fig/layout.yaml --fill-gap 4 --tolerance 1.5`.

## From a drawing

`plotplate svg-import drawing.svg -o fig/layout.yaml`: rectangles in a layer named `panels`, named after the panels (Inkscape label, or Illustrator layer-panel name exported as SVG id).
To let the user correct boxes: `plotplate svg-export fig/layout.yaml --background fig/check.png`, edit in Inkscape, then `plotplate svg-import`.

## Finish

1. Set `journal:`, `style_files:`, and the final `page.height` if it must change.
1. `plotplate validate fig/layout.yaml` and `plotplate wireframe fig/layout.yaml`; read the wireframe.
1. Axes alignment is optional: add named `guides` and `axes` entries only when the user wants axes aligned across panels (`docs/layout-spec.md`).
