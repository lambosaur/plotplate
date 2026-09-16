# Hard layout case

A PDF with arrangements that are awkward to read back, for testing and for seeing what
`plotplate from-pdf` does with them:

- an inset placed over another panel,
- a pinwheel where no straight gutter separates the panels, and one panel label falls
  inside a neighbour's box,
- a panel whose content overflows towards its neighbour.

```sh
python make.py                                    # writes hard.pdf
plotplate from-pdf hard.pdf -o layout.yaml --axes --guides --wireframe wireframe.png
plotplate validate layout.yaml                    # reports the real overlaps
plotplate preview layout.yaml
```

`plotplate demo hard-layout --build` runs all of it.

The panel boxes genuinely overlap, because the boxes of the source figure do: panels are
opaque by default, so separate them (`plotplate tidy --fill-gap 4`) or set
`style.export.transparent: true` in the layout.
