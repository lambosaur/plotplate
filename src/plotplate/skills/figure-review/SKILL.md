---
name: figure-review
description: Review a complete multi-panel figure built with plotplate before sending it to Overleaf or a journal. Use when asked to check, review or finalize a figure folder.
---

# Reviewing a full figure

## Automated part

From the figure folder:

1. `plotplate build layout.yaml` (reruns every panel, then preview, LaTeX snippet and checks), or
   `plotplate check layout.yaml` when panels are current.
1. Report every error; list warnings with a proposed action each.
   `panel-older-than-layout` means the layout changed after that panel was saved: rerun it.

## Visual part

Read `figure.png` (identical placement to the LaTeX output) and check:

- Consistent encoding across panels: the same entity has the same color (`style.yaml` colors) and the
  same name everywhere.
- Same quantity, same axis label wording and units; shared axes ranges where panels are meant to be
  compared.
- Alignment that looks intended but is off by a little: suggest a shared guide in `layout.yaml`.
- Panel letters do not collide with content (top-left corner of each box is reserved for the letter).
- Empty space: a panel with much unused area suggests a layout change; mention it, do not change boxes
  unilaterally.
- Plotting conventions of the project (`.claude/skills/plotting-conventions` if present).

## Journal requirements

Read the `notes` of the layout's journal preset (`plotplate journals`, file in `presets/journals/`)
and its `verified` field.
If the preset says it is not fully verified, tell the user which values to confirm with the journal
guidelines.
Check page width against the journal column widths and height against `max_height`
(`plotplate validate` reports both).

## Production file

Most journals want one file per figure (`deliverable.composite` in the preset).
`plotplate export layout.yaml -o build/Figure1.pdf` (or `.tif` for PLOS) writes it; report any
`export-format` warning.
`docs/journal-specs.md` in the plotplate repository lists the requirements per journal.

## Hand-off

`plotplate bundle layout.yaml build/overleaf/<figure>` collects `<figure>.tex` and panel PDFs.
The user uploads the folder content to `figures/<figure>/` in Overleaf and uses
`\input{figures/<figure>/<figure>.tex}` inside a `figure` environment (requires `graphicx`).
