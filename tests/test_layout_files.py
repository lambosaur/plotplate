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
from plotplate.variants import find_layouts, selected

FIGURE = {
    "schema": 1,
    "name": "f",
    "area": {"width": 180, "height": 60},
    "mosaic": {"rows": ["AB"], "gap": 4},  # kept so that `resolve` has something to resolve
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
    return tmp_path


@pytest.mark.parametrize(
    ("command", "written"),
    [
        (["resolve"], "layout.resolved.yaml"),
        (["tidy"], "layout.tidied.yaml"),
        (["relabel"], "layout.relabeled.yaml"),
        (["merge", "A", "--as", "AB"], "layout.merged.yaml"),
    ],
)
def test_a_rewrite_goes_to_a_variant_not_over_the_input(figure, command, written):
    before = (figure / "layout.manual.yaml").read_text()
    assert main([command[0], str(figure), *command[1:]]) == 0
    assert (figure / written).exists()
    assert (figure / "layout.manual.yaml").read_text() == before  # the selected one is untouched
    assert (figure / "layout.yaml").is_symlink()  # ... and so is the link


def test_in_place_and_as_still_do_what_they_say(figure):
    assert main(["tidy", str(figure), "--as", "tight"]) == 0
    assert (figure / "layout.tight.yaml").exists()

    assert main(["resolve", str(figure), "--in-place"]) == 0
    assert "mosaic" not in load_yaml(figure / "layout.manual.yaml")  # wrote through the link
    assert (figure / "layout.yaml").is_symlink()


def test_running_the_same_command_twice_chains(figure):
    assert main(["merge", str(figure), "A", "--as", "P"]) == 0
    assert main(["merge", str(figure / "layout.merged.yaml"), "B", "--as", "Q"]) == 0
    assert list(load_yaml(figure / "layout.merged.yaml")["panels"]) == ["P", "Q"]


def test_the_viewer_lists_the_selected_layout_once(figure):
    from plotplate.view import Viewer

    assert set(find_layouts(figure)) == {"manual", "detected"}  # not the link
    assert selected(figure) == "manual"
    state = Viewer(figure).state()
    assert [v["key"] for v in state["variants"]] == ["detected", "manual"]
    assert state["selected"] == "manual" and state["active"] == "manual"


def test_a_folder_without_a_link_is_unchanged(tmp_path):
    dump_yaml(FIGURE, tmp_path / "layout.yaml")
    assert set(find_layouts(tmp_path)) == {"base"}
    assert selected(tmp_path) == "base"
    assert pp.Layout.load(tmp_path).file.name == "layout.yaml"


def test_a_new_layout_is_never_called_layout_yaml(tmp_path, capsys):
    assert main(["new", str(tmp_path), "--mosaic", "AB", "--width", "180", "--height", "60"]) == 0
    assert (tmp_path / "layout.new.yaml").exists() and not (tmp_path / "layout.yaml").exists()

    assert main(["new", str(tmp_path), "--mosaic", "AB", "--width", "180", "--height", "60"]) == 1
    assert "exists" in capsys.readouterr().err  # a second run does not replace the first
    assert main(["new", str(tmp_path), "--mosaic", "AB", "--width", "180", "--height", "60",
                 "--as", "draft"]) == 0  # fmt: skip
    assert (tmp_path / "layout.draft.yaml").exists()


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

    from plotplate.latex import write_figure_scaffold, write_figure_tex
    from plotplate.render import page_view, preview

    paths = preview(layout)
    page = page_view(layout, paper="a4")
    tex = write_figure_tex(layout)
    scaffold = write_figure_scaffold(layout)

    assert {p.parent for p in [*paths.values(), *page.values(), tex]} == {tmp_path / "output"}
    assert sorted(p.name for p in paths.values()) == ["figure.pdf", "figure.png", "figure.svg"]
    assert sorted(p.name for p in page.values()) == ["page.pdf", "page.png", "page.svg"]
    assert scaffold.parent == tmp_path  # the file you edit stays with the sources
    assert "\\input{output/f.tex}" in scaffold.read_text()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["f-figure.tex", "layout.yaml", "output"]


def test_the_layout_can_ask_for_the_page_view_on_every_build(tmp_path, capsys):
    dump_yaml({**FIGURE, "output_dir": "out", "preview": {"page": "a4"}}, tmp_path / "layout.yaml")
    layout = pp.Layout.load(tmp_path)
    for name in layout.panels:
        panel = layout.panel(name)
        fig, _axes = panel.subplots()
        panel.save(fig, formats=["pdf", "svg"])

    assert main(["build", str(tmp_path)]) == 0
    written = sorted(p.name for p in (tmp_path / "out").iterdir())
    assert "page.pdf" in written and "page.svg" in written and "figure.png" in written
