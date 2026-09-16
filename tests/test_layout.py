import pytest

import plotplate as pp
from plotplate.geometry import Rect


def test_journal_width_and_mosaic(layout):
    assert layout.width == 183
    assert layout.panels["A"].box == Rect(0, 0, 89.5, 60)
    assert layout.panels["B"].box == Rect(93.5, 0, 89.5, 60)


def test_guides_and_offsets(layout):
    roc = layout.panels["A"].axes["roc"].region
    assert (roc.left, roc.bottom) == (10, 50)
    grid = layout.panels["A"].axes["grid"]
    assert grid.region.bottom == 40
    rects = grid.rects()
    assert len(rects) == 2
    assert rects[0].w == pytest.approx(17)
    assert rects[1].left == pytest.approx(71)


def test_margins_make_main_axes(layout):
    main = layout.panels["B"].axes["main"].region
    assert main == Rect.from_edges(103.5, 4, 181, 50)


def test_labels_follow_journal_case(layout):
    assert layout.panels["A"].label == "a"


def test_style_layers(layout_data, tmp_path):
    (tmp_path / "style.yaml").write_text("font: {size: 6.5}\ncolors: {x: red}\n")
    layout_data["style_files"] = ["style.yaml"]
    layout_data["style"] = {"font": {"small": 5.5}}
    pp.config.dump_yaml(layout_data, tmp_path / "l.yaml")
    layout = pp.Layout.load(tmp_path / "l.yaml")
    assert layout.style["font"]["size"] == 6.5
    assert layout.style["font"]["small"] == 5.5
    assert layout.style["font"]["max"] == 7  # from the nature preset
    assert layout.colors == {"x": "red"}


def test_validate_reports_problems(layout_data):
    layout_data["page"]["height"] = 200
    layout_data["panels"]["C"] = {"box": [80, 0, 20, 20]}
    layout_data["panels"]["A"]["axes"]["bad"] = {"box": [85, 5, 20, 10]}
    issues = {i.code for i in pp.Layout(layout_data).validate()}
    assert {"page-height", "panel-overlap", "axes-outside-panel"} <= issues


def test_unknown_guide_is_an_error(layout_data):
    layout_data["panels"]["A"]["axes"]["roc"]["left"] = "nope"
    with pytest.raises(ValueError, match="guide"):
        pp.Layout(layout_data)


def test_all_bundled_journals_load():
    for name in pp.list_journals():
        preset = pp.load_journal(name)
        assert "page" in preset and "verified" in preset


def test_auto_labels_follow_reading_order(layout_data):
    layout_data["labels"] = "auto"
    layout_data["panels"] = {
        "scatter_grid": {"box": [0, 60, 183, 40]},
        "roc_prc": {"box": [0, 0, 89, 55]},
        "heat": {"box": [93, 0, 89, 55]},
        "legend": {"box": [0, 105, 20, 10], "label": False},
    }
    layout_data["page"]["height"] = 120
    layout_data.pop("mosaic")
    panels = pp.Layout(layout_data).panels
    assert [panels[k].label for k in ("roc_prc", "heat", "scatter_grid")] == ["a", "b", "c"]
    assert panels["legend"].label is None


def test_labels_id_mode_is_the_default(layout_data):
    panels = pp.Layout(layout_data).panels
    assert panels["A"].label == "a"  # the key, in the journal's case
