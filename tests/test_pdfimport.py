import io

import matplotlib
import pymupdf
import pytest

import plotplate as pp
from plotplate.cli import main
from plotplate.config import load_yaml
from plotplate.geometry import mm_to_pt
from plotplate.pdfimport import layout_from_pdf

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _panel_pdf(size_in=(6.4, 4.8)):
    fig, ax = plt.subplots(figsize=size_in)
    ax.plot([0, 1], [0, 1])
    buffer = io.BytesIO()
    fig.savefig(buffer, format="pdf")
    plt.close(fig)
    return pymupdf.open("pdf", buffer.getvalue())


def _panel_png():
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.bar([1, 2], [3, 4])
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=100)
    plt.close(fig)
    return buffer.getvalue()


def _rect(x, y, w, h):
    return pymupdf.Rect(mm_to_pt(x), mm_to_pt(y), mm_to_pt(x + w), mm_to_pt(y + h))


@pytest.fixture
def manuscript(tmp_path):
    """A4 page: panel A = two placed PDFs, panel B = one placed PNG, bold letters, body text."""
    doc = pymupdf.open()
    page = doc.new_page(width=mm_to_pt(210), height=mm_to_pt(297))
    page.insert_text(
        (mm_to_pt(25), mm_to_pt(20)), "Body text with a single letter a here.", fontsize=10
    )
    src = _panel_pdf()
    page.show_pdf_page(_rect(25, 34, 40, 30), src, 0)
    page.show_pdf_page(_rect(67, 34, 40, 30), src, 0)
    page.insert_image(_rect(112, 34, 60, 45), stream=_panel_png())
    for letter, x in (("A", 25), ("B", 112)):
        page.insert_text((mm_to_pt(x), mm_to_pt(33)), letter, fontsize=10, fontname="hebo")
    path = tmp_path / "manuscript.pdf"
    doc.save(path)
    return path


def test_placed_graphics_and_letters(manuscript):
    result = layout_from_pdf(manuscript)
    assert result.method == "placed"
    assert len(result.placed) == 3
    forms = [p for p in result.placed if p.kind == "form"]
    assert forms[0].box.to_list(1) == [25.0, 34.0, 40.0, 30.0]
    assert forms[0].scale == pytest.approx(40 / (6.4 * 25.4), rel=0.01)
    image = next(p for p in result.placed if p.kind == "image")
    assert image.box.to_list(1) == [112.0, 34.0, 60.0, 45.0]
    assert image.dpi == pytest.approx(400 / (60 / 25.4), rel=0.01)

    panels = result.data["panels"]
    assert list(panels) == ["A", "B"]  # the two PDFs are grouped under letter A
    a, b = panels["A"]["box"], panels["B"]["box"]
    assert a[0] == 0 and b[0] == pytest.approx(87, abs=0.2)
    assert a[2] == pytest.approx(82, abs=0.2)  # 25..107 mm
    assert any("placed at" in note for note in result.notes)


def test_flattened_page_falls_back_to_detection(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page(width=mm_to_pt(100), height=mm_to_pt(60))
    for x in (5, 55):
        page.draw_rect(_rect(x, 5, 40, 50), color=(0, 0, 0), fill=(0.2, 0.4, 0.8))
    path = tmp_path / "flat.pdf"
    doc.save(path)
    result = layout_from_pdf(path)
    assert result.method == "detected"
    assert len(result.data["panels"]) == 2


def test_cli_from_pdf_rescales_to_journal_width(manuscript, tmp_path):
    out = tmp_path / "draft" / "layout.yaml"
    assert (
        main(
            [
                "from-pdf",
                str(manuscript),
                "-o",
                str(out),
                "--journal",
                "nature",
                "--width",
                "double",
                "--fill-gap",
                "4",
                "--wireframe",
                str(tmp_path / "draft" / "wireframe.png"),
            ]
        )
        == 0
    )
    data = load_yaml(out)
    assert data["area"]["width"] == 183
    assert data["page"]["paper"] == "a4"  # the source page was A4: the sheet is recorded
    assert data["journal"] == "nature"
    assert (tmp_path / "draft" / "wireframe.png").exists()


def test_axes_and_guides_are_read_from_vector_panels(tmp_path):
    """A page whose panels are vector PDFs keeps its axes rectangles and shared edges."""
    doc = pymupdf.open()
    page = doc.new_page(width=mm_to_pt(120), height=mm_to_pt(60))
    src = _panel_pdf((2.0, 1.5))  # matplotlib default margins inside a 50.8 x 38.1 mm panel
    page.show_pdf_page(_rect(5, 10, 50, 38), src, 0)
    page.show_pdf_page(_rect(62, 10, 50, 38), src, 0)
    for letter, x in (("A", 5), ("B", 62)):
        page.insert_text((mm_to_pt(x), mm_to_pt(9)), letter, fontsize=9, fontname="hebo")
    path = tmp_path / "vector.pdf"
    doc.save(path)

    result = layout_from_pdf(path, axes=True)
    axes = {k: v["axes"] for k, v in result.data["panels"].items()}
    assert list(axes["A"]) == ["ax1"] and list(axes["B"]) == ["ax1"]
    a_box = axes["A"]["ax1"]["box"]
    assert 5 < a_box[0] < 20 and a_box[2] > 25  # inside panel A, a real plotting area

    with_guides = layout_from_pdf(path, axes=True, guides=0.5)
    guides = with_guides.data["guides"]
    assert guides["y"], "the two panels share their top and bottom axes edges"
    entry = with_guides.data["panels"]["A"]["axes"]["ax1"]
    assert ("box" not in entry and entry["top"] in guides["y"].values()) or isinstance(
        entry["top"], str
    )
    layout = pp.Layout(with_guides.data)
    assert layout.panels["A"].axes["ax1"].region.h > 10
