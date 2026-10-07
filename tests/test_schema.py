"""The layout file is checked against the one table that lists its keys."""

import pytest

import plotplate as pp
from plotplate.cli import main
from plotplate.config import dump_yaml

FIGURE = {
    "schema": 1,
    "name": "f",
    "area": {"width": 100, "height": 50},
    "gutter": 4,
    "panels": {"A": {"box": [0, 0, 48, 50]}, "B": {"box": [52, 0, 48, 50]}},
}


def _refused(patch):
    """The message a layout gives when it cannot be read, or "" when it loads."""
    try:
        pp.Layout({**FIGURE, **patch})
    except ValueError as exc:
        return str(exc)
    return ""


@pytest.mark.parametrize(
    "wanted",
    [
        'gutters: unknown key; did you mean "gutter"?',
        'area.widht: unknown key; did you mean "width"?',
        "optimize.max_strech: unknown key",
        'style.fonts: unknown key; did you mean "font"?',
        'code-dir: unknown key; did you mean "code_dir"?',
        'panels.A.axes.roc.lft: unknown key; did you mean "left"?',
    ],
)
def test_a_key_plotplate_cannot_read_is_refused_and_the_right_one_is_named(wanted):
    """Silence is the worst answer: a key that does nothing has to say so, with a suggestion."""
    patches = {
        "gutters": {"gutters": 4},
        "area.widht": {"area": {"widht": 100, "height": 50}},
        "optimize.max_strech": {"optimize": {"max_strech": 1.2}},
        "style.fonts": {"style": {"fonts": {}}},
        "code-dir": {"code-dir": "code"},
        "panels.A.axes.roc.lft": {
            "panels": {"A": {"box": [0, 0, 48, 50], "axes": {"roc": {"lft": 2}}}}
        },
    }
    patch = patches[wanted.split(":")[0]]
    assert wanted in _refused(patch)


def test_a_value_of_the_wrong_type_is_refused():
    assert "gutter: expected a number or a list, got 'wide'" in _refused({"gutter": "wide"})


def test_a_value_outside_a_closed_set_is_refused():
    assert "not one of id, auto, none" in _refused({"labels": "letters"})


def test_free_text_has_somewhere_to_go():
    assert _refused({"notes": "why this figure is shaped like this"}) == ""


def test_the_command_line_says_it_in_one_line(tmp_path, capsys):
    """Whatever command is run, a broken file is a message and an exit code, not a traceback."""
    dump_yaml({**FIGURE, "gutters": 4}, tmp_path / "layout.yaml")
    assert main(["check", str(tmp_path)]) == 1
    assert 'did you mean "gutter"?' in capsys.readouterr().err


def test_the_old_gap_keys_still_work_and_say_where_they_went(tmp_path, capsys):
    """A layout written before `gutter:` existed keeps its geometry, and is told what to rename."""
    old = {
        "schema": 1,
        "name": "f",
        "area": {"width": 100, "height": 50},
        "mosaic": {"rows": ["AB"], "gap": [6, 6]},
        "optimize": {"gap": 6},
    }
    layout = pp.Layout(old)
    assert layout.gutter == (6.0, 6.0)  # read, not ignored
    assert layout.panels["B"].box.left == 53.0  # ... and the boxes are where they always were

    dump_yaml(old, tmp_path / "layout.yaml")
    assert main(["check", str(tmp_path)]) == 0  # a rename to do, not an error
    out = capsys.readouterr().out
    assert "mosaic.gap: renamed to gutter" in out and "optimize.gap: renamed to gutter" in out


def test_one_gutter_is_used_by_the_mosaic_and_by_the_optimizer(tmp_path):
    """The number is declared once, and both the boxes and the re-packing read it."""
    from plotplate.pack import Target

    data = {**FIGURE, "gutter": 10, "mosaic": {"rows": ["AB"]}, "panels": {}}
    layout = pp.Layout(data)
    assert layout.panels["A"].box.w == 45.0  # (100 - 10) / 2
    assert Target.from_layout(layout).gap == 10.0
