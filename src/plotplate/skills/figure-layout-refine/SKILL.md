---
name: figure-layout-refine
description: Turn a draft layout (from plotplate from-pdf, plotplate detect or a drawing) into a final layout - grouping, page size, alignment guides and axes rectangles. Use after creating a draft layout, before drawing panels.
---

# Refining a draft layout

The draft from `plotplate from-pdf` or `plotplate detect` contains panel boxes and, at best, letters.
It does not contain the decisions that make a figure look deliberate: which axes align with which, how much room labels need, what the final page size is.
The deterministic tools (`tidy`, `fill-gap`, `merge`, `--width`) fix geometry; this skill adds the judgement.

## Steps

1. **Check the grouping.**
   Read the wireframe over the source (`--wireframe`).
   Merge segments belonging to one panel (`plotplate merge draft.yaml S02 S03 --as A`), and rename panels to stable keys when the user wants ids rather than letters (`labels: auto` in the layout).

1. **Set the sheet and the figure size.**
   `journal:` and `area.width` (a journal width name), then `area.height` from the content, respecting the journal maximum (`plotplate validate` warns).
   `page:` describes the sheet (`paper`, `margins`, `caption`), and is what lets `plotplate validate` check that the figure fits the text block.
   Use `plotplate from-pdf --width` to rescale, and `plotplate optimize --gap 4` to regularize the gutters and give the recovered space to the panels (`docs/optimize.md`).

1. **Propose alignment guides.**
   Look at the source figure: panels in the same row usually share a baseline, and panels in a column share a left edge.
   Add named guides and reference them from axes entries:

   ```yaml
   guides:
     x: {left_axis: 11}        # left spine of A/roc, C/scatter, D/main
     y: {row1_bottom: 45}      # bottom spine of A/roc, A/prc and B heatmap
   ```

   Guides are the only mechanism that aligns axes *across* panels, because each panel is a separate figure.
   Do not add an axes rectangle for a panel that does not need alignment: without one, the panel uses constrained layout and fits its own labels.

1. **Reserve room for labels.**
   An axes rectangle excludes tick labels, axis labels and titles.
   Leave about 10-12 mm left of a y axis with tick labels, 8-10 mm below an x axis, and space at the top for a title or a panel letter.
   Too little room shows up as `text-clipped` when panels are drawn.

1. **Show the result.**
   `plotplate validate` and `plotplate wireframe`, read the wireframe, and present the refined layout to the user with the reasons for each guide.
   Iterate before any panel is drawn.

## Keep in mind

- Boxes are free rectangles: panels spanning rows or columns are fine.
- A composed panel (ROC + PRC, clustermap + boxplot) is one panel with several axes entries; name them by content (`roc`, `prc`, `heatmap`, `box`).
- Library figures (clustermap, Marsilea) need room around their main rectangle for dendrograms, colour strips and legends.
- Record why a guide exists in a YAML comment; the next revision depends on it.
