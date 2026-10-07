---
name: figure-layout-from-existing
description: Turn an existing assembled figure (PDF page or screenshot) into a plotplate layout.yaml. Use when asked to create or recover a figure layout from a PDF or an image.
---

# Layout from an existing figure

Goal: a `layout.yaml` whose panel boxes match the figure, obtained from deterministic tools.
Never estimate millimetre coordinates by eye from an image; the tools measure them.
`docs/layout-sources.md` in the plotplate repository explains every source in detail.

## Inputs to get from the user first

- The source: a PDF (best), or an image cropped to the figure.
- The target journal and column width (`plotplate journals` lists presets), or the width in mm.
- For a PDF: the page number.
- Which regions form one panel, if panel letters are missing or outlined.

## Draft it

`plotplate detect <input>` reads both a PDF page and an image; the extension decides.

1. `plotplate detect page.pdf --page <N> -o fig/ --journal <preset> --width <name|mm>` `-o` takes the
   figure folder; the draft is always written as `layout.detected.yaml` there, never over
   `layout.yaml`.
   Add `--force` to replace an earlier draft.
   For an image, `--width` is required and must be a number of millimetres: it is the scale.
1. Read the command output:
   - `N panels from placed graphics`: exact positions; letters named the panels.
   - `gutter detection`: nothing was placed; boxes are approximate and named `S01, S02, …`.
   - a coverage note: part of the figure is flattened; compare with the wireframe.
   - scale and dpi lines: report panels printed below 100 % scale or below 300 dpi to the user; they
     explain uneven fonts.
   - geometry problems are printed but do not stop the draft: overlapping boxes are how the detector
     says "look here".
1. Read `fig/layout.detected.wireframe.png` with the Read tool -- it is drawn over the figure the
   boxes came from, without being asked for.
   Every box must cover its plot and its letter.
1. Rename or merge where needed: `plotplate merge fig/layout.detected.yaml S01 S02 --as A`.
   Edges that were nearly equal have already been made equal, and the boxes already own the white
   space around their content.

## Spend the white space (optional, but usually worth it)

The boxes are where the old figure put them, so the gutters are uneven and space is wasted.

1. `plotplate optimize fig/layout.detected.yaml` writes `fig/layout.optimized.yaml` and reports what
   it changed: the gutters, the share of the figure the panels cover, and each panel's factor.
1. Report the notes to the user rather than acting on them alone.
   How much distortion is allowed is the user's call, and it belongs in the layout:
   `optimize: {max_stretch: 1.2}`.
   A note says what a different limit would buy.
   With `--json`, each note is a record with a stable `code` (`row-slack`, `size-bent`,
   `guides-broken`, `insets-kept`, `nothing-gained`, `one-gutter`); `--dry-run` reports without
   writing, and `--as NAME` writes `layout.NAME.yaml` so two attempts can be compared in
   `plotplate view`.
1. It refuses an arrangement that is not a grid (interlocking panels).
   Merge those panels instead.

## Finish

1. Set `journal:`, `style_files:`, `gutter:` and the final `area.height` if it must change.
1. Copy the draft you decided on to `fig/layout.yaml`: that is the one every command uses by default.
   plotplate never writes that file itself, so the choice stays the user's.
1. `plotplate check fig/layout.yaml` and `plotplate wireframe fig/layout.yaml`; read the wireframe.
1. Offer `plotplate view fig/` so the user can move the boxes themselves.
1. Axes alignment is optional: add named `guides` and `axes` entries only when the user wants axes
   aligned across panels (`docs/layout.md`).
