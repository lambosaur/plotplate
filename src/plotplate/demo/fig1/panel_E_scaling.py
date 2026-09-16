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
# # Figure 1, panel E: performance vs training set size

# %%
import pandas as pd

import plotplate as pp

layout = pp.Layout.load("layout.yaml")
panel = layout.panel("E")

# %% [markdown]
# ## Data

# %%
scaling = pd.read_parquet("data/scaling.parquet")

# %% [markdown]
# ## Plot

# %%
fig = panel.figure()
ax = panel.axes(fig, "main")
for model, group in scaling.groupby("model", sort=False):
    ax.errorbar(
        group["n_train"],
        group["pearson"],
        yerr=group["sd"],
        color=panel.colors[model],
        marker="o",
        markersize=2.5,
        capsize=1.5,
        elinewidth=0.5,
        label=model,
    )
ax.set_xscale("log")
ax.set(xlabel="Training examples", ylabel="Mean Pearson r")
ax.legend(loc="upper left")

# %%
report = panel.save(fig, source="panel_E_scaling.py")
report

# %% [markdown]
# The panel in the context of the whole figure (from the saved panel files).

# %%
panel.context()
