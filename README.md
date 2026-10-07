# plotplate

Build multi-panel figures from independent matplotlib panels that fit a layout exactly.

![From an existing figure to a layout to the final figure](docs/images/pipeline.png)

## Why

Panels exported from notebooks at "readable" sizes get rescaled or cropped when assembled in LaTeX,
Illustrator or Inkscape.
Each panel then prints with different font sizes and line widths.

This tool reverses the order:

1. You describe the figure once, in a `layout.yaml`: the sheet it is printed on, the figure's own
   size, panel boxes, alignment guides, journal rules.
1. Each panel is drawn by its own script, at exactly the size of its box.
1. The panels are assembled at scale 1.0, so every font prints at its true size, and the checks can
   prove it.

## The whole thing

Four commands, in the order you use them:

```sh
plotplate detect figure.pdf        # 1. draft a layout from a figure that exists
plotplate optimize layout.yaml     # 2. spend the white space between the panels
plotplate view figures/figure_1    # 3. move the boxes by hand, in a browser
plotplate build layout.yaml        # 4. draw the panels, place them, check them
```

Starting from nothing instead of from an existing figure?
`plotplate new fig/ --mosaic AB/CC --height 120` writes the first layout, and the rest is the same.

Everything a figure needs is in its `layout.yaml`, not in flags: how wide it is, how much white space
is left between panels, how far the optimizer may stretch a panel.
The commands take paths.

## Install

Two steps; the second is the one that matters.

**1. The `plotplate` command, once per user** — for layouts, wireframes, views and exports, in any
folder:

```sh
pixi global install --git https://github.com/lambosaur/plotplate.git plotplate
# or: pipx install "plotplate @ git+https://github.com/lambosaur/plotplate"
# or: uv tool install "plotplate @ git+https://github.com/lambosaur/plotplate"
```

**2. The library, where your panel scripts run** — they `import plotplate`, so it has to be there:

```sh
cd my-project
pixi add --pypi plotplate --git https://github.com/lambosaur/plotplate.git --tag v0.4.0
pixi run plotplate build figures/figure_1
```

`plotplate build` is the only command that runs your code, so run it through that environment, where
pandas and seaborn already live.
The two installations can disagree; the tools say so rather than letting it pass:

```sh
plotplate doctor                     # both versions, both paths, fonts, optional packages
plotplate doctor --rebuild-fonts     # after installing Arial (Debian: ttf-mscorefonts-installer)
```

**Agent skills (optional)** — `plotplate skills --dest .claude/skills` copies them into a project,
`--list` says what each one is for and where it lives.
They travel inside the package, however it was installed.

## Try it

```sh
plotplate demo --dir ~/plotplate-demo --build    # the whole walkthrough
plotplate view ~/plotplate-demo/figures/figure_1 # then look at what it made
```

It starts from a manuscript page where a figure was assembled by hand, reads it back, spends the space
it wasted, draws the panels of the maintained layout, and exports the result — so the folder ends with
three layouts of one figure to compare.
Drawing the panels needs pandas, pyarrow, scipy and seaborn in the environment that runs it.
[The demo README](src/plotplate/demo/figure/README.md) walks through every step.

## Where files go

`plotplate` works on the folder you point it at, and writes nothing inside the installation:

```text
any/folder/figure_1/
  layout.yaml             # you write it, or link it to the variant in use
  layout.optimized.yaml   # alternatives, named after where they came from
  figure_1-figure.tex     # the caption and the figure environment: yours, written once
  alignment.yaml          # optional, and only for what a rectangle cannot say
  code/                   # your panel scripts, with code_dir: code
  data/                   # optional: the tables they read
  output/                 # everything a build writes, with output_dir: output
    panels/A.pdf ...      #   one file per panel, written by panel.save()
    page.pdf/png/svg      #   the figure on its sheet: what you look at
    figure_1.tex          #   the panels, placed, for LaTeX
    overleaf/             #   plotplate latex: the folder you upload
```

`code_dir` and `output_dir` both default to the figure folder itself.
Commands take either the file or the folder (`plotplate build figures/figure_1`), and `plotplate view`
offers every `layout.<variant>.yaml` it finds next to `layout.yaml`.

There is no project skeleton to copy: keep figures inside an existing analysis or paper repository,
one folder per figure.

## Drawing a panel

Your plotting code does not change.
It is given a figure of exactly the right size, and hands it back when it is done:

```python
import plotplate as pp

panel = pp.Layout.load("layout.yaml").panel("A")
fig = panel.figure()  # exactly the size of box A, journal style applied
ax = fig.add_subplot()  # ... then your code, unchanged: gridspec, seaborn, anything
ax.plot(fpr, tpr)
panel.save(fig)  # output/panels/A.pdf .svg .png, and the checks
```

`panel.save` replaces your `plt.savefig` calls, and runs the checks that catch what a figure cannot
show you: fonts below the journal minimum, clipped text, lines too thin to print.
When panels must line up with each other, declare their axes in the layout and ask for them by name —
[python-api.md](docs/python-api.md) has that, and the rest of the API.

## Documentation

| question | file |
| --- | --- |
| What do page, area, panel, axes, guide, gutter mean, and what goes in `layout.yaml`? | [layout.md](docs/layout.md) |
| How do I write the panel code? | [python-api.md](docs/python-api.md) |
| What does the viewer do? | [view.md](docs/view.md) |
| What does plotplate give LaTeX, and what do I write? | [latex.md](docs/latex.md) |
| My figure came from an old PDF or a screenshot | [layout-sources.md](docs/layout-sources.md) |
| The boxes waste space | [optimize.md](docs/optimize.md) |
| Axes across panels must line up | [alignment.md](docs/alignment.md) |
| What does this journal require? | [journal-specs.md](docs/journal-specs.md) |
| Why not use \<some other tool>? | [related-tools.md](docs/related-tools.md) |
| Why is it built this way? | [design-notes.md](docs/design-notes.md) |

## Commands

`plotplate --help` lists them in the same four groups.

| | |
| --- | --- |
| **the four you need** | `detect` draft a layout from a figure that exists · `optimize` spend the white space · `view` move the boxes in a browser · `build` draw the panels and check them |
| **at hand-off** | `check` everything that can be wrong, in one report · `export` the figure as one file (.pdf, .png, .tif, .svg) · `latex` the folder to upload to Overleaf |
| **when a layout needs surgery** | `new` · `merge` · `resolve` · `diff` · `wireframe` |
| **your setup** | `demo` · `doctor` · `skills` · `journals` |

## Contributing

Development uses Pixi; see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
