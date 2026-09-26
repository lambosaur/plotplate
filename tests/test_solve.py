import pytest

import plotplate as pp
from plotplate.cli import main
from plotplate.config import dump_yaml, load_yaml
from plotplate.solve import ConstraintError, solve_boxes, unconstrained

DEMO_RULES = {
    "defaults": {"gap": 4},
    "rules": [
        {"row": {"panels": ["A", "B"], "top": 0, "height": 55, "equal": True, "fill": True}},
        {"row": {"panels": ["C"], "height": 42, "fill": True}},
        {"row": {"panels": ["D", "E"], "height": 45, "equal": True, "fill": True}},
        {"gap": {"below": "A", "above": "C"}},
        {"gap": {"below": "C", "above": "D"}},
    ],
}
NAMES = ["A", "B", "C", "D", "E"]


def test_rows_reproduce_a_hand_written_layout():
    boxes, height = solve_boxes(NAMES, DEMO_RULES, 183, None)
    assert height == 150  # 55 + 4 + 42 + 4 + 45, solved
    assert boxes["A"].to_list(1) == [0.0, 0.0, 89.5, 55.0]
    assert boxes["B"].to_list(1) == [93.5, 0.0, 89.5, 55.0]
    assert boxes["C"].to_list(1) == [0.0, 59.0, 183.0, 42.0]
    assert boxes["E"].to_list(1) == [93.5, 105.0, 89.5, 45.0]


def test_a_narrower_page_keeps_the_gaps_and_shrinks_the_panels():
    boxes, _ = solve_boxes(NAMES, DEMO_RULES, 174, None)  # Cell full width
    assert boxes["A"].w == boxes["B"].w == 85.0
    assert round(boxes["B"].left - boxes["A"].right, 6) == 4.0  # the gap did not scale


def test_primitives_align_equal_size_aspect_and_pin():
    rules = {
        "rules": [
            {"pin": {"panel": "A", "left": 0, "top": 0}},
            {"size": {"panel": "A", "width": 60, "height": 40}},
            {"align": {"edge": "top", "of": ["A", "B"]}},
            {"gap": {"after": "A", "before": "B", "value": 5}},
            {"equal": {"what": "height", "of": ["A", "B"]}},
            {"aspect": {"panel": "B", "ratio": 1.5}},
        ]
    }
    boxes, _ = solve_boxes(["A", "B"], rules, 200, 100)
    assert boxes["B"].left == 65.0 and boxes["B"].top == 0.0
    assert boxes["B"].h == 40.0 and boxes["B"].w == 60.0  # 1.5 * 40


def test_explicit_boxes_pin_the_rest():
    rules = {"rules": [{"gap": {"after": "A", "before": "B", "value": 4}},
                       {"align": {"edge": "top", "of": ["A", "B"]}},
                       {"pin": {"panel": "B", "right": "page"}}]}  # fmt: skip
    pinned = {"A": pp.Rect(0, 0, 80, 50)}
    boxes, _ = solve_boxes(["A", "B"], rules, 183, 60, pinned)
    assert boxes["A"].to_list(1) == [0.0, 0.0, 80.0, 50.0]
    assert boxes["B"].left == 84.0 and boxes["B"].right == 183.0


def test_conflicting_and_wrong_rules_are_reported():
    conflict = {
        "rules": [{"size": {"panel": "A", "width": 100}}, {"size": {"panel": "A", "width": 120}}]
    }
    with pytest.raises(ConstraintError, match="conflict"):
        solve_boxes(["A"], conflict, 183, 60)
    with pytest.raises(ConstraintError, match="unknown panel"):
        solve_boxes(["A"], {"rules": [{"pin": {"panel": "Z", "left": 0}}]}, 183, 60)
    with pytest.raises(ConstraintError, match="unknown rule"):
        solve_boxes(["A"], {"rules": [{"wobble": {}}]}, 183, 60)
    with pytest.raises(ConstraintError, match="unknown keys"):
        solve_boxes(["A"], {"rules": [{"row": {"panels": ["A"], "wat": 1}}]}, 183, 60)


def test_under_constrained_panels_are_named():
    rules = {"rules": [{"pin": {"panel": "A", "left": 0, "top": 0}}]}
    boxes, _ = solve_boxes(["A", "B"], rules, 183, 60)
    assert set(unconstrained(boxes, 183, 60)) == {"A", "B"}


@pytest.fixture
def constrained_layout(tmp_path):
    data = {
        "schema": 1,
        "journal": "nature",
        "area": {"width": "double", "height": "solve"},
        "constraints": DEMO_RULES,
        "panels": {name: {} for name in NAMES},
    }
    dump_yaml(data, tmp_path / "layout.yaml")
    return tmp_path / "layout.yaml"


def test_layout_uses_the_solver_and_reports_it(constrained_layout):
    layout = pp.Layout.load(constrained_layout)
    assert layout.height == 150
    assert layout.panels["C"].box.to_list(1) == [0.0, 59.0, 183.0, 42.0]
    assert [i.code for i in layout.validate()] == []


def test_resolve_freezes_the_solution(constrained_layout, tmp_path):
    out = tmp_path / "frozen.yaml"
    assert main(["resolve", str(constrained_layout), "-o", str(out)]) == 0
    data = load_yaml(out)
    assert "constraints" not in data
    assert data["area"]["height"] == 150
    assert data["panels"]["B"]["box"] == [93.5, 0.0, 89.5, 55.0]
    assert pp.Layout(data).panels["B"].box.to_list(1) == [93.5, 0.0, 89.5, 55.0]


def test_validate_warns_when_the_rules_are_too_loose(tmp_path):
    data = {
        "schema": 1,
        "area": {"width": 183, "height": 100},
        "constraints": {"rules": [{"pin": {"panel": "A", "left": 0, "top": 0}}]},
        "panels": {"A": {}, "B": {}},
    }
    codes = [i.code for i in pp.Layout(data).validate()]
    assert "under-constrained" in codes
