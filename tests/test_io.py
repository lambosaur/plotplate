import shutil
import subprocess

import numpy as np
import pymupdf
import pytest

import plotplate as pp
from plotplate.config import load_yaml
from plotplate.detect import draft_layout
from plotplate.latex import figure_tex, standalone_document
from plotplate.render import preview, wireframe
from plotplate.svg import export_svg, import_svg
from plotplate.tidy import fill_gaps, merge_panels, tidy
from plotplate.variants import find_layouts


def test_svg_roundtrip_keeps_boxes(layout, tmp_path):
    svg = export_svg(layout, tmp_path / "l.svg")
    data, issues = import_svg(svg, layout.raw)
    assert not [i for i in issues if i.level != "info"]
    pp.config.dump_yaml(data, tmp_path / "again.yaml")  # plain types only
    again = pp.Layout.load(tmp_path / "again.yaml")
    for name, spec in layout.panels.items():
        assert again.panels[name].box.to_list() == spec.box.to_list()
        for ax_name, ax in spec.axes.items():
            assert again.panels[name].axes[ax_name].region.to_list() == ax.region.to_list()
    assert again.panels["A"].axes["grid"].ncols == 2  # non-geometric settings survive


def test_svg_import_handles_transforms_and_units(tmp_path):
    svg = tmp_path / "drawn.svg"
    svg.write_text(
        """<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     width="100mm" height="50mm" viewBox="0 0 400 200">
  <g inkscape:groupmode="layer" inkscape:label="panels" transform="translate(20,0)">
    <rect inkscape:label="A" x="0" y="0" width="160" height="200"/>
    <g transform="matrix(1,0,0,1,200,0)">
      <rect inkscape:label="B" x="0" y="0" width="160" height="100"/>
    </g>
  </g>
</svg>"""
    )
    data, _ = import_svg(svg)
    assert data["area"] == {"width": 100.0, "height": 50.0}
    assert data["panels"]["A"]["box"] == [5.0, 0.0, 40.0, 50.0]
    assert data["panels"]["B"]["box"] == [55.0, 0.0, 40.0, 25.0]


def test_tidy_aligns_and_snaps():
    data = {
        "page": {"width": 100, "height": 50},
        "panels": {"A": {"box": [0.2, 0.1, 47.8, 49.7]}, "B": {"box": [52.1, 0.4, 47.7, 20.2]}},
    }
    out = tidy(data, tolerance=1.0, step=0.5)
    assert out["panels"]["A"]["box"] == [0.0, 0.0, 48.0, 50.0]
    assert out["panels"]["B"]["box"] == [52.0, 0.0, 48.0, 20.5]


def test_merge_and_fill_gaps():
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
    filled = fill_gaps(merged, gap=4)
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
    assert "\\makebox(0,0)[lt]{\\plotplatePanelLabel{a}}" in tex
    for line in tex.splitlines():  # no stray spaces leak into the enclosing paragraph
        assert "%" in line


@pytest.mark.skipif(shutil.which("tectonic") is None, reason="tectonic not installed")
def test_latex_matches_preview(layout, tmp_path):
    _draw_all(layout)
    doc = tmp_path / "doc.tex"
    doc.write_text(standalone_document(layout, graphics_prefix=f"{layout.panels_dir}/", labels=False))
    try:
        subprocess.run(
            ["tectonic", doc.name], cwd=tmp_path, check=True, capture_output=True, timeout=300
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


def test_cli_build_check_bundle(layout, tmp_path, capsys):
    from plotplate.cli import main

    _draw_all(layout)
    assert main(["check", str(layout.path)]) == 0
    from plotplate.render import preview

    preview(layout)  # the composed figure, which the bundle carries for looking at
    assert main(["bundle", str(layout.path), str(tmp_path / "overleaf")]) == 0
    tex = (tmp_path / "overleaf" / "t.tex").read_text()
    assert "figures/t/A.pdf" in tex
    assert (tmp_path / "overleaf" / "B.pdf").exists()
    assert (tmp_path / "overleaf" / "t.pdf").exists()  # ... as one file, for a co-author
    out = capsys.readouterr().out
    assert "\\input{figures/t/t.tex}" in out  # the exact line to paste in the manuscript
    assert "\\includegraphics{figures/t/t.pdf}" in out  # ... or this one, once hand-finished
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
    assert main(["demo"]) == 0  # lists the cases
    assert main(["demo", "nope", "--dir", str(dest)]) == 1  # unknown case
    assert main(["demo", "figure", "--dir", str(dest)]) == 0
    figure = dest / "figures" / "figure_1"
    assert (dest / "legacy" / "manuscript.pdf").exists()
    assert (figure / "layout.yaml").exists()
    assert main(["demo", "figure", "--dir", str(dest)]) == 1  # refuses a non-empty folder
    pytest.importorskip("seaborn")
    pytest.importorskip("pyarrow")
    assert main(["demo", "figure", "--dir", str(dest), "--build", "--force"]) == 0
    # the three layouts of the walkthrough: read back, optimized, and the maintained one
    assert set(find_layouts(figure)) == {"base", "detected", "optimized"}
    assert load_yaml(figure / "layout.optimized.yaml")["area"] == {"width": 183.0, "height": 168.0}
    assert (figure / "export" / "Figure1.pdf").exists()
    assert (figure / "preview-page.png").exists()


def test_svg_import_illustrator_style_ids(tmp_path):
    svg = tmp_path / "illustrator.svg"
    svg.write_text(
        """<svg xmlns="http://www.w3.org/2000/svg"
     width="183mm" height="100mm" viewBox="0 0 518.74 283.46">
  <g id="panels">
    <rect id="A" x="0" y="0" width="255" height="283.46"/>
    <rect id="B" x="263.74" y="0" width="255" height="283.46"/>
    <rect id="rect12" x="1" y="1" width="2" height="2"/>
  </g>
  <g id="axes"><rect id="A_x2F_roc_1_" x="28.35" y="14.17" width="200" height="200"/></g>
</svg>"""
    )
    data, issues = import_svg(svg)
    assert list(data["panels"]) == ["A", "B"]
    assert data["panels"]["B"]["box"][0] == pytest.approx(93.04, abs=0.01)
    assert data["panels"]["A"]["axes"]["roc"]["box"][:2] == pytest.approx([10.0, 5.0], abs=0.01)
    assert [i.code for i in issues] == ["svg-unlabelled"]


def test_awkward_arrangements_are_read_back_and_refused_by_the_optimizer(tmp_path):
    """The fixture nobody should copy: an inset, a pinwheel, and overflowing content."""
    from plotplate.cli import main
    from plotplate.pack import PackError, Target, optimize

    from .fixtures.awkward_figure import build

    pdf = build(tmp_path / "awkward.pdf")
    out = tmp_path / "layout.detected.yaml"
    assert main(["from-pdf", str(pdf), "-o", str(out), "--axes", "--guides"]) == 0
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


def test_svg_import_survives_a_plain_svg_save(layout, tmp_path):
    """Inkscape's Plain SVG drops inkscape:label; the ids plotplate wrote still name the panels."""
    import re

    svg = export_svg(layout, tmp_path / "l.svg")
    stripped = re.sub(r'\s+inkscape:label="[^"]*"', "", svg.read_text(encoding="utf-8"))
    plain = tmp_path / "plain.svg"
    plain.write_text(stripped, encoding="utf-8")

    data, issues = import_svg(plain, layout.raw)
    assert set(data["panels"]) == set(layout.panels)  # not "panel-A", and nothing lost
    assert data["panels"]["A"]["axes"]["roc"]["box"] == pytest.approx(
        layout.panels["A"].axes["roc"].region.to_list(), abs=0.01
    )
    assert [i.code for i in issues] == []


def test_svg_import_keeps_axes_names_that_repeat_across_panels(tmp_path):
    """Axes names are per-panel: two panels may both have a `roc`, and a panel name may hyphenate."""
    import re

    data = {
        "schema": 1,
        "name": "t",
        "area": {"width": 180, "height": 60},
        "panels": {
            "A": {"box": [0, 0, 88, 60], "axes": {"roc": {"box": [10, 5, 70, 45]}}},
            "A-zoom": {"box": [92, 0, 88, 60], "margins": [10, 5, 8, 10]},
        },
    }
    path = tmp_path / "layout.yaml"
    pp.config.dump_yaml(data, path)
    layout = pp.Layout.load(path)

    svg = export_svg(layout, tmp_path / "l.svg")
    plain = tmp_path / "plain.svg"
    plain.write_text(
        re.sub(r'\s+inkscape:label="[^"]*"', "", svg.read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    updated, issues = import_svg(plain, layout.raw)

    assert set(updated["panels"]) == {"A", "A-zoom"}  # "A-zoom/main" did not become "A/zoom-main"
    assert [i.code for i in issues] == []


def test_panel_letters_take_no_space_and_follow_the_style(layout, tmp_path):
    """The letter is stamped at a millimetre inside `picture`: the figure keeps its size."""
    from plotplate.latex import figure_tex

    tex = figure_tex(layout)
    assert "subfigure" not in tex and "subcaption" not in tex  # those would add a line per panel
    assert f"\\begin{{picture}}({layout.width:.2f},{layout.height:.2f})" in tex
    assert "\\fontsize{8pt}{8pt}\\selectfont\\sffamily\\bfseries" in tex  # from the style
    assert "\\makebox(0,0)[lt]{\\plotplatePanelLabel{a}}" in tex  # nature: lower case

    styled = pp.Layout(
        {
            **layout.raw,
            "style": {"panel_label": {"format": "({letter})", "latex_font": "\\fontspec{Arial}"}},
        },
        layout.path,
    )
    assert "\\plotplatePanelLabel{(a)}" in figure_tex(styled)
    assert "\\selectfont\\fontspec{Arial}\\bfseries" in figure_tex(styled)


def test_the_label_format_reaches_the_preview_too(layout, tmp_path):
    """What LaTeX draws and what the preview draws are the same string."""
    from plotplate.render import _preview_svg

    styled = pp.Layout({**layout.raw, "style": {"panel_label": {"format": "{letter})"}}}, layout.path)
    svg = _preview_svg(styled, tmp_path / "preview.svg", labels=True).read_text()
    assert ">a)<" in svg
