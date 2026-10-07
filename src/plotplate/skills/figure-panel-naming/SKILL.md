---
name: figure-panel-naming
description: Name the parts of a figure panel (axes, legends, reference points) so they can be referred to in layouts, alignment rules and later revisions. Use when writing or reviewing panel code, or when plotplate reports unnamed axes.
---

# Naming the parts of a panel

A panel is one matplotlib figure that may hold many axes. Every later step refers to those parts
by name: alignment rules (`A.roc`), revisions, reviews. Names are cheap to add while writing the
code and expensive to recover afterwards, because nothing in a drawn figure says which axes was
the ROC curve.

`plotplate check <layout>` reports every anonymous axes (`unnamed-axes`) and every declared
alignment that did not come out (`align-drift`). Run it after a build; it is the mechanical check
behind this skill.

## Rules

1. **Name by content, not by position.**
   `roc`, `prc`, `heatmap`, `scaling`, `residuals`. Never `left`, `panel2`, `ax_a`: a revision
   moves panels, and a position-based name then lies.

1. **Prefer the layout.**
   An axes entry in `layout.yaml` both places and names it:

   ```yaml
   A:
     axes:
       roc: {left: left_axis, top: 5, right: 44, bottom: row1_bottom}
   ```

   `panel.axes(fig, "roc")` then returns an axes already called `roc`.

1. **Name axes created in code** (gridspec cells, insets, library extras) with one line:

   ```python
   inset = fig.add_axes(panel.rect(30, 8, 18, 12))
   inset.set_label("zoom")  # the name plotplate reports
   ```

   Grids from the layout are numbered from their entry (`scatter1` … `scatter4`), which is fine:
   the entry already says what they are.

1. **Name variables after the same thing.**
   `ax_roc = panel.axes(fig, "roc")` keeps code and layout searchable together.

1. **One drawing function per named part**, taking that axes and its data:
   `def draw_roc(ax, curves): ...`. A later split or merge then moves function calls, not code.

1. **Register what has no axes edge.**

   - A reference point in data coordinates: `panel.mark("zero", ax=ax_scaling, x=0, y=0)`.
   - Any artist's box: `panel.anchor("key", legend)`; legends and colorbars are recorded
     automatically as `<axes>.legend` and by their axes name.

1. **Keep names stable across revisions.**
   Renaming a part breaks the layout's axes entries, `alignment.yaml` and the panel files. If a rename is intended, update
   the rules in the same change, and say so in the revision plan.

## Reviewing existing panel code

1. `plotplate build <layout>`, which ends with `plotplate check`.
1. For every `ax1`, `ax2`… reported: find where that axes is created and give it a name, in the
   layout when it should also be placed there, otherwise with `set_label`.
1. For alignment work, check that the parts the user cares about appear in the listing; add
   `panel.mark` or `panel.anchor` for the ones that do not.
1. Do not rename existing parts to satisfy taste: a name in use is a contract with
   `alignment.yaml` and the panel files.
