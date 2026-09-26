# Optimize: spend the white space

[← README](../README.md) · [layout sources](layout-sources.md) · [constraints](constraints.md) · [workflow](workflow.md)

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

A panel may change size by at most a factor you set:

```sh
plotplate optimize figures/figure_1 --gap 4 --max-stretch 1.2   # grow by 20 % at most (default)
plotplate optimize figures/figure_1 --max-stretch 1.0           # no distortion: only move panels
plotplate optimize figures/figure_1 --max-stretch 1.5 --max-shrink 1.1
```

`--max-stretch 1.2` means "1.2× at most"; `--max-shrink` is the other direction (the same factor by
default, so a figure can also be retargeted to a narrower column). `1.0` means "do not resize this
figure at all", which still normalises the gutters and moves the panels together.

The limit is the point where the tool stops and reports instead of guessing:

```text
note: the row at 0-72 mm still has 33 mm of width to spare: A, B hit the 1.20x limit;
      about --max-stretch 1.48 would fill it
```

That is a decision for you to take, not for the tool: growing a panel by half changes how the figure
reads. The same applies to a size that cannot be reached. A width you asked for explicitly is an
error (`the panels would have to grow 2.37x to fill 400 mm`); the figure's current width is only the
default, so it bends and says so (`the figure could not keep its width of 183 mm`).

## How it works

1. **Grow into the white space.** Each panel's sides move to the middle of the gutter towards the
   nearest panel facing it, or to the edge of the figure — then that growth is clamped to the
   distortion limit. This is the step that recovers a hole: a narrow panel next to a wide one, a
   ragged right edge, a short last row.
1. **Recover the grid.** Panel edges within `--tolerance` (1 mm) of each other become one shared
   boundary, which turns the panels into spans over a grid. A panel may span several columns or rows.
   A panel nested inside another is recorded as an inset and keeps its place inside its host.
1. **Re-spend the space.** Every gutter of that grid becomes exactly `--gap`, and the rest of the
   width (and height) goes to the panels: the boundaries are solved so they add up to the target
   size, each panel stays inside its limit, and each strip prefers one overall scale — which is what
   spreads the recovered space evenly instead of giving it all to one panel.

The solver is Cassowary (`kiwisolver`, already a matplotlib dependency), the same one the
[constraints](constraints.md) use. No objective function is minimised: "no wasted space" is stated as
a requirement (the boundaries must add up to the width), which is why the result is reproducible and
the failure messages are exact.

### Sizes

| flag | meaning |
| --- | --- |
| `--width 174` or `--width single` | fill that width exactly (a journal width name works) |
| `--height scale` (default) | let the height follow the width, so the figure keeps its proportions |
| `--height keep` | fill the current height too |
| `--height 168` | fill that height (how you bring a figure under a journal's maximum) |

### Axes move with their panel

The distance from a panel edge to its outermost axes edge is kept: that space holds tick labels, axis
titles and the panel letter, and none of them gets bigger because the panel did. Everything between
those edges is stretched, so the extra millimetres end up in the plotting areas. Shared axes edges are
then named as [guides](layout-spec.md) again; when a formerly shared edge no longer coincides — two
rows grew by different factors — the report says so, and `plotplate align` checks it after a rebuild.

## What it refuses

An arrangement that is not a grid:

```text
cannot optimize layout.detected.yaml: these panels overlap without being nested: B/D, E/F.
Their boxes do not form a grid, so there is no white space to redistribute: merge them into one
panel (`plotplate merge`), or fix the boxes first
```

A pinwheel, or a panel reaching into two rows, has no unambiguous grid to re-spend. Merging the
interlocking panels into one panel (one matplotlib figure, drawn by one script) is usually the honest
answer, since that is what they are.

## Where the result goes

By default next to the input, as the `optimized` [variant](workflow.md#several-layouts-for-one-figure):

```sh
plotplate optimize figures/figure_1/layout.detected.yaml   # -> layout.optimized.yaml
plotplate view figures/figure_1                            # compare them, overlaid
```

Nothing is overwritten, and `--dry-run` reports without writing at all. The optimized file has plain
numbers in it (like `plotplate resolve`): no mosaic, no constraints, since the whole point was to
compute the boxes.

**The panels must be redrawn for it.** A layout with different boxes needs panel files of that size,
so `plotplate view` shows `panel-size` errors until you run `plotplate build` against the layout you
decided to keep. That is the check doing its job: a panel drawn at the wrong size is exactly the
problem plotplate exists to prevent.

## Optimize or constraints?

Both compute boxes, from different starting points:

| | `plotplate optimize` | [`constraints:`](constraints.md) |
| --- | --- | --- |
| input | boxes that already exist | relations you write |
| keeps | the arrangement you had | the relations, whatever the size |
| use for | a draft read back from an old figure | a figure you maintain |

A good path is: read an old figure back, optimize it to see what the space allows, then write the
layout you will maintain — with constraints, so the next journal's width costs one edit.
