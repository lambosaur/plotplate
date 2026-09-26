# plotplate demo: one figure, from a hand-assembled page to a delivered file

A complete, synthetic walkthrough. Nothing here uses real data.
`plotplate demo figure --dir <folder> --build` copies this folder and runs every step inside it.

## The story

1. **The starting point: `legacy/manuscript.pdf`.**
   A manuscript page where a figure was assembled by hand in LaTeX: panels exported at whatever size
   looked right, scaled with `\includegraphics[width=...]`, gaps typed in millimetres, rows that do not
   line up. `legacy/manuscript.tex` and `legacy/make_legacy_panels.py` show how it was made.

1. **Read it back:** `figures/figure_1/layout.detected.yaml`.

   ```sh
   plotplate from-pdf legacy/manuscript.pdf -o figures/figure_1/layout.detected.yaml \
       --journal nature --width double --paper a4 --axes --guides \
       --wireframe figures/figure_1/detected.wireframe.png
   ```

   Exact panel positions, panels named from their letters, the plotting areas inside the vector panels,
   and the sheet the page was. It also reports how much each panel was scaled: fonts printed at 23 % of
   their size explain why the old figure looks uneven.

1. **Spend the white space it wasted:** `figures/figure_1/layout.optimized.yaml`.

   ```sh
   plotplate optimize figures/figure_1/layout.detected.yaml --gap 4 --max-stretch 1.5 --height 168
   ```

   Every gutter becomes 4 mm and the recovered space goes to the panels — here from 77 % of the figure
   covered to 92 % — while no panel grows by more than half. `--height 168` also brings the figure under
   Nature's 170 mm maximum, which the draft exceeded. See `docs/optimize.md` in the plotplate repository.

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

1. **Deliver:** the LaTeX snippet `figure_1.tex`, the production file, and a page view.

   ```sh
   plotplate export figures/figure_1 -o figures/figure_1/export/Figure1.pdf
   plotplate preview figures/figure_1 --page a4
   ```

## Look at all of it

```sh
plotplate view figures/figure_1
```

One page showing the figure on A4, with the layout over it, and the three layouts of this figure
(`base`, `detected`, `optimized`) to switch between and overlay. The panels were drawn for `base`, so
the other two report `panel-size` — that check is the point: a panel drawn at the wrong size is exactly
what plotplate exists to prevent. Rebuild against a layout to adopt it.

## Files

| path | what |
| --- | --- |
| `style.yaml` | project-wide style shared by all figures (named colors) |
| `legacy/` | the old figure: PDF page, its LaTeX source, the script that made its panels |
| `figures/figure_1/layout.yaml` | the maintained layout (Nature double column, A4, shared guides) |
| `figures/figure_1/alignment.yaml` | what must line up across panels, checked by `plotplate align` |
| `figures/figure_1/make_data.py` | writes the precomputed tables in `data/` |
| `figures/figure_1/panel_*.py` | Jupytext percent notebooks, one per panel |
| `figures/figure_1/variants/panel_B_marsilea.py` | panel B drawn with Marsilea instead of seaborn |

## Requirements

The demo panels need pandas, pyarrow, scipy and seaborn in the same environment as `plotplate`:

```sh
pipx install "plotplate[demo] @ git+https://github.com/<org>/plotplate"
# or, for an existing pipx install:
pipx inject plotplate pandas pyarrow scipy seaborn
```

The Marsilea variant also needs `marsilea`.
