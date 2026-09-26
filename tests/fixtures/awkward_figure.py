r"""Build a PDF with awkward panel arrangements, to test what ``from-pdf`` does with them.

An inset placed over another panel, a pinwheel (no straight gutter separates the panels, and
one panel label falls inside a neighbour's box), and a panel whose content overflows towards
its neighbour. These are the cases that break a naive reader, so they are kept as a fixture
rather than as an example to copy: nobody should lay a figure out this way.

Run it on its own to look at the file::

    pixi run -e dev python tests/fixtures/awkward_figure.py /tmp/awkward.pdf
    plotplate from-pdf /tmp/awkward.pdf -o /tmp/layout.detected.yaml --axes --guides
"""

from __future__ import annotations

import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pymupdf

from plotplate.geometry import mm_to_pt

# Panel boxes in millimetres, as the figure was assembled: (x, y, w, h, kind).
PANELS = {
    "A": (0, 6, 90, 60, "plot"),  # big panel ...
    "inset": (55, 12, 30, 22, "plot"),  # ... with an inset placed on top of it
    "B": (95, 6, 55, 26, "plot"),  # pinwheel: four panels around the centre,
    "C": (153, 6, 30, 55, "plot"),  # no straight gutter runs across them
    "D": (124, 35, 26, 26, "plot"),
    "E": (95, 35, 26, 55, "plot"),
    "F": (0, 75, 100, 60, "heat"),  # content overflowing towards its neighbour
    "G": (105, 75, 78, 60, "plot"),
}
LETTERS = {"A": (0, 5), "B": (95, 5), "C": (153, 5), "D": (124, 34), "E": (95, 34), "F": (0, 74),
           "G": (105, 74)}  # fmt: skip


def _panel(w_mm: float, h_mm: float, kind: str, rng: np.random.Generator) -> pymupdf.Document:
    """One panel of the given size, as a one-page PDF."""
    fig, ax = plt.subplots(figsize=(w_mm / 25.4, h_mm / 25.4))
    if kind == "heat":
        image = ax.imshow(rng.normal(size=(8, 8)), cmap="RdBu_r")
        fig.colorbar(image)
    else:
        ax.plot(rng.normal(size=30).cumsum())
        ax.set_xlabel("x")
        ax.set_ylabel("y")
    buffer = io.BytesIO()
    fig.savefig(buffer, format="pdf")
    plt.close(fig)
    return pymupdf.open("pdf", buffer.getvalue())


def build(out: str | Path, width: float = 183, height: float = 150) -> Path:
    """Write the awkward figure to ``out`` and return the path."""
    rng = np.random.default_rng(0)
    doc = pymupdf.open()
    page = doc.new_page(width=mm_to_pt(width), height=mm_to_pt(height))
    for x, y, w, h, kind in PANELS.values():
        with _panel(w, h, kind, rng) as source:
            page.show_pdf_page(
                pymupdf.Rect(mm_to_pt(x), mm_to_pt(y), mm_to_pt(x + w), mm_to_pt(y + h)), source, 0
            )
    for text, (x, y) in LETTERS.items():
        page.insert_text(pymupdf.Point(mm_to_pt(x), mm_to_pt(y)), text, fontsize=9, fontname="hebo")
    doc.save(out)
    doc.close()
    return Path(out)


if __name__ == "__main__":
    import sys

    print(f"wrote {build(sys.argv[1] if len(sys.argv) > 1 else 'awkward.pdf')}")
