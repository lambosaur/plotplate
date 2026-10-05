---
name: figure-layout-revision
description: Rearrange an existing figure - move, resize, merge, split, add or remove panels - and carry the change into the panel notebooks. Use when asked to change the layout of a figure that already has panels, or to apply a new layout coming from a PDF or a drawing.
---

# Revising a figure layout

A revision changes two things that must stay consistent: `layout.yaml` and the notebooks that draw the
panels.
Work in a plan-first loop: propose, show, agree, then edit.

## 1. Understand the request

Inputs can be a sentence ("make the heatmap wider and put the scaling curve next to it"), a new PDF or
drawing of the intended arrangement, or both.
Read the current `layout.yaml` and run `plotplate validate` and `plotplate wireframe` to see what
exists.
With a new PDF or SVG, build the target layout first (`plotplate from-pdf`, `plotplate svg-import`;
see the `figure-layout-from-existing` skill), into `new.yaml`.

## 2. Propose the change (do not edit notebooks yet)

1. Write the target layout to a separate file (`new.yaml`), never over the current one.

1. `plotplate diff layout.yaml new.yaml -o revision.yaml --wireframe revision.png`

1. Read `revision.png` with the Read tool, and report to the user:

   - the change list (moved, merged, split, added, removed, relabelled), each with the notebooks it
     affects,
   - what it implies for content: a split needs its plots divided between two notebooks; a merge puts
     them in one; a removal orphans a notebook,
   - anything the layout cannot express yet (for example alignment guides you intend to add).

1. Ask for confirmation, and iterate on `new.yaml` until the user agrees.
   `plotplate diff` matches panels by key, or by box overlap when keys differ, so a panel that keeps
   its place under a new key is reported as renamed, and one old box overlapping two new ones as a
   split.
   When it guesses wrong (a panel replaced by unrelated content at the same place, for example), write
   the mapping explicitly and pass `--mapping map.yaml`:

   ```yaml
   mapping:
     A: [curves]           # renamed
     C: [scatter_left, scatter_right]   # split
     D: [perf]
   ```

## 3. Apply

1. Replace `layout.yaml` with the agreed `new.yaml` (keep the old one until the build passes).
1. Panel keys are identities, letters are display: with `labels: auto` the letters follow reading
   order, so inserting a panel does not rename anything.
   Use `plotplate relabel` to freeze letters explicitly.
1. Update the notebooks, following the plan:
   - **moved/resized**: usually nothing to change; rerun and read the checks.
   - **merged**: one notebook draws both sets of axes; move the drawing functions, keep one
     `panel.save`.
   - **split**: copy the notebook, keep the relevant drawing functions in each, point each at its
     panel key.
   - **added**: new notebook `panel_<key>_<topic>.py` from the same structure.
   - **removed**: delete the notebook and the stale files in `panels/`.
   - rename notebooks and `panels/<key>.*` files when a key changes.
1. `plotplate build layout.yaml` and fix what the checks report (see the `figure-panel-fitting`
   skill).
1. Read `figure.png`; compare with the intention; report the result and any remaining warnings.

## Rules

- Never change a layout and a notebook's content in the same step without showing the plan first.
- Never move axes in code to compensate for a layout change (`ax.set_position`): change the rectangle
  in the layout.
- Keep alignment: when panels in a row share an edge, express it with a named guide instead of
  repeating numbers.
- Keep the old layout file until `plotplate check` passes, so the change can be reverted.
