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
# # Figure 1, panel A: ROC and precision-recall curves
#
# Two axes inside one panel. Their rectangles come from `layout.yaml`
# (`panels.A.axes`), so the ROC left spine aligns with panels C and D.

# %%
import pandas as pd

import plotplate as pp

layout = pp.Layout.load("layout.yaml")
panel = layout.panel("A")
colors = panel.colors

# %% [markdown]
# ## Data

# %%
roc = pd.read_parquet("data/roc_curves.parquet")
pr = pd.read_parquet("data/pr_curves.parquet")
areas = pd.read_parquet("data/areas.parquet").set_index("model")

# %% [markdown]
# ## Plot

# %%
fig = panel.figure()
ax_roc = panel.axes(fig, "roc")
ax_prc = panel.axes(fig, "prc")

for model, curve in roc.groupby("model", sort=False):
    ax_roc.plot(
        curve["fpr"],
        curve["tpr"],
        color=colors[model],
        label=f"{model} ({areas.loc[model, 'auroc']:.2f})",
    )
ax_roc.plot([0, 1], [0, 1], color="0.7", linewidth=0.5, linestyle="--")
ax_roc.set(xlabel="False positive rate", ylabel="True positive rate", xlim=(0, 1), ylim=(0, 1))
ax_roc.legend(loc="lower right", title="AUROC")

for model, curve in pr.groupby("model", sort=False):
    ax_prc.plot(
        curve["recall"],
        curve["precision"],
        color=colors[model],
        label=f"{areas.loc[model, 'auprc']:.2f}",
    )
ax_prc.set(xlabel="Recall", ylabel="Precision", xlim=(0, 1), ylim=(0, 1))
ax_prc.legend(loc="upper right", title="AUPRC")

# %%
report = panel.save(fig, source="panel_A_roc_prc.py")
report

# %% [markdown]
# The panel in the context of the whole figure (from the saved panel files).

# %%
panel.context()
