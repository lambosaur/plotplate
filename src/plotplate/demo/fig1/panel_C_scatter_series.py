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
# # Figure 1, panel C: observed vs predicted, one scatterplot per RBP
#
# A 1 x 4 grid of axes defined once in the layout (`ncols: 4`, `wgap`).

# %%
import numpy as np
import pandas as pd

import plotplate as pp

layout = pp.Layout.load("layout.yaml")
panel = layout.panel("C")

# %% [markdown]
# ## Data

# %%
points = pd.read_parquet("data/observed_vs_predicted.parquet")

# %% [markdown]
# ## Plot

# %%
fig = panel.figure()
axes = panel.axes(fig, "scatter")[0]
for ax, (rbp, group) in zip(axes, points.groupby("rbp", sort=False), strict=True):
    r = np.corrcoef(group["observed"], group["predicted"])[0, 1]
    ax.scatter(
        group["observed"],
        group["predicted"],
        s=2,
        alpha=0.6,
        color=panel.colors["ParNet"],
        rasterized=True,
    )
    ax.set_title(f"{rbp} (r = {r:.2f})")
    ax.set(xlim=(-3, 3), ylim=(-4, 4), xlabel="Observed")
axes[0].set_ylabel("Predicted")

# %%
report = panel.save(fig, source="panel_C_scatter_series.py")
report

# %% [markdown]
# The panel in the context of the whole figure (from the saved panel files).

# %%
panel.context()
