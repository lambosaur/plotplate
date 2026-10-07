# Layout sources

[← README](../README.md) · [the layout file](layout.md) · [the layout file](layout.md)

## Scope

This file explains what `plotplate` can read to create a layout, and what the input must contain for
good results.
It covers PDF pages, screenshots, and drawings from Inkscape or Illustrator.

## Summary

| source | command | precision | panel names | requires |
| --- | --- | --- | --- | --- |
| PDF with placed panels | `plotplate detect` | exact | from letters, when they are live text | panels placed as files, not flattened |
| flattened PDF | `plotplate detect` | about 0.5 mm | `S01`, `S02`… | white gutters between panels |
| screenshot or image | `plotplate detect --width <mm>` | about 0.5 mm at 300 dpi | `S01`, `S02`… | image cropped to the figure, known width in mm |
| nothing yet | `plotplate new` | exact | yours | a mosaic string, e.g. `AB/CC` |

None of these commands uses a language model or a network service.

## PDF pages: `plotplate detect`

### How it works (no computer vision)

A PDF page is a list of drawing instructions.
`plotplate detect` runs through them, following the coordinate transformations, and records every
*placed* object (`Do` operators for image and form XObjects) with its box and scale.
Panel letters come from the text layer, not from image analysis.
Only the fallback (`--detect`, or a page with nothing placed) renders the page and analyses pixels.

### What the command reads

A PDF does not store "panels".
It stores drawing instructions.
When a file is **placed** (for example a panel PDF or PNG), the page draws it as one object with a
position and a scale.
`plotplate detect` follows these instructions and records the box of every placed object larger than
`--min-size` (5 mm).

For each object, it also reports:

- for vector objects, the scale at which the object was placed (`scale 26%` means its fonts print at
  26 % of their size),
- for raster images, the effective resolution in dpi.

These numbers show why an old figure looks uneven.

### What a panel box means, and what it is not

The box of a panel is **where a drawn thing is**, never where a letter is:

| source | the box is | what that implies |
| --- | --- | --- |
| a placed panel | the exact rectangle the placed file was drawn in | it includes the margins the panel file itself has, but none of the white space around it in the assembled figure |
| a detected gutter block | the ink bounding box of the block, found by cutting along white gutters | usually tighter than the real panel: the outer tick labels are in, the surrounding white space is not |

Nothing here measures "where the content is densest", and a letter never produces a box: letters group
and name the objects, and a panel's box is extended to include its own letter.
So a panel letter that was typed far from its plot names the right panel but does not move it.

Because the boxes come from the drawn objects, a drafted layout normally has uneven white space
between them — that is a property of the figure that was assembled, not an error in the reading.
`plotplate detect` changes that on purpose: it grows every box until it meets its neighbours 4 mm
away, and `plotplate optimize` does the same and then re-spends the recovered space within a
distortion limit ([optimize.md](optimize.md)).

### Panel names from letters

If the page contains panel letters as **live text** (single letters such as `A`, `b`, `(c)`), each
placed object is assigned to the nearest letter above or left of it.
Objects that share a letter become one panel, so two plots under `A` give one panel `A`.
Bold letters are preferred when present, because body text also contains single letters.
Letters converted to outlines are shapes, not text: panels are then named `S01`, `S02`…, and you
rename them with `plotplate merge layout.yaml S01 --as A`.

### Which programs produce placed objects

| program and action | placed objects in the PDF | tested |
| --- | --- | --- |
| LaTeX `\includegraphics` (Overleaf, any engine) | yes, PDF and raster files | yes |
| Illustrator, InDesign: *File > Place* of a raster image | yes | no (expected from the PDF format) |
| Illustrator: placed PDF/AI/EPS artwork, expanded or embedded | usually converted into paths | no |
| Inkscape: imported bitmap (linked or embedded) | yes | no (expected from the PDF format) |
| Inkscape: imported PDF or SVG | converted into paths | no |
| PowerPoint, Keynote export | images yes; charts usually paths | no |

When most of the content near the placed objects is not placed, `plotplate detect` prints a note
("placed graphics cover only N % of the drawn content").
Check the wireframe, and use `--detect` if boxes are missing.

### Plotting areas and shared edges

With `--axes`, the command also reads the plotting areas *inside* each vector panel: a matplotlib axes
paints its background as one rectangle, which survives in the PDF.
On the demo figure this recovered every axes rectangle exactly, including the four cells of a scatter
row; only a 1.8 mm colorbar was below the size threshold.
Raster panels (PNG, TIFF) contain no such shapes, and the command says so.

With `--guides` (default tolerance 0.5 mm), edges shared by axes of at least two panels become named
guides (`x1`, `y1`, …), and the axes entries reference them.
This is what keeps panels aligned through later edits.
On the demo figure it found the same six shared edges the layout declares by hand, including the
baseline shared by panel a's curves and panel b's heatmap.
Rename the guides to something meaningful (`left_axis`, `row1_bottom`) while refining.

### Practical advice

- A manuscript page is fine: body text and the caption are ignored, because only placed objects count.
- Choose the page with `--page N`.
- `--journal nature --width double` rescales the draft to the journal width.
- The boxes are grown to own the white space around their content, and nearly-equal edges are made
  equal, before the draft is written: what you read is a few round numbers.
  `plotplate optimize` then re-spends the space within a distortion limit
  ([optimize.md](optimize.md)).
- The sheet is recorded in the draft, so `plotplate check` can check that the figure fits the text
  block and `plotplate view` can show it on the page.
  A manuscript page tells plotplate its own paper size; a figure-only PDF is assumed to be A4.
- `\includegraphics[trim=…, clip]` records the full, unclipped object: the box can be slightly larger
  than the visible part.
- Always look at `layout.detected.wireframe.png`, which is drawn without being asked for: the boxes
  over the figure they came from.
- Insets are absorbed into the panel they sit on (their letter groups them), which is usually right:
  an inset is part of its panel.
- Interlocking arrangements work, including a panel label that falls inside a neighbouring panel's
  box.

## Flattened PDFs and screenshots: `plotplate detect`

When nothing was placed (shapes only, or a scanned page), `plotplate detect` renders the page itself;
the same command works on a PNG or JPEG.
Both split the image along white gutters.

The image must have a white background and visible gaps between panels.
A composed panel (two plots side by side) comes out as two segments: merge them with
`plotplate merge`.
Panel letters far from a plot are dropped.
For a screenshot, crop it to the figure and give the real figure width with `--width` (mm): an image
carries no physical size, so that number is what sets the scale.

## Choosing a source

1. If you have the PDF your old figure was compiled into, use `plotplate detect`.
1. If panels were flattened, or you only have an image, the same command detects the gutters; then
   merge the segments that belong to one panel.
1. If you are designing a new figure, start from `plotplate new` and move the boxes in
   `plotplate view`: exact numbers are easier to set than to detect.

After any source, refine the layout by hand: set the final height, and add guides where axes must line
up ([layout.md](layout.md)).
