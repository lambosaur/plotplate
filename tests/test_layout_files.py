"""Where plotplate writes: never over the layout a figure folder has selected.

A figure folder keeps several layouts (`layout.<qualifier>.yaml`) and chooses between them,
possibly with `layout.yaml` as a symlink. No command may overwrite that choice without being
told to, and every build output goes to one folder, so one folder can be ignored by git and one
folder promoted.
"""

import os

import pytest

import plotplate as pp
from plotplate.cli import main
from plotplate.config import dump_yaml, load_yaml
from plotplate.variants import find_layouts

FIGURE_TEXT = ""  # filled by the fixture: the untouched text of layout.manual.yaml

FIGURE = {
    "schema": 1,
    "name": "f",
    "area": {"width": 180, "height": 60},
    "gutter": 4,
    "mosaic": {"rows": ["AB"]},  # kept so that `resolve` has something to resolve
    "panels": {
        "A": {"box": [0, 0, 88, 60], "margins": [10, 4, 2, 10]},
        "B": {"box": [92, 0, 88, 60], "margins": [10, 4, 2, 10]},
    },
}


@pytest.fixture
def figure(tmp_path):
    """A folder with two layouts and layout.yaml as a symlink to one of them."""
    dump_yaml(FIGURE, tmp_path / "layout.manual.yaml")
    dump_yaml({**FIGURE, "name": "detected"}, tmp_path / "layout.detected.yaml")
    os.symlink("layout.manual.yaml", tmp_path / "layout.yaml")
    global FIGURE_TEXT
    FIGURE_TEXT = (tmp_path / "layout.manual.yaml").read_text()
    return tmp_path


@pytest.mark.parametrize(
    "command",
    [["resolve"], ["merge", "A", "--as", "AB"]],
)
def test_the_layout_in_use_is_never_overwritten(figure, command, capsys):
    """Given the folder (so, layout.yaml), a rewrite refuses and says how to name an output."""
    before = (figure / "layout.manual.yaml").read_text()
    assert main([command[0], str(figure), *command[1:]]) == 1
    message = capsys.readouterr().err
    assert "does not overwrite it" in message and "-o " in message
    assert (figure / "layout.manual.yaml").read_text() == before
    assert (figure / "layout.yaml").is_symlink()


@pytest.mark.parametrize(
    "command",
    [["resolve"], ["merge", "A", "--as", "AB"]],
)
def test_a_draft_is_rewritten_in_place(figure, command):
    """A layout.<something>.yaml is a draft: the command that was asked for rewrites it."""
    draft = figure / "layout.detected.yaml"
    before = draft.read_text()
    assert main([command[0], str(draft), *command[1:]]) == 0
    assert draft.read_text() != before
    assert (figure / "layout.manual.yaml").read_text() == FIGURE_TEXT  # nothing else moved


def test_an_output_can_always_be_named(figure):
    assert main(["merge", str(figure), "A", "B", "--as", "AB",
                 "-o", str(figure / "layout.tight.yaml")]) == 0  # fmt: skip
    assert (figure / "layout.tight.yaml").exists()
    assert main(["resolve", str(figure), "-o", str(figure / "layout.yaml")]) == 0
    assert "mosaic" not in load_yaml(figure / "layout.manual.yaml")  # wrote through the link
    assert (figure / "layout.yaml").is_symlink()


def test_one_file_is_listed_once_however_many_names_it_has(figure):
    """layout.yaml linked to layout.manual.yaml is one layout, not two."""
    from plotplate.view import Viewer

    assert set(find_layouts(figure)) == {"manual", "detected"}
    assert [v["key"] for v in Viewer(figure).state()["variants"]] == ["detected", "manual"]


def test_a_folder_without_a_link_is_unchanged(tmp_path):
    dump_yaml(FIGURE, tmp_path / "layout.yaml")
    assert set(find_layouts(tmp_path)) == {"base"}
    assert pp.Layout.load(tmp_path).file.name == "layout.yaml"


def test_every_draft_of_an_existing_figure_has_the_same_name(tmp_path, capsys):
    """Whatever was read, the draft is layout.detected.yaml: one name to remember."""
    from plotplate.render import wireframe

    dump_yaml(FIGURE, tmp_path / "source.yaml")
    wireframe(pp.Layout.load(tmp_path / "source.yaml"), tmp_path / "shot.png")

    assert main(["detect", str(tmp_path / "shot.png"), "--width", "180"]) == 0
    assert (tmp_path / "layout.detected.yaml").exists()

    assert main(["detect", str(tmp_path / "shot.png"), "--width", "180"]) == 1
    assert "exists" in capsys.readouterr().err  # a second draft does not replace the first
    assert main(["detect", str(tmp_path / "shot.png"), "--width", "180", "--force"]) == 0


def test_output_dir_keeps_the_figure_folder_to_its_sources(tmp_path):
    """With output_dir set, a build writes nothing beside the layout but the file you edit."""
    dump_yaml({**FIGURE, "output_dir": "output"}, tmp_path / "layout.yaml")
    layout = pp.Layout.load(tmp_path)
    for name in layout.panels:
        panel = layout.panel(name)
        fig, axes = panel.subplots()
        for ax in axes.values():
            for one in getattr(ax, "flat", [ax]):
                one.plot([0, 1], [1, 0])
        panel.save(fig, formats=["pdf", "svg"])

    assert layout.panels_dir == tmp_path / "output" / "panels"
    assert (layout.panels_dir / "A.pdf").exists()

    assert main(["build", str(tmp_path)]) == 0
    written = sorted(p.name for p in (tmp_path / "output").iterdir())
    assert written == ["f.tex", "page.pdf", "page.png", "page.svg", "panels"]
    scaffold = tmp_path / "f-figure.tex"
    assert scaffold.exists()  # the file you edit stays with the sources
    assert "\\input{output/f.tex}" in scaffold.read_text()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["f-figure.tex", "layout.yaml", "output"]


def test_a_layout_that_declares_no_sheet_still_gets_its_page_view(tmp_path, capsys):
    """Nothing in the file says `page:`, and a4 is the sheet a figure is checked against."""
    dump_yaml({**FIGURE, "output_dir": "out"}, tmp_path / "layout.yaml")
    layout = pp.Layout.load(tmp_path)
    for name in layout.panels:
        panel = layout.panel(name)
        fig, _axes = panel.subplots()
        panel.save(fig, formats=["pdf", "svg"])

    assert main(["build", str(tmp_path)]) == 0
    written = sorted(p.name for p in (tmp_path / "out").iterdir())
    assert "page.pdf" in written and "page.svg" in written and "page.png" in written


def test_the_upload_folder_lands_in_the_output_folder_by_default(tmp_path, capsys):
    """One folder holds everything a build makes, the Overleaf upload included."""
    dump_yaml({**FIGURE, "output_dir": "output"}, tmp_path / "layout.yaml")
    layout = pp.Layout.load(tmp_path)
    for name in layout.panels:
        panel = layout.panel(name)
        fig, _axes = panel.subplots()
        panel.save(fig, formats=["pdf"])

    assert main(["latex", str(tmp_path)]) == 0
    upload = tmp_path / "output" / "overleaf"
    assert sorted(p.name for p in upload.iterdir()) == ["A.pdf", "B.pdf", "f-figure.tex", "f.tex"]
    assert "output/overleaf" in capsys.readouterr().out

    elsewhere = tmp_path / "final"  # ... and a destination can still be named
    assert main(["latex", str(tmp_path), str(elsewhere)]) == 0
    assert (elsewhere / "f.tex").exists()
