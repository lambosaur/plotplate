# Examples

A sandbox for trying plotplate.
Everything in here is generated and git-ignored: only this file is tracked.

```sh
pixi run -e dev demo      # -> examples/figure-walkthrough/
```

That is the same thing a user gets from `plotplate demo figure --dir <folder> --build`, since the case
ships inside the package (`src/plotplate/demo/figure/`).
It builds one figure from a manuscript page: read the old figure back, optimize the space it wasted,
draw the panels of the maintained layout, export, and show where it sits on A4.

```sh
plotplate view examples/figure-walkthrough/figures/figure_1
```

The folder ends up with three layouts of the same figure — `layout.yaml` (maintained),
`layout.detected.yaml` (read back) and `layout.optimized.yaml` — which the viewer lets you switch
between and overlay.

Awkward arrangements (an inset over a panel, a pinwheel, overflowing content) used to live here as a
second case.
They are a regression fixture, not something to copy, so they now live in
`tests/fixtures/awkward_figure.py` and are exercised by the test suite.
To look at one:

```sh
pixi run -e dev python tests/fixtures/awkward_figure.py /tmp/awkward.pdf
plotplate from-pdf /tmp/awkward.pdf -o /tmp/awkward/layout.detected.yaml --axes --guides
plotplate view /tmp/awkward
```
