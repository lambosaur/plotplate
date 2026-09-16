---
name: notebook-editing
description: How to choose between NotebookEdit and a generator script when editing a Jupyter notebook (.ipynb) in this project. Use before making any change to a notebook.
---

# Editing notebooks

No fixed tool is mandated. Pick based on the size of the change.

## `NotebookEdit`: small, targeted changes

Direct, per-cell replace/insert/delete on a live `.ipynb`. Requires a prior `Read` of
the notebook. Good fit for a change touching one or two cells. Closer to how a human
actually works with a notebook in an editor (cell by cell), rather than regenerating
the whole file.

## A generator script: large structural rewrites

A script that builds the notebook's JSON from scratch is a better fit when a change
touches many cells' shared logic at once (for example: a helper function threaded
through several cells, or a full reorder of cell structure).

If you write one:

- Save it under `.claude/scratch/`, not `scripts/`. `.claude/scratch/` is a
  Claude-only working area, not something a human is expected to run; `scripts/` is
  for actual user-facing scripts.
- Treat it as disposable, not a resume point. Re-running it fully overwrites the
  notebook, including any hand-edits made since via `NotebookEdit`. Check `git diff`
  after regenerating, before assuming it matches the notebook's current state.
- A short `README.md` next to it, noting what it was for and that it may be stale, is
  enough context for a later session.

## Either way

Verify after the edit: a syntax/structural sanity check, plus running whatever test
suite covers the notebook's logic, regardless of which editing tool was used to get
there.
