import copy

import pytest

import plotplate as pp
from plotplate.cli import main
from plotplate.config import dump_yaml, load_yaml
from plotplate.revise import diff_layouts


@pytest.fixture
def before(tmp_path):
    data = {
        "schema": 1,
        "labels": "auto",
        "page": {"width": 180, "height": 100},
        "panels": {
            "roc": {"box": [0, 0, 88, 48], "axes": {"main": {"box": [10, 4, 74, 38]}}},
            "heat": {"box": [92, 0, 88, 48]},
            "scatter": {"box": [0, 52, 88, 48]},
            "scaling": {"box": [92, 52, 88, 48]},
        },
    }
    dump_yaml(data, tmp_path / "old.yaml")
    return tmp_path / "old.yaml", data


def _changes(before_path, data):
    dump_yaml(data, before_path.parent / "new.yaml")
    old = pp.Layout.load(before_path)
    new = pp.Layout.load(before_path.parent / "new.yaml")
    return {c.change: c for c in diff_layouts(old, new)}, old, new


def test_detects_move_resize_and_axes_change(before):
    path, data = before
    new = copy.deepcopy(data)
    new["panels"]["roc"]["box"] = [0, 0, 60, 48]
    new["panels"]["roc"]["axes"]["main"]["box"] = [10, 4, 46, 38]
    changes, _, _ = _changes(path, new)
    assert "moved" in changes
    assert "resized" in changes["moved"].detail and "axes main" in changes["moved"].detail


def test_detects_merge_split_add_remove(before):
    path, data = before
    new = copy.deepcopy(data)
    new["panels"]["curves"] = {"box": [0, 0, 180, 48]}  # roc + heat merged
    del new["panels"]["roc"], new["panels"]["heat"]
    del new["panels"]["scaling"]  # removed
    new["panels"]["scatter"]["box"] = [0, 52, 43, 48]  # split into two
    new["panels"]["scatter_b"] = {"box": [45, 52, 43, 48]}
    new["panels"]["new_panel"] = {"box": [140, 52, 40, 20]}  # elsewhere: a real addition
    changes, _, _ = _changes(path, new)
    assert sorted(changes["merged"].old) == ["heat", "roc"]
    assert changes["merged"].new == ["curves"]
    assert sorted(changes["split"].new) == ["scatter", "scatter_b"]
    assert changes["removed"].old == ["scaling"]
    assert changes["added"].new == ["new_panel"]


def test_same_box_with_a_new_key_is_a_rename(before):
    path, data = before
    new = copy.deepcopy(data)
    new["panels"]["performance"] = new["panels"].pop("scaling")  # same box, new key
    changes, _, _ = _changes(path, new)
    assert changes["relabelled"].old == ["scaling"]
    assert changes["relabelled"].new == ["performance"]


def test_mapping_overrides_geometry(before, tmp_path):
    path, data = before
    new = copy.deepcopy(data)
    new["panels"]["renamed"] = new["panels"].pop("roc")
    dump_yaml(new, tmp_path / "new.yaml")
    dump_yaml({"mapping": {"roc": "renamed"}}, tmp_path / "map.yaml")
    assert (
        main(
            [
                "diff",
                str(path),
                str(tmp_path / "new.yaml"),
                "-o",
                str(tmp_path / "plan.yaml"),
                "--mapping",
                str(tmp_path / "map.yaml"),
                "--wireframe",
                str(tmp_path / "diff.png"),
            ]
        )
        == 0
    )
    plan = load_yaml(tmp_path / "plan.yaml")
    assert plan["summary"]["relabelled"] == 1
    assert plan["changes"][0]["old"] == ["roc"] and plan["changes"][0]["new"] == ["renamed"]
    assert (tmp_path / "diff.png").exists()


def test_relabel_writes_explicit_letters(before, tmp_path):
    path, _ = before
    assert main(["relabel", str(path), "-o", str(tmp_path / "labelled.yaml")]) == 0
    data = load_yaml(tmp_path / "labelled.yaml")
    assert data["labels"] == "id"
    assert [data["panels"][k]["label"]["text"] for k in ("roc", "heat")] == ["A", "B"]
