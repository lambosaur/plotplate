# plotplate demo: one figure, from a hand-assembled page to a delivered file

A complete, synthetic walkthrough. Nothing here uses real data.
`plotplate demo --dir <folder> --build` copies this folder and runs every step inside it.

## The story

1. **The starting point: `legacy/manuscript.pdf`.**
   A manuscript page where a figure was assembled by hand in LaTeX: panels exported at whatever size
   looked right, scaled with `\includegraphics[width=...]`, gaps typed in millimetres, rows that do not
   line up. `legacy/manuscript.tex` and `legacy/make_legacy_panels.py` show how it was made.

1. **Read it back:** `figures/figure_1/layout.detected.yaml`.

   ```sh
   plotplate detect legacy/manuscript.pdf -o figures/figure_1/layout.detected.yaml \
       --journal nature --width double
   ```

   Exact panel positions, panels named from their letters, the plotting areas inside the vector panels,
   and the sheet the page was. It also reports how much each panel was scaled: fonts printed at 23 % of
   their size explain why the old figure looks uneven. The boxes it writes are round numbers that own
   the white space around their content, and
   `figures/figure_1/layout.detected.wireframe.png` shows them over the page they came from.

1. **Spend the white space it wasted:** `figures/figure_1/layout.optimized.yaml`.

   First say what the figure wants, in the draft itself — this is the file you would edit:

   ```yaml
   gutter: 4
   optimize: {height: 168}   # also brings it under Nature's 170 mm maximum
   ```

   ```sh
   plotplate optimize figures/figure_1/layout.detected.yaml
   ```

   The uneven gutters become 4 mm everywhere, and the space that frees goes to the panels. Nobody
   chose how much the panels may grow — the optimizer took the smallest factor that fills every row
   and says so. See `docs/optimize.md` in the plotplate repository.

1. **The layout that is maintained:** `figures/figure_1/layout.yaml`.
   Written by hand from those drafts: a round 183 × 150 mm, a mosaic instead of typed boxes, and named
   guides so axes line up across panels (read the comments in the file). This is the one that gets
   built; the two drafts stay next to it to compare against.

1. **Draw the panels:** `figures/figure_1/panel_*.py`, one notebook per panel, from the tables in
   `figures/figure_1/data/` (written by `make_data.py`).

   ```sh
   python figures/figure_1/make_data.py
   plotplate build figures/figure_1
   ```

   The build writes everything into `figures/figure_1/output/`: the panel files, the figure on its
   page (`page.png`, which is what you look at), and `figure_1.tex`, which places the panels.

1. **Deliver:** one file for the journal, or a folder for Overleaf.

   ```sh
   plotplate export figures/figure_1 -o figures/figure_1/output/Figure1.pdf
   plotplate latex figures/figure_1
   ```

## Look at all of it

```sh
plotplate view figures/figure_1
```

One page showing the figure on A4, with the layout over it, and the three layouts of this figure
(`base`, `detected`, `optimized`) to switch between and overlay.
Drag the boxes around and save the result as `layout.<name>.yaml`. The panels were drawn for
`base`, so the other two report `panel-size` — that check is the point: a panel drawn at the wrong
size is exactly what plotplate exists to prevent. Rebuild against a layout to adopt it.

## Files

| path | what |
| --- | --- |
| `style.yaml` | project-wide style shared by all figures (named colors) |
| `legacy/` | the old figure: PDF page, its LaTeX source, the script that made its panels |
| `figures/figure_1/layout.yaml` | the maintained layout (Nature double column, A4, shared guides) |
| `figures/figure_1/output/` | everything a build writes; delete it at any time |
| `figures/figure_1/make_data.py` | writes the precomputed tables in `data/` |
| `figures/figure_1/panel_*.py` | Jupytext percent notebooks, one per panel |
| `figures/figure_1/variants/panel_B_marsilea.py` | panel B drawn with Marsilea instead of seaborn |

## Requirements

The demo panels need pandas, pyarrow, scipy and seaborn in the same environment as `plotplate`:

```sh
pipx install "plotplate[demo] @ git+https://github.com/lambosaur/plotplate"
# or, for an existing pipx install:
pipx inject plotplate pandas pyarrow scipy seaborn
```

The Marsilea variant also needs `marsilea`.
