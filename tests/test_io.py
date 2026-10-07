import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pymupdf
import pytest

import plotplate as pp
from plotplate.config import load_yaml
from plotplate.detect import draft_layout
from plotplate.latex import (
    figure_tex,
    standalone_document,
    write_figure_scaffold,
    write_figure_tex,
)
from plotplate.render import preview, wireframe
from plotplate.tidy import merge_panels, snap
from plotplate.variants import find_layouts


def test_snap_rounds_a_draft_and_keeps_axes_inside_their_panel():
    """What a detector measured becomes a few round numbers -- guides and axes included."""
    data = {
        "area": {"width": 100, "height": 50},
        "gutter": 4,
        "guides": {"x": {"left_axis": 10.2}, "y": {}},
        "panels": {
            "A": {
                "box": [0.2, 0.1, 47.8, 49.7],
                "axes": {"main": {"left": 10.1, "top": 2.2, "right": 44.9, "bottom": 44.8}},
            },
            "B": {"box": [52.1, 0.4, 47.7, 20.2]},
        },
    }
    out = snap(data, tolerance=1.0)
    assert out["panels"]["A"]["box"] == [0.0, 0.0, 48.0, 50.0]
    assert out["panels"]["B"]["box"] == [52.0, 0.0, 48.0, 50.0]  # grown into the space below
    axes = out["panels"]["A"]["axes"]["main"]
    assert (axes["left"], axes["right"]) == (10.0, 45.0)  # moved with the boxes, not left behind
    assert out["guides"]["x"]["left_axis"] == 10.0  # ... and so did the guide they share
    assert pp.Layout(out).validate() == []  # nothing ended up outside its panel


def test_merge_panels_unions_their_boxes():
    data = {
        "page": {"width": 100, "height": 50},
        "panels": {
            "S1": {"box": [5, 5, 30, 30]},
            "S2": {"box": [40, 5, 5, 30]},
            "S3": {"box": [60, 5, 30, 40]},
        },
    }
    merged = merge_panels(data, ["S1", "S2"], "A")
    assert list(merged["panels"]) == ["A", "S3"]
    assert merged["panels"]["A"]["box"] == [5, 5, 40, 30]
    filled = snap(merged, tolerance=0.1, gap=4, step=0)
    assert filled["panels"]["A"]["box"] == [0.0, 0.0, 50.5, 50.0]
    assert filled["panels"]["S3"]["box"] == [54.5, 0.0, 45.5, 50.0]


def _draw_all(layout):
    for name in layout.panels:
        panel = layout.panel(name)
        fig, axes = panel.subplots()
        for ax in axes.values():
            for a in np.atleast_1d(ax).ravel():
                a.plot([0, 1], [1, 0])
                a.set_xlabel("x value")
                a.set_ylabel("y")
        assert panel.save(fig, formats=["pdf", "svg", "png"]).ok


def test_preview_and_detect_recover_layout(layout, tmp_path):
    _draw_all(layout)
    paths = preview(layout, tmp_path)
    assert all(p.exists() for p in paths.values())
    wireframe(layout, tmp_path / "w.png", background=paths["png"])
    draft = draft_layout(paths["png"], layout.width)
    assert len(draft["panels"]) >= 2
    for seg in draft["panels"].values():  # every detected block sits inside a real panel
        box = pp.Rect.from_list(seg["box"])
        assert any(spec.box.contains(box, tol=1.0) for spec in layout.panels.values())


def test_latex_snippet_positions(layout):
    tex = figure_tex(layout)
    assert "\\put(93.50,0.00){\\includegraphics{panels/B.pdf}}" in tex
    assert "\\makebox(0,0)[lt]{{\\fontsize{8pt}{8pt}\\selectfont\\sffamily\\bfseries a}}" in tex
    for line in tex.splitlines():  # no stray spaces leak into the enclosing paragraph
        assert "%" in line


def _tectonic() -> str | None:
    """The tectonic binary, including the one beside this interpreter (pixi puts it there)."""
    found = shutil.which("tectonic")
    if found:
        return found
    sibling = Path(sys.executable).parent / "tectonic"
    return str(sibling) if sibling.exists() else None


@pytest.mark.skipif(_tectonic() is None, reason="tectonic not installed")
def test_latex_matches_preview(layout, tmp_path):
    _draw_all(layout)
    doc = tmp_path / "doc.tex"
    doc.write_text(standalone_document(layout, graphics_prefix=f"{layout.panels_dir}/", labels=False))
    try:
        subprocess.run(
            [str(_tectonic()), doc.name], cwd=tmp_path, check=True, capture_output=True, timeout=300
        )
    except subprocess.CalledProcessError as exc:  # e.g. offline, bundle not cached
        pytest.skip(f"tectonic failed: {exc.stderr[-300:]!r}")
    prev = preview(layout, tmp_path / "prev", labels=False)

    def raster(path):
        with pymupdf.open(path) as d:
            pix = d[0].get_pixmap(dpi=100, colorspace=pymupdf.csGRAY)
            return np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w).astype(float)

    a, b = raster(tmp_path / "doc.pdf"), raster(prev["pdf"])
    assert a.shape == b.shape
    assert (np.abs(a - b) > 64).mean() < 0.005


def test_cli_check_and_latex(layout, tmp_path, capsys):
    from plotplate.cli import main

    _draw_all(layout)
    assert main(["check", str(layout.path)]) == 0
    assert main(["latex", str(layout.path), str(tmp_path / "overleaf")]) == 0
    tex = (tmp_path / "overleaf" / "t.tex").read_text()
    assert "figures/t/A.pdf" in tex
    assert (tmp_path / "overleaf" / "B.pdf").exists()
    assert "makeatletter" not in tex  # the uploaded file stays the simplest thing that works
    out = capsys.readouterr().out
    assert "\\input{figures/t/t-figure.tex}" in out  # the one line the manuscript needs

    # the half the author owns: the figure environment, the caption, the label
    scaffold = (tmp_path / "overleaf" / "t-figure.tex").read_text()
    assert "\\begin{figure}" in scaffold and "\\caption{...}" in scaffold
    assert "\\input{figures/t/t.tex}" in scaffold and "\\label{fig:t}" in scaffold
    assert main(["resolve", str(layout.path), "-o", str(tmp_path / "resolved.yaml")]) == 0
    resolved = load_yaml(tmp_path / "resolved.yaml")
    assert "mosaic" not in resolved and resolved["panels"]["B"]["axes"]["main"]["box"]


def test_export_composite(layout, tmp_path):
    from PIL import Image

    from plotplate.render import export_figure

    with pytest.raises(ValueError, match="cannot export"):
        export_figure(layout, tmp_path / "missing.pdf")
    _draw_all(layout)
    pdf, issues = export_figure(layout, tmp_path / "Fig1.pdf")
    assert issues == []
    with pymupdf.open(pdf) as doc:
        assert len(doc) == 1
        text = doc[0].get_text()
        fonts = {f[3] for f in doc[0].get_fonts(full=True)}
    assert "a" in text.split() and "b" in text.split()  # letters are real text
    assert fonts
    tif, issues = export_figure(layout, tmp_path / "Fig1.tif", dpi=300)
    assert [i.code for i in issues] == ["export-format"]  # nature does not take TIFF
    with Image.open(tif) as image:
        assert image.info["compression"] == "tiff_lzw"
        assert image.size[0] == pytest.approx(183 / 25.4 * 300, abs=2)


def test_demo_copy_and_build(tmp_path):
    from plotplate.cli import main

    dest = tmp_path / "demo"
    assert main(["demo", "--dir", str(dest)]) == 0
    figure = dest / "figures" / "figure_1"
    assert (dest / "legacy" / "manuscript.pdf").exists()
    assert (figure / "layout.yaml").exists()
    assert main(["demo", "--dir", str(dest)]) == 1  # refuses a non-empty folder
    pytest.importorskip("seaborn")
    pytest.importorskip("pyarrow")
    assert main(["demo", "--dir", str(dest), "--build", "--force"]) == 0
    # the three layouts of the walkthrough: read back, optimized, and the maintained one
    assert set(find_layouts(figure)) == {"base", "detected", "optimized"}
    assert load_yaml(figure / "layout.optimized.yaml")["area"] == {"width": 183.0, "height": 168.0}
    assert (figure / "output" / "Figure1.pdf").exists()
    assert (figure / "output" / "page.png").exists()
    assert not (figure / "figure.pdf").exists()  # one folder holds everything generated


def test_awkward_arrangements_are_read_back_and_refused_by_the_optimizer(tmp_path):
    """The fixture nobody should copy: an inset, a pinwheel, and overflowing content."""
    from plotplate.cli import main
    from plotplate.pack import PackError, Target, optimize

    from .fixtures.awkward_figure import build

    pdf = build(tmp_path / "awkward.pdf")
    out = tmp_path / "layout.detected.yaml"
    assert main(["detect", str(pdf), "-o", str(out)]) == 0
    data = load_yaml(out)
    assert len(data["panels"]) == 7  # inset merged into its panel, pinwheel recovered
    assert data["page"]["paper"] == "a4"  # a figure-only PDF: the sheet asked for is recorded
    # Those panels really do overlap, so there is no grid to re-spend: the optimizer says so.
    with pytest.raises(PackError, match="do not form a grid"):
        optimize(pp.Layout.load(out), Target())


def test_build_refuses_an_interpreter_without_plotplate(layout, tmp_path, capsys):
    from plotplate.cli import main

    _draw_all(layout)
    fake = tmp_path / "python"
    fake.write_text("#!/bin/sh\nexit 1\n")
    fake.chmod(0o755)
    assert main(["build", str(layout.path), "--python", str(fake)]) == 1
    assert "cannot import plotplate" in capsys.readouterr().out


def test_doctor_reports_the_current_environment(capsys):
    from plotplate.cli import main

    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "versions agree" in out and "fonts:" in out


def test_panel_letters_take_no_space_and_follow_the_style(layout, tmp_path):
    """The letter is stamped at a millimetre inside `picture`: the figure keeps its size."""
    from plotplate.latex import figure_tex

    tex = figure_tex(layout)
    assert "subfigure" not in tex and "subcaption" not in tex  # those would add a line per panel
    assert f"\\begin{{picture}}({layout.width:.2f},{layout.height:.2f})" in tex
    assert "\\fontsize{8pt}{8pt}\\selectfont\\sffamily\\bfseries" in tex  # from the style
    assert "\\selectfont\\sffamily\\bfseries a}" in tex  # nature: lower case, inline font

    styled = pp.Layout(
        {
            **layout.raw,
            "style": {"panel_label": {"format": "({letter})", "latex_font": "\\fontspec{Arial}"}},
        },
        layout.path,
    )
    assert "\\bfseries (a)}" in figure_tex(styled)
    assert "\\selectfont\\fontspec{Arial}\\bfseries" in figure_tex(styled)


def test_the_label_format_reaches_the_preview_too(layout, tmp_path):
    """What LaTeX draws and what the preview draws are the same string."""
    from plotplate.render import _preview_svg

    styled = pp.Layout({**layout.raw, "style": {"panel_label": {"format": "{letter})"}}}, layout.path)
    svg = _preview_svg(styled, tmp_path / "preview.svg", labels=True).read_text()
    assert ">a)<" in svg


def test_the_default_tex_defines_nothing_at_all(layout):
    """The file is meant to be read in Overleaf: a picture, the images, the letters. Nothing else."""
    tex = figure_tex(layout)
    assert "\\makeatletter" not in tex and "\\gdef" not in tex and "@" not in tex
    defined = [line for line in tex.splitlines() if "\\providecommand" in line or "\\def" in line]
    assert not defined  # nothing at all is defined: the file is only pictures and text


@pytest.mark.skipif(_tectonic() is None, reason="tectonic not installed")
def test_the_panel_reference_recipe_compiles(layout, tmp_path):
    """The lines the figure file suggests really do give \\ref{fig:ta} -> "1a", and cost no space."""
    _draw_all(layout)
    body = figure_tex(layout, graphics_prefix=f"{layout.panels_dir}/")
    suggested = [
        line.strip().removeprefix("% ")
        for line in write_figure_scaffold(layout, tmp_path / "f.tex").read_text().splitlines()
        if "phantomsubcaption" in line
    ]
    assert len(suggested) == len(layout.panels)

    doc = tmp_path / "doc.tex"
    doc.write_text(
        "\\documentclass{article}\n\\usepackage{graphicx}\n\\usepackage{subcaption}\n"
        "\\usepackage{hyperref}\n\\begin{document}\n\\begin{figure}\n  \\centering\n"
        + body
        + "  \\caption{First}\\label{fig:t}\n  "
        + "\n  ".join(suggested)
        + "\n\\end{figure}\nrefs \\ref{fig:t} \\ref{fig:ta} \\ref{fig:tb}\n\\end{document}\n",
        encoding="utf-8",
    )
    try:
        subprocess.run(
            [str(_tectonic()), doc.name], cwd=tmp_path, check=True, capture_output=True, timeout=300
        )
    except subprocess.CalledProcessError as exc:  # e.g. offline, bundle not cached
        pytest.skip(f"tectonic failed: {exc.stderr[-300:]!r}")

    with pymupdf.open(tmp_path / "doc.pdf") as pdf:
        text = " ".join(" ".join(page.get_text().split()) for page in pdf)
    assert "refs 1 1a 1b" in text  # the figure, then its panels


def test_the_figure_file_is_written_once_and_never_overwritten(layout, tmp_path):
    """A caption written by hand survives every rebuild: plotplate only rewrites the panels."""
    scaffold = write_figure_scaffold(layout)
    assert scaffold.name == "t-figure.tex"
    text = scaffold.read_text()
    assert "\\phantomsubcaption\\label{fig:ta}" in text  # one per panel, ready to uncomment
    assert "\\makeatletter" not in text and "\\gdef" not in text
    mine = scaffold.read_text().replace("\\caption{...}", "\\caption{A real caption.}")
    scaffold.write_text(mine)

    write_figure_tex(layout)  # as `plotplate build` does, over and over
    write_figure_scaffold(layout)
    assert scaffold.read_text() == mine  # untouched

    assert "A real caption" not in write_figure_scaffold(layout, force=True).read_text()


def test_the_caption_you_wrote_is_the_caption_that_is_uploaded(layout, tmp_path):
    """`plotplate latex` copies the author's figure file; only the \\input path is rewritten."""
    from plotplate.cli import main
    from plotplate.latex import write_figure_scaffold, write_figure_tex

    write_figure_tex(layout)  # as a build does
    scaffold = write_figure_scaffold(layout)
    assert "\\input{t.tex}%" in scaffold.read_text()  # the .tex really is next to the layout
    assert (layout.base_dir / "t.tex").exists()

    scaffold.write_text(scaffold.read_text().replace("\\caption{...}", "\\caption{A real caption.}"))
    _draw_all(layout)
    assert main(["latex", str(layout.path), str(tmp_path / "overleaf")]) == 0
    uploaded = (tmp_path / "overleaf" / "t-figure.tex").read_text()
    assert "A real caption." in uploaded  # ... and it travelled
    assert "\\input{figures/t/t.tex}" in uploaded  # with the path the Overleaf project uses


def test_a_build_writes_the_page_view_and_the_layout_asks_for_the_outlines(layout, tmp_path):
    """`page: {outlines: true}` annotates the page view; export writes the figure itself."""
    import pymupdf

    from plotplate.cli import main
    from plotplate.render import compose, export_figure

    _draw_all(layout)

    def drawings(path):  # the panels draw plenty; the boxes are what is counted here
        with pymupdf.open(path) as doc:
            return len(doc[0].get_drawings())

    plain, marked = compose(layout), compose(layout, outlines=True)
    bare, boxed = len(plain[0].get_drawings()), len(marked[0].get_drawings())
    plain.close()
    marked.close()
    assert boxed > bare  # outlines are visible in a count

    assert main(["build", str(layout.path)]) == 0
    assert drawings(layout.output_dir / "page.pdf") >= bare
    assert not (layout.output_dir / "figure.pdf").exists()  # one rendering, not two
    export_figure(layout, tmp_path / "one.pdf")
    assert drawings(tmp_path / "one.pdf") == bare  # the figure itself stays clean

    layout.raw["page"] = {**(layout.sheet or {}), "outlines": True}
    layout.save()
    assert main(["build", str(layout.path)]) == 0
    assert drawings(layout.output_dir / "page.pdf") > bare


def test_export_writes_one_file_in_the_format_the_name_asks_for(layout, tmp_path):
    """The one cropped file: for a journal, a co-author, or a last touch in a drawing program."""
    from plotplate.render import export_figure

    _draw_all(layout)
    pdf, _ = export_figure(layout, tmp_path / "Figure1.pdf")
    assert pdf.exists()
    svg, _ = export_figure(layout, tmp_path / "touch-up.svg")
    text = svg.read_text()
    assert "<image" in text and "A.svg" in text  # links the panels, so each one stays editable
    with pytest.raises(ValueError, match="unsupported export format"):
        export_figure(layout, tmp_path / "Figure1.eps")


def test_export_refuses_a_hole_but_can_draw_a_draft(layout, tmp_path, capsys):
    """A missing panel stops the deliverable, as an error; --allow-missing makes a draft."""
    from plotplate.cli import main

    panel = layout.panel("A")
    fig, axes = panel.subplots()
    for ax in axes.values():
        for one in getattr(ax, "flat", [ax]):
            one.plot([0, 1], [1, 0])
    panel.save(fig, formats=["pdf"])  # only A is drawn; B is missing

    assert main(["export", str(layout.path), "-o", str(tmp_path / "fig.pdf")]) == 1
    message = capsys.readouterr().err
    assert "[error] panel-missing" in message and "--allow-missing" in message
    assert not (tmp_path / "fig.pdf").exists()

    assert (
        main(["export", str(layout.path), "-o", str(tmp_path / "draft.pdf"), "--allow-missing"]) == 0
    )
    assert (tmp_path / "draft.pdf").exists()
    assert "empty box" in capsys.readouterr().out
