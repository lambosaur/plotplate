r"""Build a PDF with awkward panel arrangements, to test `plotplate from-pdf`.

An inset placed over another panel, a pinwheel (no straight gutter separates the panels,
and one panel label falls inside a neighbour's box), and a panel whose content overflows
towards its neighbour. Run it, then:

    pixi run -e dev python examples/hard-layout/make.py
    plotplate from-pdf examples/hard-layout/hard.pdf -o examples/hard-layout/layout.yaml \\
        --axes --guides --wireframe examples/hard-layout/wireframe.png
    plotplate preview examples/hard-layout/layout.yaml
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import io

import matplotlib.pyplot as plt
import numpy as np
import pymupdf

from plotplate.geometry import mm_to_pt

rng = np.random.default_rng(0)


def panel_pdf(w_mm: float, h_mm: float, kind: str = "plot") -> "pymupdf.Document":
    """One panel of the given size, as a one-page PDF."""
    fig, ax = plt.subplots(figsize=(w_mm / 25.4, h_mm / 25.4))
    if kind == "heat":
        im = ax.imshow(rng.normal(size=(8, 8)), cmap="RdBu_r")
        fig.colorbar(im)
    else:
        ax.plot(rng.normal(size=30).cumsum())
        ax.set_xlabel("x")
        ax.set_ylabel("y")
    buf = io.BytesIO()
    fig.savefig(buf, format="pdf")
    plt.close(fig)
    return pymupdf.open("pdf", buf.getvalue())


def rect(x: float, y: float, w: float, h: float) -> "pymupdf.Rect":
    """Rectangle in millimetres, as PDF points."""
    return pymupdf.Rect(mm_to_pt(x), mm_to_pt(y), mm_to_pt(x + w), mm_to_pt(y + h))


doc = pymupdf.open()
page = doc.new_page(width=mm_to_pt(183), height=mm_to_pt(150))
# A: big panel with an inset placed on top of it
page.show_pdf_page(rect(0, 6, 90, 60), panel_pdf(90, 60), 0)
page.show_pdf_page(rect(55, 12, 30, 22), panel_pdf(30, 22), 0)  # inset inside A
# B: pinwheel - four panels rotating around the centre, no straight gutter across
page.show_pdf_page(rect(95, 6, 55, 26), panel_pdf(55, 26), 0)  # B top-left-ish
page.show_pdf_page(rect(153, 6, 30, 55), panel_pdf(30, 55), 0)  # C right tall
page.show_pdf_page(rect(124, 35, 26, 26), panel_pdf(26, 26), 0)  # D centre
page.show_pdf_page(rect(95, 35, 26, 55), panel_pdf(26, 55), 0)  # E left tall
# F: content overflowing to the right (wide colorbar area) next to G
page.show_pdf_page(rect(0, 75, 100, 60), panel_pdf(100, 60, "heat"), 0)
page.show_pdf_page(rect(105, 75, 78, 60), panel_pdf(78, 60), 0)
for text, x, y in (
    ("A", 0, 5),
    ("B", 95, 5),
    ("C", 153, 5),
    ("D", 124, 34),
    ("E", 95, 34),
    ("F", 0, 74),
    ("G", 105, 74),
):
    page.insert_text(pymupdf.Point(mm_to_pt(x), mm_to_pt(y)), text, fontsize=9, fontname="hebo")
out = Path(__file__).resolve().parent / "hard.pdf"
doc.save(out)
doc.close()
print(f"wrote {out}")
