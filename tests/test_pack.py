"""The optimizer: recover the grid, spend the white space, respect the limits."""

import json

import pytest

import plotplate as pp
from plotplate.cli import main
from plotplate.config import dump_yaml, load_yaml
from plotplate.geometry import Rect
from plotplate.pack import PackError, Target, optimize, read_grid
from plotplate.variants import find_layouts

RAGGED = {
    "schema": 1,
    "name": "ragged",
    "page": {"paper": "a4", "margins": 13.5},
    "area": {"width": 183, "height": 140},
    "panels": {
        # Two rows, uneven gutters (12 and 10 mm), a ragged right edge, a short last row.
        "A": {"box": [0, 0, 70, 48], "axes": {"main": {"box": [11, 4, 56, 40]}}},
        "B": {"box": [82, 0, 60, 44], "axes": {"main": {"box": [92, 3, 46, 37]}}},
        "C": {"box": [0, 58, 100, 40], "axes": {"main": {"box": [12, 62, 84, 32]}}},
        "D": {"box": [110, 58, 50, 40], "axes": {"main": {"box": [120, 62, 36, 32]}}},
    },
}


@pytest.fixture
def ragged(tmp_path):
    dump_yaml(RAGGED, tmp_path / "layout.detected.yaml")
    return pp.Layout.load(tmp_path / "layout.detected.yaml")


def _boxes(data):
    return {name: Rect.from_list(panel["box"]) for name, panel in data["panels"].items()}


def test_read_grid_finds_rows_columns_and_spanning_panels():
    grid = read_grid(
        {
            "A": Rect(0, 0, 40, 30),
            "B": Rect(44, 0, 40, 30),
            "C": Rect(0, 34, 84, 30),  # spans both columns
        }
    )
    assert grid.xs == [0.0, 40.0, 44.0, 84.0]
    assert grid.span("C", "x") == (0, 3)
    # C spans the gutter between A and B, and it is still a gutter: C's width includes it.
    assert [gutter for _size, gutter in grid.strips("x")] == [False, True, False]
    assert [gutter for _size, gutter in grid.strips("y")] == [False, True, False]


def test_read_grid_calls_an_inset_an_inset():
    grid = read_grid({"A": Rect(0, 0, 90, 60), "zoom": Rect(55, 12, 30, 22)})
    assert grid.insets == {"zoom": "A"}
    assert list(grid.spans) == ["A"]


def test_read_grid_refuses_an_arrangement_that_is_not_a_grid():
    pinwheel = {
        "B": Rect(95, 0, 55, 30),
        "D": Rect(124, 27, 26, 30),  # overlaps B by 3 mm, and is not inside it
    }
    with pytest.raises(PackError, match="overlap without being nested"):
        read_grid(pinwheel)


def test_optimize_normalises_the_gutters_and_fills_the_width(ragged):
    data, report = optimize(ragged, Target(gap=4.0, stretch=1.3, shrink=1.0))
    boxes = _boxes(data)
    assert report.gutters[1] == (4.0, 4.0)  # every gutter is the asked-for gap
    assert report.occupancy[1] > report.occupancy[0] + 0.1  # and the space went to the panels
    assert max(box.right for box in boxes.values()) == pytest.approx(183, abs=0.01)
    assert data["area"]["width"] == 183.0
    for name in boxes:
        fx, fy = report.factors(name)
        assert 1.0 <= fx <= 1.3 + 1e-6 and 1.0 <= fy <= 1.3 + 1e-6
    assert not pp.Layout(data, ragged.path).validate()  # no overlap, nothing outside the area


def test_axes_keep_their_margins_when_the_panel_grows(ragged):
    data, _ = optimize(ragged, Target(gap=4.0, stretch=1.3))
    panel = pp.Layout(data, ragged.path).panels["A"]
    axes = panel.axes["main"].region
    # The 11 mm that held the tick labels is still 11 mm; the plot itself took the extra space.
    assert axes.left - panel.box.left == pytest.approx(11, abs=0.05)
    assert panel.box.right - axes.right == pytest.approx(70 - 67, abs=0.05)
    assert axes.w > 56


def test_no_distortion_allowed_keeps_the_panels_and_narrows_the_figure(ragged):
    """With stretch 1 the panels cannot grow, so the gutters shrink and the figure follows."""
    _data, report = optimize(ragged, Target(gap=4.0, stretch=1.0, shrink=1.0))
    for name in report.after:
        assert report.factors(name) == pytest.approx((1.0, 1.0), abs=0.01)
    assert report.width < 183  # it no longer fills the column, and the report says why
    assert "size-bent" in [note.code for note in report.notes]
    assert any("could not keep its width" in note.message for note in report.notes)


def test_a_frozen_panel_keeps_its_size(ragged):
    _data, report = optimize(ragged, Target(gap=4.0, stretch=1.4, freeze=("B",)))
    assert report.factors("B") == pytest.approx((1.0, 1.0), abs=0.01)
    assert report.factors("A")[0] > 1.0


def test_a_target_that_cannot_be_reached_says_what_would_be_needed(ragged):
    with pytest.raises(PackError, match=r"grow 2\.\d+x to fill 400"):
        optimize(ragged, Target(gap=4.0, stretch=1.2, width=400.0))


def test_keep_aspect_holds_the_ratio(ragged):
    _data, report = optimize(ragged, Target(gap=4.0, stretch=1.4, keep_aspect=("D",)))
    before, after = report.before["D"], report.after["D"]
    assert after.w / after.h == pytest.approx(before.w / before.h, rel=1e-3)


def test_cli_writes_the_optimized_variant_next_to_the_input(ragged, tmp_path):
    assert main(["optimize", str(tmp_path), "--gap", "4", "--max-stretch", "1.3"]) == 0
    written = tmp_path / "layout.optimized.yaml"
    assert written.exists()
    assert load_yaml(written)["area"]["width"] == 183.0
    assert "constraints" not in load_yaml(written)


def test_cli_dry_run_writes_nothing(ragged, tmp_path):
    assert main(["optimize", str(ragged.path), "--dry-run"]) == 0
    assert not (tmp_path / "layout.optimized.yaml").exists()


def test_the_stretch_is_chosen_when_it_is_not_given(ragged):
    """One run decides: the smallest limit that fills every row, and it says which."""
    _data, report = optimize(ragged, Target(gap=4.0))
    assert report.automatic and 1.0 < report.stretch <= 2.0
    assert report.width == pytest.approx(183, abs=0.01)  # the figure kept its width
    assert not report.notes  # nothing left to say: no row is short, nothing had to give
    assert report.occupancy[1] > 0.85

    tighter = optimize(ragged, Target(gap=4.0, stretch=report.stretch - 0.1))[1]
    assert tighter.notes, "a smaller limit leaves something on the table, and says so"
    slack = next(note for note in tighter.notes if note.code == "row-slack")
    assert slack.as_dict()["spare_mm"] > 0  # a code and numbers, not only a sentence
    assert slack.as_dict()["panels"] and slack.as_dict()["fills_at"] > tighter.stretch


def test_a_limit_that_cannot_work_names_one_that_can(ragged):
    """A width you asked for, with a limit that cannot reach it: the message has the number."""
    with pytest.raises(PackError, match=r"--max-stretch 1\.\d+ works"):
        optimize(ragged, Target(gap=4.0, stretch=1.0, width=200.0))


def test_per_panel_limits_come_from_the_layout_file(ragged, tmp_path):
    data = {
        **RAGGED,
        "optimize": {"gap": 4, "panels": {"B": {"freeze": True}, "A": {"stretch": 1.05}}},
    }
    dump_yaml(data, tmp_path / "layout.yaml")
    assert main(["optimize", str(tmp_path), "--dry-run"]) == 0

    layout = pp.Layout.load(tmp_path / "layout.yaml")
    _out, report = optimize(layout, Target(gap=4.0, freeze=("B",), limits={"A": 1.05}))
    assert report.factors("B") == pytest.approx((1.0, 1.0), abs=0.01)
    assert report.factors("A")[0] <= 1.05 + 1e-6


def test_json_output_is_machine_readable(ragged, capsys):
    assert main(["optimize", str(ragged.path), "--dry-run", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["output"] is None and payload["stretch_chosen_automatically"] is True
    assert set(payload["panels"]) == {"A", "B", "C", "D"}
    assert payload["panels"]["A"]["factor"][0] >= 1.0
    assert payload["occupancy"]["after"] > payload["occupancy"]["before"]


def test_cli_names_the_variant_it_writes(ragged, tmp_path):
    """`--as tight` writes layout.tight.yaml, so several attempts sit side by side."""
    assert main(["optimize", str(tmp_path), "--as", "tight", "--max-stretch", "1.3"]) == 0
    assert (tmp_path / "layout.tight.yaml").exists()
    assert "tight" in find_layouts(tmp_path)


def test_cli_json_reports_notes_as_records(ragged, tmp_path, capsys):
    """An agent reads the codes; a person reads the same sentence in the table."""
    assert main(["optimize", str(tmp_path), "--max-stretch", "1.02", "--json", "--dry-run"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["notes"] and all({"code", "message"} <= set(n) for n in report["notes"])
    assert any(n["code"] == "row-slack" and n["spare_mm"] > 0 for n in report["notes"])


def test_bring_inside_puts_a_stray_panel_back(ragged):
    """A box dragged over the edge is a mistake, not an arrangement: it is put back first."""
    from plotplate.pack import bring_inside

    fixed = bring_inside(
        {
            "A": Rect(-10, -5, 70, 48),  # pulled up and to the left
            "B": Rect(170, 0, 40, 48),  # pushed off the right edge
            "C": Rect(0, 0, 200, 300),  # larger than the figure itself
        },
        183.0,
        140.0,
    )
    assert fixed["A"] == Rect(0, 0, 70, 48)  # moved, same size
    assert fixed["B"] == Rect(143, 0, 40, 48)
    assert fixed["C"] == Rect(0, 0, 183, 140)  # only this one had to shrink


def test_the_optimize_section_is_read_once_for_every_caller(tmp_path):
    """The command, the viewer and an agent must read the same intent from the same place."""
    from plotplate.pack import Target

    data = {
        **RAGGED,
        "optimize": {
            "gap": 3,
            "max_stretch": 1.3,
            "height": "keep",
            "panels": {"A": {"freeze": True}, "B": {"stretch": 1.05}, "C": {"keep_aspect": True}},
        },
    }
    dump_yaml(data, tmp_path / "layout.yaml")
    target = Target.from_layout(pp.Layout.load(tmp_path / "layout.yaml"))
    assert (target.gap, target.stretch, target.height) == (3.0, 1.3, 140.0)
    assert (target.freeze, target.keep_aspect, target.limits) == (("A",), ("C",), {"B": 1.05})


BAND = {
    "schema": 1,
    "name": "band",
    "area": {"width": 183, "height": 120},
    "panels": {
        "A": {"box": [0, 0, 60, 50]},
        "B": {"box": [120, 0, 63, 50]},
        "C": {"box": [0, 60, 183, 50]},  # already spans the whole width, guides included
    },
}


def test_page_guides_stop_the_panels_growing_across_them():
    """Two guides with a blank band between them keep it blank: they are hard stops."""
    free = optimize(pp.Layout(dict(BAND)), Target(gap=4.0))[1]
    assert free.after["A"].right > 70 and free.after["B"].left < 110  # without them, it fills

    held, report = optimize(
        pp.Layout({**BAND, "page_guides": {"x": [70, 110], "y": []}}), Target(gap=4.0)
    )
    assert report.after["A"].right == pytest.approx(70, abs=0.01)
    assert report.after["B"].left == pytest.approx(110, abs=0.01)
    assert report.after["C"].w == pytest.approx(183, abs=0.01)  # what already spanned still does
    assert [note.code for note in report.notes] == ["guides-held"]
    assert held["page_guides"] == {"x": [70, 110], "y": []}  # and they are kept in the result


def test_the_band_between_two_guides_is_not_treated_as_a_gutter():
    """Held-open space is not something a bigger limit could fill, so no note says it is."""
    _data, report = optimize(
        pp.Layout({**BAND, "page_guides": {"x": [70, 110], "y": []}}), Target(gap=4.0)
    )
    assert report.stretch < 2.0  # the automatic search stops instead of chasing the band
    assert not [note for note in report.notes if note.code == "row-slack"]


def test_a_guide_on_or_outside_the_figure_edge_is_not_a_constraint():
    """A margin guide, or one left behind by a narrower target, stops nothing new."""
    _data, report = optimize(
        pp.Layout({**BAND, "page_guides": {"x": [0, 183, 260], "y": [0, 247]}}),
        Target(gap=4.0, width=160.0),
    )
    assert report.width == pytest.approx(160, abs=0.01)
    assert not [note for note in report.notes if note.code == "guides-held"]


def test_a_horizontal_guide_holds_a_row_apart():
    _data, report = optimize(
        pp.Layout({**BAND, "page_guides": {"x": [], "y": [56]}}), Target(gap=4.0, height=120.0)
    )
    assert report.after["A"].bottom <= 56.01 and report.after["C"].top >= 55.99
