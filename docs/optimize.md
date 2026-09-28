# Optimize: spend the white space

[← README](../README.md) · [layout sources](layout-sources.md) · [constraints](constraints.md) ·
[workflow](workflow.md)

## Scope

`plotplate optimize` takes a layout whose panels are where they happened to land — read back from an
old figure, drafted from a screenshot, or typed by hand — and gives the white space between them back
to the panels, without changing the arrangement.

## What it optimizes

One thing: **the share of the figure the panels cover**, at a gutter you choose.
Every millimetre between panels is a millimetre not spent on data, so the objective is to have as
little of it as possible, inside the size the figure is allowed to have.

What it does **not** decide:

- the order of the panels, or which row they are in (that is the meaning of the figure),
- whether panel A *should* be wider than panel B (that is a judgement about content; you say so with
  `--freeze`, `--keep-aspect`, or by editing the layout),
- what is drawn inside a panel (the panel scripts do that, from the box the layout gives them).

## How far it may go: the distortion limit

A panel may change size by at most a factor.
By default **the optimizer picks that factor itself**: the smallest one that lets every row fill the
width, never more than 2.0.
One run, and the report says which factor it used.

```sh
plotplate optimize figures/figure_1                      # decides, and says what it decided
plotplate optimize figures/figure_1 --max-stretch 1.2    # never grow a panel by more than 20 %
plotplate optimize figures/figure_1 --max-stretch 1.0    # no distortion: only move panels
```

`--max-stretch 1.0` still normalises the gutters and pushes the panels together; the figure then
becomes narrower instead of the panels becoming bigger, and the report says so.
`--max-shrink` (1.2) is the other direction, which is what lets a figure be retargeted to a narrower
column.

When you set a factor that cannot work, the message carries the one that can:

```text
cannot optimize layout.detected.yaml: no arrangement fits with panels growing at most 1.05x
and 4 mm gutters. --max-stretch 1.10 works (or leave it out, and it is chosen for you);
a smaller --gap also helps
```

And when a limit you chose leaves space unused, the note names the row, not a range of millimetres:

```text
note: row 1 (a, b, 0-72 mm) is 33 mm narrower than the figure: its panels reached their
      1.20x limit, and raising the limit to 1.48 would fill it
```

## Limits for one panel, in the layout

A limit that belongs to a figure — this panel is a photograph, that one must not be touched — belongs
in the layout file, not in a command line you have to remember:

```yaml
optimize:
  gap: 4
  max_stretch: auto        # or a number; the command line overrides it
  panels:
    A: {stretch: 1.05}     # this one may only grow a little
    B: {freeze: true}      # ... and this one not at all
    D: {keep_aspect: true} # a photograph: keep its proportions
```

`plotplate optimize` reads that section every time, so the intent is versioned with the figure, is
visible in a diff, and is something an agent can edit.
The flags (`--gap`, `--max-stretch`, `--freeze`, `--keep-aspect`) override it for one run, for trying
something out.

## Page guides are hard stops

A [page guide](layout-spec.md#page-guides) is a line the optimizer will not move a panel across:

- a panel that ends beside a guide may grow up to it, and no further;
- two guides with nothing between them hold that band open — it is reserved space (a legend, a label
  column, air), not a gutter to be closed, so it keeps its width while everything else is re-spent;
- a panel that *already* spans a guide keeps spanning it: the stop applies to the shared edges, which
  is what holds back the panels beside the guide;
- a guide on the figure's own edge, or outside it — a margin of the sheet, or one left behind by a
  narrower `--width` — constrains nothing, because the figure's edges already do.

The report says which guides held (`guides-held`), and the space they keep open is not counted as a
row that could have been filled, so it never asks for a bigger `--max-stretch` to chase space that is
empty on purpose.

In `plotplate view --edit`, **arrange** uses the guides as they are on the page, before they are
saved: drag a guide, press arrange, see it hold.

## Notes

A note is the one thing the numbers do not say by themselves.
It is written as a sentence for whoever reads the terminal, and it also carries a code and the numbers
behind the sentence, so a script does not have to read English:

| code | what happened | numbers it carries |
| --- | --- | --- |
| `row-slack` | a row could not fill the width, because its panels reached their limit | `row`, `panels`, `top_mm`, `bottom_mm`, `spare_mm`, `stretch`, `fills_at` |
| `size-bent` | the figure had to become narrower or shorter to keep its panels | `axis`, `requested_mm`, `reason` |
| `guides-broken` | shared axes edges no longer line up after the change | `lost`, `before`, `after` |
| `guides-held` | page guides stopped the panels growing across them | `guides` (axis and position of each) |
| `insets-kept` | a nested panel rode along inside its host | `insets` |
| `nothing-gained` | the panels already used the space | — |

With the default automatic limit, a well-behaved figure produces no notes at all: `row-slack` only
appears when *you* set a limit that leaves space unused, and then `fills_at` is the limit that would
spend it.
The codes are part of the interface and do not change; the sentences may be reworded.

## For agents and scripts

`--json` prints the whole report — every panel's box before and after, its factor, the occupancy, the
gutters, the guides, and the notes as `{"code": …, "message": …, …}` records — instead of the table:

```sh
plotplate optimize figures/figure_1 --dry-run --json
```

`--dry-run` writes nothing, so an agent can propose a change, show the numbers, and only then write
it.
`--as NAME` writes `layout.NAME.yaml`, which is how several attempts end up side by side in the folder
for `plotplate view` to switch between:

```sh
plotplate optimize figures/figure_1 --max-stretch 1.1 --as careful
plotplate optimize figures/figure_1 --max-stretch 1.6 --as bold
```

## How it works

1. **Grow into the white space.**
   Each panel's sides move to the middle of the gutter towards the nearest panel facing it, or to the
   edge of the figure — then that growth is clamped to the distortion limit.
   This is the step that recovers a hole: a narrow panel next to a wide one, a ragged right edge, a
   short last row.
1. **Recover the grid.**
   Panel edges within `--tolerance` (1 mm) of each other become one shared boundary, which turns the
   panels into spans over a grid.
   A panel may span several columns or rows.
   A panel nested inside another is recorded as an inset and keeps its place inside its host.
1. **Re-spend the space.**
   Every gutter of that grid becomes exactly `--gap`, and the rest of the width (and height) goes to
   the panels: the boundaries are solved so they add up to the target size, each panel stays inside
   its limit, and each strip prefers one overall scale — which is what spreads the recovered space
   evenly instead of giving it all to one panel.

The solver is Cassowary (`kiwisolver`, already a matplotlib dependency), the same one the
[constraints](constraints.md) use.
No objective function is minimised: "no wasted space" is stated as a requirement (the boundaries must
add up to the width), which is why the result is reproducible and the failure messages are exact.

### Sizes

| flag | meaning |
| --- | --- |
| `--width 174` or `--width single` | fill that width exactly (a journal width name works) |
| `--height scale` (default) | let the height follow the width, so the figure keeps its proportions |
| `--height keep` | fill the current height too |
| `--height 168` | fill that height (how you bring a figure under a journal's maximum) |

### Axes move with their panel

The distance from a panel edge to its outermost axes edge is kept: that space holds tick labels, axis
titles and the panel letter, and none of them gets bigger because the panel did.
Everything between those edges is stretched, so the extra millimetres end up in the plotting areas.
Shared axes edges are then named as [guides](layout-spec.md) again; when a formerly shared edge no
longer coincides — two rows grew by different factors — the report says so, and `plotplate align`
checks it after a rebuild.

## What it refuses

An arrangement that is not a grid:

```text
cannot optimize layout.detected.yaml: these panels overlap without being nested: B/D, E/F.
Their boxes do not form a grid, so there is no white space to redistribute: merge them into one
panel (`plotplate merge`), or fix the boxes first
```

A pinwheel, or a panel reaching into two rows, has no unambiguous grid to re-spend.
Merging the interlocking panels into one panel (one matplotlib figure, drawn by one script) is usually
the honest answer, since that is what they are.

## Where the result goes

By default next to the input, as the `optimized`
[variant](workflow.md#several-layouts-for-one-figure):

```sh
plotplate optimize figures/figure_1/layout.detected.yaml   # -> layout.optimized.yaml
plotplate view figures/figure_1                            # compare them, overlaid
```

Nothing is overwritten, and `--dry-run` reports without writing at all.
The optimized file has plain numbers in it (like `plotplate resolve`): no mosaic, no constraints,
since the whole point was to compute the boxes.

**The panels must be redrawn for it.**
A layout with different boxes needs panel files of that size, so `plotplate view` shows `panel-size`
errors until you run `plotplate build` against the layout you decided to keep.
That is the check doing its job: a panel drawn at the wrong size is exactly the problem plotplate
exists to prevent.

## Optimize or constraints?

Both compute boxes, from different starting points:

| | `plotplate optimize` | [`constraints:`](constraints.md) |
| --- | --- | --- |
| input | boxes that already exist | relations you write |
| keeps | the arrangement you had | the relations, whatever the size |
| use for | a draft read back from an old figure | a figure you maintain |

A good path is: read an old figure back, optimize it to see what the space allows, then write the
layout you will maintain — with constraints, so the next journal's width costs one edit.
