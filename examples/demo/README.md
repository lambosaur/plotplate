# plotplate demo

A complete, synthetic walkthrough. Nothing here uses real data.
`plotplate demo <folder> --build` copies this folder and runs every step inside `<folder>`.

## The story

1. **The starting point: `legacy/manuscript.pdf`.**
   A manuscript page where a figure was assembled in LaTeX from panels exported at default notebook sizes, then scaled with `\includegraphics[width=...]`.
   `legacy/manuscript.tex` and `legacy/make_legacy_panels.py` show how it was made.

1. **Draft a layout from it:** `legacy/draft/layout.yaml`.

   ```sh
   plotplate from-pdf legacy/manuscript.pdf -o legacy/draft/layout.yaml \
       --journal nature --width double --fill-gap 4 --wireframe legacy/draft/wireframe.png

   # with --axes --guides, the plotting areas and the edges panels share are read too
   plotplate from-pdf legacy/manuscript.pdf -o legacy/draft/with-axes.yaml --axes --guides
   ```

   The command reads where each panel was placed and names panels from their letters.
   It also reports how much each panel was scaled: fonts printed at 26 % of their size explain why the old figure looked uneven.

1. **Refine the layout:** `fig1/layout.yaml`.
   Starting from the draft, set the final height, and add guides so axes line up across panels (see the comments in the file).

1. **Draw the panels:** `fig1/panel_*.py`, one notebook per panel, from the tables in `fig1/data/` (written by `fig1/make_data.py`).

   ```sh
   python fig1/make_data.py
   plotplate build fig1/layout.yaml
   ```

1. **Deliver:** the LaTeX snippet `fig1/fig1.tex`, the production file, and a page view.

   ```sh
   plotplate export fig1/layout.yaml -o fig1/export/Figure1.pdf
   plotplate preview fig1/layout.yaml --page a4
   ```

## Files

| path | what |
| --- | --- |
| `style.yaml` | project-wide style shared by all figures (named colors) |
| `legacy/` | the old figure: PDF page, its LaTeX source, the script that made its panels |
| `fig1/layout.yaml` | the refined layout (Nature double column, shared guides) |
| `fig1/make_data.py` | writes the precomputed tables in `fig1/data/` |
| `fig1/panel_*.py` | Jupytext percent notebooks, one per panel |
| `fig1/variants/panel_B_marsilea.py` | panel B drawn with Marsilea instead of seaborn |

## Requirements

The demo panels need pandas, pyarrow, scipy and seaborn in the same environment as `plotplate`:

```sh
pipx install "plotplate[demo] @ git+https://github.com/<org>/plotplate"
# or, for an existing pipx install:
pipx inject plotplate pandas pyarrow scipy seaborn
```

The Marsilea variant also needs `marsilea`.
