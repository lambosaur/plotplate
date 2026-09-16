"""The "before" situation: panels exported at default notebook sizes, with no layout.

These files were included in `manuscript.tex` with `\\includegraphics[width=...]`, which
scales every panel by a different factor. `manuscript.pdf` is the compiled result.
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure

rng = np.random.default_rng(1)


def roc() -> Figure:
    fig, ax = plt.subplots()
    x = np.linspace(0, 1, 50)
    ax.plot(x, x**0.3)
    ax.plot(x, x**0.6)
    ax.set_xlabel("FPR")
    ax.set_ylabel("TPR")
    return fig


def heat() -> Figure:
    fig, ax = plt.subplots(figsize=(8, 6))
    image = ax.imshow(rng.normal(size=(12, 8)), cmap="RdBu_r")
    fig.colorbar(image)
    return fig


def scatter() -> Figure:
    fig, axes = plt.subplots(1, 4, figsize=(16, 4))
    for ax in axes:
        ax.scatter(rng.normal(size=100), rng.normal(size=100), s=4)
    return fig


def box() -> Figure:
    fig, ax = plt.subplots()
    ax.boxplot([rng.normal(size=50) for _ in range(3)])
    return fig


def line() -> Figure:
    fig, ax = plt.subplots(figsize=(5, 3))
    ax.plot(rng.normal(size=20).cumsum())
    return fig


for name, maker, fmt in [
    ("roc", roc, "pdf"),
    ("prc", roc, "pdf"),
    ("heat", heat, "png"),
    ("scatter", scatter, "pdf"),
    ("box", box, "pdf"),
    ("line", line, "png"),
]:
    figure = maker()
    figure.savefig(f"{name}.{fmt}", bbox_inches="tight", dpi=150)
    plt.close(figure)
