# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Figure 1, panel B (variant): Marsilea heatmap
#
# The same data as `panel_B_clustermap.py`, drawn with Marsilea instead of seaborn.
# `fit_marsilea` renders twice so the whole figure fills the panel box, with the heatmap
# pinned to a rectangle derived from the layout (bottom edge on guide `row1_bottom`).
# Output goes to `variants/panels/` so it does not replace the main panel B.

# %%
import marsilea as ma
import marsilea.plotter as mp
import pandas as pd

import plotplate as pp
from plotplate.marsilea_helpers import fit_marsilea

layout = pp.Layout.load("../layout.yaml")
panel = layout.panel("B")
small = layout.style["font"]["small"]

# %% [markdown]
# ## Data

# %%
matrix = pd.read_parquet("../data/correlation_matrix.parquet")


# %% [markdown]
# ## Plot


# %%
def build(width_in: float, height_in: float) -> ma.Heatmap:
    board = ma.Heatmap(
        matrix.to_numpy(), cmap="RdBu_r", vmin=-1, vmax=1, width=width_in, height=height_in, label="r"
    )
    board.add_right(mp.Labels(matrix.index, fontsize=small, padding=0), pad=0.01)
    board.add_bottom(mp.Labels(matrix.columns, fontsize=small, padding=0), pad=0.005)
    board.add_dendrogram("left", size=0.25, colors="0.2")
    board.add_dendrogram("top", size=0.18, colors="0.2")
    board.add_legends("right", pad=0.03)
    return board


# The layout's `heatmap` rectangle leaves slightly too little room on the right for the
# Marsilea labels and legend (fit_marsilea reports the missing millimetres), so the
# heatmap is narrowed by 2 mm; its left, top and bottom edges stay on the layout lines.
heat = panel.axes_rect("heatmap")
board = fit_marsilea(build, panel, main=pp.Rect(heat.x, heat.y, heat.w - 2, heat.h))

# %%
report = panel.save(board.figure, outdir="panels", source="variants/panel_B_marsilea.py")
report
