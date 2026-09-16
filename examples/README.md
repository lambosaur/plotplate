# Examples

Sandboxes for trying plotplate and for debugging awkward inputs.
Everything these produce is generated, and git-ignored: only the scripts and this file are tracked.

| folder | what | how |
| --- | --- | --- |
| `demo/` | the full walkthrough that ships with the package (legacy PDF, layout, panels, export) | `pixi run -e dev demo`, or `plotplate demo examples/demo --build` |
| `hard-layout/` | a PDF with awkward arrangements: an inset over a panel, a pinwheel where no straight gutter separates panels, a panel overflowing towards its neighbour | `pixi run -e dev hard-case` |

The hard-layout case shows what `plotplate from-pdf` does with interlocking panels: it recovers every panel, and the panel boxes it reports genuinely overlap, because the boxes of the source figure do.
`plotplate validate` warns about the overlap, and refining the layout (moving edges, `plotplate tidy --fill-gap`) is what removes it.
