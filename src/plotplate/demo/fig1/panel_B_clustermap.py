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
# # Figure 1, panel B: clustermap
#
# `sns.clustermap` builds its own figure with several axes. It is still one panel:
# `place_clustermap` resizes the figure to the box and pins the heatmap to the
# `heatmap` rectangle from the layout (bottom edge shared with panel A's axes).

# %%
import pandas as pd
import seaborn as sns

import plotplate as pp
from plotplate.seaborn_helpers import place_clustermap

layout = pp.Layout.load("layout.yaml")
panel = layout.panel("B")

# %% [markdown]
# ## Data

# %%
matrix = pd.read_parquet("data/correlation_matrix.parquet")

# %% [markdown]
# ## Plot

# %%
with panel.style():
    grid = sns.clustermap(
        matrix,
        figsize=panel.figsize,
        cmap="RdBu_r",
        vmin=-1,
        vmax=1,
        linewidths=0,
        xticklabels=True,
        yticklabels=True,
        dendrogram_ratio=0.1,
        cbar_kws={"ticks": [-1, 0, 1]},
    )
    place_clustermap(grid, panel, "heatmap", row_dendrogram_mm=8, col_dendrogram_mm=5, cbar="cbar")
    grid.ax_heatmap.set(xlabel="", ylabel="")
    grid.ax_heatmap.tick_params(axis="both", length=0, pad=1)
    grid.ax_heatmap.tick_params(axis="x", rotation=90)
    grid.ax_cbar.set_title("r", fontsize=layout.style["font"]["small"], pad=2)

# %%
report = panel.save(grid.figure, source="panel_B_clustermap.py")
report

# %% [markdown]
# The panel in the context of the whole figure (from the saved panel files).

# %%
panel.context()
