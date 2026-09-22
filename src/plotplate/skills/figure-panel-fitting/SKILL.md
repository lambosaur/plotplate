---
name: figure-panel-fitting
description: Write or adjust the plotting code of one figure panel so it fits its plotplate layout box with valid font sizes, no clipping and no overlaps. Use when creating or editing a panel_<X>_*.py notebook next to a layout.yaml.
---

# Fitting a panel into its layout box

A panel is one matplotlib figure whose size is fixed by `layout.yaml`.
The layout decides size and alignment; the notebook decides content.

## Rules

- Get the figure from the layout: `panel = plotplate.Layout.load("layout.yaml").panel("A")`, then
  `panel.figure()` / `panel.axes(fig, name)` / `panel.subplots()`.
  For seaborn figure-level plots pass `figsize=panel.figsize` and call `panel.fit(fig)` (clustermap:
  `place_clustermap`).
  For Marsilea boards use `fit_marsilea(build, panel, main=...)`; if it reports missing millimetres,
  reduce label padding or propose a layout change.
- Never pass another `figsize`, never `bbox_inches="tight"`, never `tight_layout()` on axes placed
  from the layout.
- Never hard-code font sizes in pt unless required; rely on the style (`font.size`, `small`, `large`).
  If a size must be set, use `layout.style["font"][...]`.
- Colors of shared entities come from `panel.colors` (project `style.yaml`), not literals.
- Save only with `panel.save(fig, source="<notebook file>")`.
  It writes `panels/<X>.{pdf,svg,png}` and `panels/<X>.json` with the check results.
- Data comes from precomputed tables in `data/`; keep computation out of panel notebooks except light
  reshaping.

Structure the notebook with one drawing function per layout axes entry (see `docs/panel-recipes.md`),
so later layout changes only move function calls.
For spans or nested grids inside a region, use
`panel.gridspec(fig, region, nrows, ncols, wgap=, hgap=)`.

## Loop

1. Run the notebook (or `plotplate build layout.yaml A` from the figure folder).
1. Read the report printed by `save` (also in `panels/A.json`).
1. Read `panels/A.png` with the Read tool to look at the result; `preview.png` to see it next to other
   panels.
1. Fix and repeat until the report has no errors, and warnings are either fixed or explained to the
   user.

## Fixes by issue code

| code | typical fix, in order of preference |
| --- | --- |
| `font-too-small` | remove the explicit small size; fewer/shorter labels (thin ticks with `MaxNLocator`, abbreviate); only then ask to enlarge the box |
| `font-too-large` | remove the explicit size; legend/title sizes follow the style automatically |
| `text-clipped` | shorten the label, move the legend inside/elsewhere, rotate tick labels; if the axes rectangle leaves no room, propose a layout change (margin) to the user |
| `text-overlap` | rotate or thin tick labels, reposition legend, abbreviate; for dense categorical labels consider fewer categories or a smaller style `small` size above the minimum |
| `font-size-spread` | bring sizes closer: use the style sizes (`size`, `small`, `large`) instead of explicit ones; the journal limit is in the preset |
| `line-too-thin` | raise explicit `linewidth` to at least the style `lines.min` |
| `axes-outside-panel` | move the layout rectangle inward, or reduce dendrogram/colour-strip/colorbar sizes |
| `axes-moved` | remove `set_position`/`tight_layout`/layout engine calls on layout-placed axes |
| `figure-size` | create the figure through the panel, or call `panel.fit(fig)` |

## Layout changes need the user

Changing `layout.yaml` (boxes, guides, axes rectangles) affects other panels and alignment.
Propose the change with its effect ("C's left axis would no longer align with A and D") and let the
user decide.
When a fix for one issue reintroduces another (e.g. rotating labels makes them clip), state the
tradeoff instead of silently choosing.
