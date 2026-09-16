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
# # Figure 1, panel D: per-RBP performance by model

# %%
import pandas as pd
import seaborn as sns

import plotplate as pp

layout = pp.Layout.load("layout.yaml")
panel = layout.panel("D")

# %% [markdown]
# ## Data

# %%
perf = pd.read_parquet("data/per_rbp_performance.parquet")
order = ["ParNet", "Baseline CNN", "k-mer model"]

# %% [markdown]
# ## Plot

# %%
fig = panel.figure()
ax = panel.axes(fig, "main")
with panel.style():
    sns.boxplot(
        data=perf,
        x="model",
        y="pearson",
        order=order,
        hue="model",
        hue_order=order,
        palette=panel.colors,
        ax=ax,
        width=0.6,
        fliersize=1.5,
        linewidth=0.5,
    )
ax.set(xlabel="", ylabel="Pearson r per RBP")

# %%
report = panel.save(fig, source="panel_D_boxplot.py")
report

# %% [markdown]
# The panel in the context of the whole figure (from the saved panel files).

# %%
panel.context()
