import json

import pymupdf
import pytest
import seaborn as sns

import plotplate as pp
from plotplate.geometry import pt_to_mm
from plotplate.marsilea_helpers import fit_marsilea
from plotplate.seaborn_helpers import place_clustermap


def codes(issues):
    return {i.code for i in issues}


def test_save_writes_exact_size_and_report(layout, tmp_path):
    panel = layout.panel("A")
    fig = panel.figure()
    ax = panel.axes(fig, "roc")
    ax.plot([0, 1], [0, 1])
    ax.set_xlabel("x")
    report = panel.save(fig)
    assert report.ok, report
    assert sorted(report.files) == ["A.pdf", "A.png", "A.svg"]
    with pymupdf.open(layout.panels_dir / "A.pdf") as doc:
        assert pt_to_mm(doc[0].rect.width) == pytest.approx(89.5, abs=0.01)
        assert pt_to_mm(doc[0].rect.height) == pytest.approx(60, abs=0.01)
        fonts = {f[3] for f in doc[0].get_fonts()}
    assert any("Arial" in f or "Liberation" in f or "DejaVu" in f for f in fonts)
    meta = json.loads((layout.panels_dir / "A.json").read_text())
    assert meta["box_mm"] == [0, 0, 89.5, 60]


def test_grid_axes_shape(layout):
    panel = layout.panel("A")
    axes = panel.axes(panel.figure(), "grid")
    assert axes.shape == (1, 2)


def test_font_too_small_and_clipping(layout):
    panel = layout.panel("B")
    fig, axes = panel.subplots()
    axes["main"].set_title("tiny", fontsize=3)
    fig.text(0.99, 0.5, "this label runs off the edge")
    found = codes(panel.check(fig))
    assert "font-too-small" in found
    assert "text-clipped" in found


def test_legend_after_figure_uses_style(layout):
    panel = layout.panel("B")
    _, axes = panel.subplots()
    axes["main"].plot([0, 1], label="line")
    legend = axes["main"].legend()
    assert legend.get_texts()[0].get_fontsize() == layout.style["font"]["small"]


def test_wrong_size_and_moved_axes(layout):
    panel = layout.panel("A")
    fig = panel.figure()
    ax = panel.axes(fig, "roc")
    ax.set_position((0.3, 0.3, 0.4, 0.4))  # e.g. moved by hand or by a helper
    fig.set_size_inches(3, 2)
    found = codes(panel.check(fig))
    assert "figure-size" in found
    assert "axes-moved" in found


def test_overlap_warning(layout):
    panel = layout.panel("B")
    fig, axes = panel.subplots()
    axes["main"].text(0.5, 0.5, "first label", transform=axes["main"].transAxes)
    axes["main"].text(0.52, 0.5, "second label", transform=axes["main"].transAxes)
    assert "text-overlap" in codes(panel.check(fig))


def test_clustermap_fits_box(layout):
    import numpy as np

    panel = layout.panel("B")
    data = np.random.default_rng(0).normal(size=(6, 4))
    with panel.style():
        grid = sns.clustermap(data, figsize=(8, 8))
        place_clustermap(grid, panel, "main", col_dendrogram_mm=3, cbar=None)
    issues = panel.check(grid.figure)
    assert "figure-size" not in codes(issues)
    assert "axes-moved" not in codes(issues)
    _, _, w, _ = grid.ax_heatmap.get_position().bounds
    assert w * panel.box.w == pytest.approx(77.5, abs=0.01)


def test_font_size_spread(layout_data, tmp_path):
    layout_data["style"] = {"font": {"max_spread": 1}}
    pp.config.dump_yaml(layout_data, tmp_path / "l.yaml")
    panel = pp.Layout.load(tmp_path / "l.yaml").panel("B")
    fig, axes = panel.subplots()
    axes["main"].set_xlabel("label")  # font.size 7 vs tick labels 6 -> spread 1, fine
    assert "font-size-spread" not in codes(panel.check(fig))
    axes["main"].set_title("title", fontsize=8)
    assert "font-size-spread" in codes(panel.check(fig))


def test_color_cycle_palette(layout_data, tmp_path):
    layout_data["style"] = {"color_cycle": "wong-no-black"}
    pp.config.dump_yaml(layout_data, tmp_path / "l.yaml")
    panel = pp.Layout.load(tmp_path / "l.yaml").panel("B")
    _, axes = panel.subplots()
    (line,) = axes["main"].plot([0, 1])
    assert line.get_color().upper() == pp.palette("wong-no-black")[0]


def test_marsilea_fill_and_pin(layout):
    ma = pytest.importorskip("marsilea")
    import numpy as np

    panel = layout.panel("B")
    data = np.random.default_rng(0).normal(size=(8, 5))

    def build(w, h):
        board = ma.Heatmap(data, width=w, height=h, label="z")
        board.add_right(ma.plotter.Labels([f"row{i}" for i in range(8)]), pad=0.02)
        board.add_dendrogram("left", size=0.2)
        return board

    board = fit_marsilea(build, panel)
    assert "figure-size" not in codes(panel.check(board.figure))

    target = pp.Rect(110, 8, 40, 38)
    board = fit_marsilea(build, panel, main=target)
    fig = board.figure
    x0, _, x1, y1 = board.get_main_ax().get_position().extents
    assert panel.box.x + x0 * panel.box.w == pytest.approx(110, abs=0.01)
    assert panel.box.y + (1 - y1) * panel.box.h == pytest.approx(8, abs=0.01)
    assert (x1 - x0) * panel.box.w == pytest.approx(40, abs=0.01)
    assert not {"figure-size", "axes-moved"} & codes(panel.check(fig))

    with pytest.raises(ValueError, match="not enough room"):
        fit_marsilea(build, panel, main=pp.Rect(94, 1, 88, 58))


def test_checks_measure_at_export_dpi_and_restore(layout):
    panel = layout.panel("B")
    fig, axes = panel.subplots()
    axes["main"].set_xlabel("x")
    dpi = fig.dpi
    panel.check(fig)
    assert fig.dpi == dpi


def test_axes_grid_ratios_and_gridspec(layout_data, tmp_path):
    layout_data["panels"]["A"]["axes"]["ratio"] = {
        "box": [10, 5, 70, 40],
        "width_ratios": [2, 1],
        "height_ratios": [1, 3],
        "wgap": 4,
        "hgap": 2,
    }
    pp.config.dump_yaml(layout_data, tmp_path / "l.yaml")
    panel = pp.Layout.load(tmp_path / "l.yaml").panel("A")
    rects = panel.axes_rects("ratio")
    assert [round(r.w, 3) for r in rects[:2]] == [44.0, 22.0]
    assert [round(r.h, 3) for r in (rects[0], rects[2])] == [9.5, 28.5]
    assert rects[1].left == pytest.approx(58.0)

    fig = panel.figure()
    gs = panel.gridspec(fig, pp.Rect(10, 5, 70, 40), 1, 3, wgap=5)
    axes = [fig.add_subplot(gs[0, i]) for i in range(3)]
    first, second = (ax.get_position() for ax in axes[:2])
    gap_mm = (second.x0 - first.x1) * panel.box.w
    assert gap_mm == pytest.approx(5, abs=0.01)
    assert first.x0 * panel.box.w == pytest.approx(10, abs=0.01)


def test_axes_outside_panel_is_an_error(layout):
    panel = layout.panel("B")
    fig = panel.figure()
    fig.add_axes((0.5, 0.9, 0.3, 0.2))  # top 10 % beyond the panel
    assert "axes-outside-panel" in codes(panel.check(fig))


def test_place_clustermap_refuses_parts_outside(layout_data, tmp_path):
    import numpy as np

    layout_data["panels"]["B"] = {"axes": {"heat": {"box": [110, 1, 50, 40]}}}
    pp.config.dump_yaml(layout_data, tmp_path / "l.yaml")
    panel = pp.Layout.load(tmp_path / "l.yaml").panel("B")
    with panel.style():
        grid = sns.clustermap(np.random.default_rng(0).normal(size=(6, 4)), figsize=panel.figsize)
    with pytest.raises(ValueError, match="outside the panel"):
        place_clustermap(grid, panel, "heat", col_dendrogram_mm=5)
