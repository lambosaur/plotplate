# Examples

Sandboxes for trying plotplate and for debugging awkward inputs.
Everything these produce is generated, and git-ignored: only the scripts and this file are tracked.

Both cases ship inside the package, so a user can run them anywhere with
`plotplate demo <case> --dir <folder> --build`.

| folder | case | how |
| --- | --- | --- |
| `demo/` | `figure`: the full walkthrough (legacy PDF, layout, panels, export) | `pixi run -e dev demo` |
| `hard-layout/` | `hard-layout`: awkward arrangements (inset over a panel, pinwheel, overflow) | `pixi run -e dev hard-case` |

The hard-layout case shows what `plotplate from-pdf` does with interlocking panels: it recovers every
panel, and the panel boxes it reports genuinely overlap, because the boxes of the source figure do.
`plotplate validate` warns about the overlap, and refining the layout (moving edges,
`plotplate tidy --fill-gap`) is what removes it.
