"""Generate the synthetic, precomputed tables used by the demo panels.

In a real project this step is replaced by copying small result tables exported from the
analysis repositories into ``data/``. Only numpy and pandas (with pyarrow) are needed.
"""

from pathlib import Path

import numpy as np
import pandas as pd


def roc_curve(labels: np.ndarray, scores: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """False and true positive rates at every score threshold (numpy only)."""
    order = np.argsort(-scores)
    hits = labels[order]
    tpr = np.concatenate([[0.0], np.cumsum(hits) / hits.sum()])
    fpr = np.concatenate([[0.0], np.cumsum(~hits) / (~hits).sum()])
    return fpr, tpr


def pr_curve(labels: np.ndarray, scores: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Recall and precision at every score threshold (numpy only)."""
    order = np.argsort(-scores)
    hits = labels[order]
    true_positives = np.cumsum(hits)
    recall = true_positives / hits.sum()
    precision = true_positives / np.arange(1, len(hits) + 1)
    return np.concatenate([[0.0], recall]), np.concatenate([[1.0], precision])


rng = np.random.default_rng(7)
out = Path(__file__).resolve().parent / "data"
out.mkdir(exist_ok=True)
models = {"ParNet": 1.6, "Baseline CNN": 1.0, "k-mer model": 0.5}

# A: ROC / PR curves and their areas
labels = rng.random(4000) < 0.2
roc_rows, pr_rows, auc_rows = [], [], []
for model, signal in models.items():
    scores = rng.normal(labels * signal, 1.0)
    fpr, tpr = roc_curve(labels, scores)
    recall, precision = pr_curve(labels, scores)
    roc_rows.append(pd.DataFrame({"model": model, "fpr": fpr, "tpr": tpr}))
    pr_rows.append(pd.DataFrame({"model": model, "recall": recall, "precision": precision}))
    auc_rows.append(
        {"model": model, "auroc": np.trapezoid(tpr, fpr), "auprc": np.trapezoid(precision, recall)}
    )
pd.concat(roc_rows).to_parquet(out / "roc_curves.parquet", index=False)
pd.concat(pr_rows).to_parquet(out / "pr_curves.parquet", index=False)
pd.DataFrame(auc_rows).to_parquet(out / "areas.parquet", index=False)

# B: RBP x cell-type correlation matrix
rbps = [f"RBP{i:02d}" for i in range(1, 19)]
conditions = ["K562", "HepG2", "HEK293", "HeLa", "SH-SY5Y", "iPSC", "NPC", "MCF7"]
factors = rng.normal(size=(len(rbps), 2)) @ rng.normal(size=(2, len(conditions)))
matrix = pd.DataFrame(
    np.tanh(factors / 2 + rng.normal(0, 0.2, factors.shape)), index=rbps, columns=conditions
)
matrix.rename_axis("rbp").to_parquet(out / "correlation_matrix.parquet")

# C: observed vs predicted for four RBPs
scatter_rows = []
for rbp, noise in zip(["RBFOX2", "QKI", "PTBP1", "HNRNPC"], [0.4, 0.6, 0.8, 1.1], strict=True):
    observed = rng.normal(size=250)
    scatter_rows.append(
        pd.DataFrame(
            {"rbp": rbp, "observed": observed, "predicted": observed + rng.normal(0, noise, 250)}
        )
    )
pd.concat(scatter_rows).to_parquet(out / "observed_vs_predicted.parquet", index=False)

# D: per-RBP performance per model
perf = pd.DataFrame(
    [
        {
            "model": model,
            "rbp": f"RBP{i:03d}",
            "pearson": float(np.clip(rng.normal(0.25 + 0.2 * s, 0.1), -0.1, 0.95)),
        }
        for model, s in models.items()
        for i in range(120)
    ]
)
perf.to_parquet(out / "per_rbp_performance.parquet", index=False)

# E: performance as a function of training set size
sizes = np.array([1e3, 3e3, 1e4, 3e4, 1e5, 3e5, 1e6])
scaling = pd.DataFrame(
    [
        {
            "model": model,
            "n_train": int(n),
            "pearson": 0.2 + 0.1 * s * np.log10(n / 1e3) / 3,
            "sd": 0.02 + 0.01 * rng.random(),
        }
        for model, s in models.items()
        for n in sizes
    ]
)
scaling.to_parquet(out / "scaling.parquet", index=False)
print(f"wrote tables to {out}")
