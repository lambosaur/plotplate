import matplotlib
import pytest

matplotlib.use("Agg")

import plotplate as pp
from plotplate.align import check_rules, near_misses, read_features
from plotplate.cli import main
from plotplate.config import dump_yaml


@pytest.fixture
def drawn(tmp_path):
    """Two panels: their axes share a bottom edge, and their left edges differ by 0.5 mm."""
    data = {
        "schema": 1,
        "page": {"width": 120, "height": 60},
        "panels": {
            "A": {"box": [0, 0, 58, 60], "axes": {"main": {"box": [10, 5, 44, 40]}}},
            "B": {"box": [62, 0, 58, 60], "axes": {"main": {"box": [72.5, 5, 44, 40]}}},
        },
    }
    dump_yaml(data, tmp_path / "layout.yaml")
    layout = pp.Layout.load(tmp_path / "layout.yaml")
    for name in ("A", "B"):
        panel = layout.panel(name)
        fig = panel.figure()
        ax = panel.axes(fig, "main")
        ax.plot([0, 1], [0, 1])
        panel.mark("origin", ax=ax, x=0, y=0)
        panel.save(fig, formats=["pdf"])
    return layout


def test_geometry_is_recorded_in_page_millimetres(drawn):
    features, issues = read_features(drawn)
    assert not [i for i in issues if i.level != "info"]
    assert features["A.main"].values == {"left": 10.0, "right": 54.0, "top": 5.0, "bottom": 45.0}
    assert features["B.main"].values["left"] == 72.5
    assert set(features["A.main"].spines) >= {"left", "bottom"}
    # data (0, 0) sits inside the axes, away from the corner, because of matplotlib's margins
    origin = features["A.origin"].values
    assert 10.0 < origin["x"] < 14.0 and 41.0 < origin["y"] < 45.0


def test_rules_pass_and_fail_with_the_deviation(drawn):
    features, _ = read_features(drawn)
    ok = check_rules(features, [{"match": "bottom", "of": ["A.main", "B.main"]}], 0.2)
    assert [i for i in ok if i.level == "error"] == []
    bad = check_rules(features, [{"match": "left", "of": ["A.main", "B.main"]}], 0.2)
    assert bad[0].code == "align-mismatch" and "62.50" in bad[0].message


def test_near_misses_report_almost_aligned_edges(drawn):
    features, _ = read_features(drawn)
    codes = {i.code for i in near_misses(features, tolerance=1.0)}
    assert "align-near" not in codes  # A.left 10 vs B.left 72.5: far apart, not a near miss
    shifted = dict(features)
    shifted["B.main"].values["top"] = 5.4
    messages = [i.message for i in near_misses(shifted, tolerance=1.0) if i.code == "align-near"]
    assert any("top" in m and "0.40 mm" in m for m in messages)


def test_cli_align_uses_alignment_file(drawn, tmp_path):
    dump_yaml(
        {"tolerance": 0.2, "rules": [{"match": "left", "of": ["A.main", "B.main"]}]},
        tmp_path / "alignment.yaml",
    )
    assert main(["align", str(drawn.path)]) == 1  # the file next to the layout is picked up
    dump_yaml({"tolerance": 0.2, "rules": [{"match": "bottom", "of": ["A.main", "B.main"]}]},
              tmp_path / "alignment.yaml")  # fmt: skip
    assert main(["align", str(drawn.path)]) == 0
    assert main(["preview", str(drawn.path), "--rules"]) == 0
