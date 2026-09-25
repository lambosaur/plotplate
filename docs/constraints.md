# Constraints: boxes computed, not typed

[← README](../README.md) · [layout reference](layout-spec.md) · [alignment](alignment.md)

## Scope

This file describes the optional `constraints` section of a layout: relations between panels (same
row, equal widths, 4 mm apart) from which the boxes are computed.
Layouts with explicit boxes or a `mosaic` keep working unchanged.

## Why

Typed numbers stop being true as soon as something changes.
Switch a figure from Nature (183 mm) to Cell (174 mm) and every box needs editing; the gaps drift, and
the near-misses `plotplate align --near` reports appear.
Relations survive those edits: state them once, and the boxes follow.

The solver is Cassowary, from `kiwisolver`, which matplotlib already installs, so this costs no new
dependency.

## Example

```yaml
page: {width: double, height: solve}   # solve: computed from the rules below
constraints:
  defaults: {gap: 4}
  rules:
    - row: {panels: [A, B], top: 0, height: 55, equal: true, fill: true}
    - row: {panels: [C], height: 42, fill: true}
    - row: {panels: [D, E], height: 45, equal: true, fill: true}
    - gap: {below: A, above: C}
    - gap: {below: C, above: D}
panels: {A: {}, B: {}, C: {}, D: {}, E: {}}
```

This gives the demo figure exactly: `A [0, 0, 89.5, 55]`, `B [93.5, 0, 89.5, 55]`,
`C [0, 59, 183, 42]`, and a page height of 150 mm (55 + 4 + 42 + 4 + 45).
Change `page.width` to 174 and the panels become 85 mm wide, with the gaps still 4 mm.

## Rules

Shorthands, which expand into the primitives below:

| rule | meaning |
| --- | --- |
| `row: {panels: […], gap, equal, fill, top, bottom, height, left, right, width}` | panels left to right, sharing top and bottom; `equal` gives them equal widths; `fill` spans the page; `top`/`bottom`/`height` apply to the row, `left`/`right` to its ends |
| `column: {panels: […], …}` | the transpose: top to bottom, sharing left and right |

Primitives:

| rule | meaning |
| --- | --- |
| `align: {edge: left\|right\|top\|bottom, of: [A, B, …]}` | those panels share that edge |
| `equal: {what: width\|height, of: [A, B, …]}` | same size in that direction |
| `gap: {after: A, before: B, value: 4}` | horizontal space between two panels |
| `gap: {below: A, above: C, value: 4}` | vertical space |
| `size: {panel: A, width: 60, height: 40}` | fixed size |
| `aspect: {panel: B, ratio: 1.6}` | width = ratio × height |
| `pin: {panel: A, left: 0, bottom: page}` | an edge at a number, or at the page edge |

Every rule takes `strength: required` (default), `strong`, `medium` or `weak`.
A preference bends when it conflicts with a required rule, which is how you say "prefer these equal,
but the page width wins".

`defaults: {gap: 4}` sets the gap used by rules that do not give one.

## Explicit boxes still work

A panel with a `box` is pinned, and the rules position the others around it.
That is the way to fix one panel (a photograph at its native aspect, say) and let the rest follow.

## Diagnostics

- **Conflicts** raise an error naming the constraint that could not be added.
- **Too few rules** are reported by `plotplate validate` as `under-constrained`, listing the panels
  that took the minimum size or the whole page.
- `plotplate resolve layout.yaml -o frozen.yaml` writes the solved boxes as plain numbers and drops
  the `constraints` section, when you want to stop solving and edit by hand.

## Relation to guides and alignment rules

Three mechanisms, at different levels:

| level | file | what it does |
| --- | --- | --- |
| panel boxes | `constraints` in `layout.yaml` | computes where panels sit |
| axes inside panels | `guides` in `layout.yaml` | shared coordinates for plotting areas across panels |
| verification | `alignment.yaml` | measures what the drawn panels actually did ([alignment.md](alignment.md)) |

Constraints do not replace the guides: they place panel boxes, while guides place the axes inside
them.
Both end up as numbers the panel code reads.
