# The viewer

[← README](../README.md) · [the layout file](layout.md) · [optimize](optimize.md)

```sh
plotplate view figures/figure_1     # http://127.0.0.1:8765, Ctrl-C to stop
```

This is where a layout is edited.
The page shows the figure on the sheet it is meant for, with the layout drawn over it, and the boxes
can be moved.
Nothing is written until you ask for it.

## What the page shows

- the page, its text block and the space kept for the caption — A4 unless the layout's `page:` section
  says otherwise, and the view says when it had to assume one;
- panel boxes and letters, axes rectangles, guides, alignment rules and the measured geometry, each
  one toggleable, so you can also look at the layout with the figure hidden;
- every layout variant of the figure: one is active, the others can be overlaid as outlines;
- the panels with their boxes, and the current checks.

It re-reads the files on every request, so a `plotplate build` in another terminal appears within a
second, which makes it a good second screen while editing panel code.

It binds to 127.0.0.1 and uses only the Python standard library.

## Moving boxes

- drag a panel to move it, drag a corner to resize it; edges stick to the figure, to the guides, to
  the other panels **and to one gutter away from them**, so a panel lands at a real 4 mm gutter rather
  than flush against its neighbour.
  The reach is about five screen pixels, so it feels the same at any zoom, and holding **shift**
  ignores it;
- the arrow keys nudge the selected panel by 0.5 mm (2 mm with shift), and the four number fields set
  its box exactly;
- axes follow their panel the same way `plotplate optimize` moves them: the margins that hold tick
  labels keep their millimetres, and the plotting area takes the rest;
- **+ |** and **+ –** add a page guide, which you then drag anywhere on the sheet.
  `Delete` removes the selected one, and so does dragging it off the sheet.
  Panels stick to page guides, which is how two panels in different rows are put on the same line;
  they are saved with the layout ([layout.md](layout.md#page-guides)).
  A layout that declares none starts with four: the margins of the sheet;
- **locked** (in the edit box, or the checkbox beside each panel in the list) makes a panel refuse to
  be dragged, resized or nudged, and makes *arrange* keep its size.
  It can still be clicked — that is how it gets unlocked — and clicking it never grabs whatever sits
  under it.
  It is stored as `optimize: {panels: {A: {freeze: true}}}`, so the page's lock and the optimizer's
  promise are one thing;
- **+ panel** draws one more box, named after the next free letter: enough to sketch a whole figure
  before any of it is written.
  It counts as a panel straight away — *arrange* includes it, and saving writes it out;
- **renumber** hands out the letters in reading order (rows first, then left to right), which is what
  a panel inserted between two others needs.
  All the renames happen at once, so panels can swap letters; where the panel's *name* is its letter
  and nothing has been drawn yet, the names are renumbered too, and otherwise only the letters are.
  **letter** changes what the reader sees; **name** changes the panel's identity, which is also the
  name of `panels/A.pdf` and of the code that draws it.
  Renaming a panel that has already been drawn is refused, naming the files it would orphan — use
  `plotplate merge <layout> A --as S1` and rename the panel code, or change only the letter.
  Saved layouts are written in reading order, whatever order the panels were drawn in;
- **undo** and **redo** (`ctrl-Z`, `ctrl-shift-Z`) step through everything the page holds — boxes,
  guides, locks, letters, renames, added panels — and a whole drag counts as one step.
  The history goes back as far as the last save, and *revert* can itself be undone;
- **arrange** runs the optimizer on what is currently on the page: panels dragged off the figure are
  put back, gutters are evened out, and the white space goes back to the panels.
  Nothing is written — the result arrives as another edit, so it can be nudged further, reverted, or
  saved;
- **save** writes `layout.<name>.yaml` — a resolved layout, the same thing `optimize` writes.

`layout.yaml` is never written: its comments, its `mosaic:` and its journal widths do not survive
being written back as numbers, so what you drag is saved beside it and you copy it over when you are
happy with it.
Anything a drag cannot express — an annotation, a last cosmetic touch — belongs in the layout file, or
in a drawing program on `plotplate export <layout> -o touch-up.svg`, which links the panel SVGs so
each one stays editable.
