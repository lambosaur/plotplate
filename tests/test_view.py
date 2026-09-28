import json
import threading
import urllib.error
import urllib.request

import matplotlib
import pytest

matplotlib.use("Agg")

import plotplate as pp
from plotplate.view import Viewer, make_server


@pytest.fixture
def served(layout):
    """A drawn figure served by the viewer; yields (base url, layout)."""
    for name in layout.panels:
        panel = layout.panel(name)
        fig, axes = panel.subplots()
        for ax in axes.values():
            for one in getattr(ax, "flat", [ax]):
                one.plot([0, 1], [1, 0])
                one.set_xlabel("x")
        panel.save(fig, formats=["pdf"])
    server = make_server(layout.path, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/", layout
    server.shutdown()
    server.server_close()


def fetch(url):
    return urllib.request.urlopen(url, timeout=10).read()


def test_page_state_and_image(served):
    base, layout = served
    page = fetch(base).decode()
    assert '<svg id="paper"' in page and "__TITLE__" not in page  # the template rendered

    state = json.loads(fetch(base + "state.json"))
    assert state["width"] == layout.width and state["height"] == layout.height
    assert [p["name"] for p in state["panels"]] == list(layout.panels)
    assert {"roc", "grid"} <= {a["name"] for a in state["panels"][0]["axes"]}
    assert state["guides"]["y"]["bottom"] == 50
    assert any(f["kind"] == "axes" for f in state["features"])  # measured geometry is there

    image = fetch(base + "image/figure.png")
    assert image[:4] == b"\x89PNG" and len(image) > 1000


def test_stamp_changes_when_a_panel_is_redrawn(served, tmp_path):
    base, layout = served
    first = json.loads(fetch(base + "state.json"))["stamp"]
    (layout.panels_dir / "A.json").write_text("{}")  # as a rebuild would
    assert json.loads(fetch(base + "state.json"))["stamp"] != first


def test_unknown_route_is_404(served):
    base, _ = served
    with pytest.raises(urllib.error.HTTPError) as caught:
        fetch(base + "nope")
    assert caught.value.code == 404


def test_viewer_reads_the_files_on_every_call(layout):
    """Editing the layout while the server runs changes what it serves."""
    from plotplate.config import dump_yaml

    viewer = Viewer(layout.path)
    before = viewer.state()["height"]
    data = viewer.layout().raw
    data["area"]["height"] = before + 10
    dump_yaml(data, layout.path)
    assert viewer.state()["height"] == before + 10


def test_every_layout_variant_is_offered(served, tmp_path):
    """A second layout file next to the first one shows up, and can be made active."""
    from plotplate.config import dump_yaml

    base, layout = served
    taller = {**layout.raw, "area": {**layout.raw["area"], "height": 80}}
    dump_yaml(taller, layout.path.with_name("layout.optimized.yaml"))

    state = json.loads(fetch(base + "state.json"))
    assert [v["key"] for v in state["variants"]] == ["base", "optimized"]
    assert state["active"] == "base" and state["height"] == 60
    assert {v["key"]: len(v["boxes"]) for v in state["variants"]} == {"base": 2, "optimized": 2}

    other = json.loads(fetch(base + "state.json?layout=optimized"))
    assert other["active"] == "optimized" and other["height"] == 80
    assert fetch(base + "image/figure.png?layout=optimized")[:4] == b"\x89PNG"


def test_the_sheet_is_part_of_the_state(served):
    base, _layout = served
    sheet = json.loads(fetch(base + "state.json"))["sheet"]
    assert sheet["paper"] == "a4" and sheet["size"] == [210.0, 297.0]
    assert sheet["area"] == [13.5, 25.0, 183.0, 60.0]  # centred in the text block, at its top
    assert sheet["assumed"] is False


def test_a_broken_layout_is_reported_instead_of_crashing(served):
    base, layout = served
    layout.path.with_name("layout.broken.yaml").write_text("panels: [not, a, mapping]\n")
    state = json.loads(fetch(base + "state.json?layout=broken"))
    assert state["error"] and state["active"] == "broken"
    assert [v["key"] for v in state["variants"]] == ["base", "broken"]
    assert next(v for v in state["variants"] if v["key"] == "broken")["error"]
    assert json.loads(fetch(base + "state.json"))["panels"]  # the good one still works


@pytest.fixture
def editable(layout):
    """The same viewer, started with --edit; yields (base url, layout)."""
    server = make_server(layout.path, port=0, editable=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/", layout
    server.shutdown()
    server.server_close()


def post(url, payload, content_type="application/json"):
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": content_type}
    )
    return json.loads(urllib.request.urlopen(request, timeout=10).read())


def test_edited_boxes_are_saved_as_a_new_variant(editable):
    """Drag a panel on the page, save it: a variant appears, with the axes moved with it."""
    base, layout = editable
    answer = post(base + "save", {"variant": "custom", "panels": {"A": [0, 0, 100, 50]}})
    assert answer["saved"] == "layout.custom.yaml"

    saved = pp.Layout.load(layout.path.with_name("layout.custom.yaml"))
    assert saved.panels["A"].box.to_list() == [0, 0, 100, 50]
    assert saved.panels["B"].box == layout.panels["B"].box  # untouched panels stayed
    roc = saved.panels["A"].axes["roc"].region
    assert roc.left == pytest.approx(layout.panels["A"].axes["roc"].region.left, abs=0.01)
    assert roc.w > layout.panels["A"].axes["roc"].region.w  # the plot took the extra width
    assert "mosaic" not in saved.raw  # what is written is a resolved layout
    assert json.loads(fetch(base + "state.json"))["editable"] is True


def test_saving_never_touches_the_layout_you_maintain(editable):
    base, layout = editable
    before = layout.path.read_text()
    with pytest.raises(urllib.error.HTTPError) as caught:
        post(base + "save", {"variant": "base", "panels": {"A": [0, 0, 60, 40]}})
    assert caught.value.code == 400
    assert "layout.yaml is the file you maintain" in caught.value.read().decode()
    assert layout.path.read_text() == before


def test_a_read_only_viewer_refuses_to_save(served):
    base, layout = served
    with pytest.raises(urllib.error.HTTPError) as caught:
        post(base + "save", {"variant": "custom", "panels": {"A": [0, 0, 60, 40]}})
    assert caught.value.code == 400 and "read-only" in caught.value.read().decode()
    assert not layout.path.with_name("layout.custom.yaml").exists()
    assert json.loads(fetch(base + "state.json"))["editable"] is False


@pytest.mark.parametrize(
    ("payload", "says"),
    [
        ({"variant": "../escape", "panels": {}}, "not a variant name"),
        ({"variant": "custom", "panels": {"../z": [0, 0, 10, 10]}}, "not a panel name"),
        ({"variant": "custom", "panels": {"Z": {"locked": True}}}, "has no box"),
        ({"variant": "custom", "panels": {"A": [0, 0, 0.2, 40]}}, "1 x 1 mm"),
        ({"variant": "custom", "panels": {"A": ["a", 0, 10, 10]}}, "four numbers"),
    ],
)
def test_a_save_that_makes_no_sense_is_refused(editable, payload, says):
    base, layout = editable
    with pytest.raises(urllib.error.HTTPError) as caught:
        post(base + "save", payload)
    assert says in caught.value.read().decode()
    assert not layout.path.with_name("layout.custom.yaml").exists()


def test_a_save_from_another_site_or_a_form_is_refused(editable):
    """A page on another origin can reach localhost; it cannot write through this route."""
    base, layout = editable
    for headers in ({"Origin": "https://evil.example"}, {}):
        request = urllib.request.Request(
            base + "save",
            data=b"variant=custom",
            headers={"Content-Type": "application/x-www-form-urlencoded", **headers},
        )
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=10)
        assert caught.value.code in (403, 415)
    assert not layout.path.with_name("layout.custom.yaml").exists()


def test_page_guides_are_saved_with_the_boxes(editable):
    """Page guides are the author's scaffolding: they travel with the variant they belong to."""
    base, layout = editable
    answer = post(
        base + "save",
        {"variant": "custom", "panels": {}, "page_guides": {"x": [91.5, 10], "y": [64]}},
    )
    assert answer["saved"] == "layout.custom.yaml"
    saved = pp.Layout.load(layout.path.with_name("layout.custom.yaml"))
    assert saved.page_guides == {"x": [10.0, 91.5], "y": [64.0]}  # sorted, and still millimetres
    assert json.loads(fetch(base + "state.json?layout=custom"))["page_guides"]["y"] == [64.0]


def test_a_layout_without_page_guides_gains_none(editable):
    base, layout = editable
    post(base + "save", {"variant": "custom", "panels": {}, "page_guides": {"x": [], "y": []}})
    assert "page_guides" not in pp.config.load_yaml(layout.path.with_name("layout.custom.yaml"))


def test_the_page_can_arrange_what_it_holds_without_writing_anything(editable):
    """The arrange button: optimize on the draft, answered as boxes, no file touched."""
    base, layout = editable
    before = sorted(p.name for p in layout.path.parent.iterdir())
    answer = post(base + "optimize", {"panels": {"A": [0, 0, 60, 40]}})

    assert set(answer["panels"]) == set(layout.panels)
    assert answer["width"] == layout.width and answer["height"] == layout.height
    assert "of the figure" in answer["summary"]
    assert sorted(p.name for p in layout.path.parent.iterdir()) == before  # nothing written


def test_arranging_brings_a_panel_dragged_off_the_figure_back(editable):
    """The case the button exists for: a box pulled over the edge, put back where it belongs."""
    base, layout = editable
    answer = post(base + "optimize", {"panels": {"B": [120, -14, 89.5, 25]}})
    for box in answer["panels"].values():
        assert box[0] >= -0.01 and box[1] >= -0.01
        assert box[0] + box[2] <= layout.width + 0.01
        assert box[1] + box[3] <= layout.height + 0.01


def test_a_read_only_viewer_does_not_arrange_either(served):
    base, _layout = served
    with pytest.raises(urllib.error.HTTPError) as caught:
        post(base + "optimize", {"panels": {}})
    assert "read-only" in caught.value.read().decode()


def test_a_layout_that_declares_no_axes_shows_none(tmp_path):
    """From a screenshot there are only panel boxes: nothing is inferred, so nothing is drawn."""
    from plotplate.config import dump_yaml

    dump_yaml(
        {
            "schema": 1,
            "area": {"width": 180, "height": 60},
            "panels": {"A": {"box": [0, 0, 88, 60]}, "B": {"box": [92, 0, 88, 60]}},
        },
        tmp_path / "layout.yaml",
    )
    state = Viewer(tmp_path).state()
    assert [p["axes"] for p in state["panels"]] == [[], []]
    assert state["features"] == [] and state["rules"] == []  # nothing measured, nothing to check
    assert state["guides"] == {"x": {}, "y": {}}
    # ... but the page still offers the four margins to arrange those boxes against
    assert state["page_guides_from_margins"] is True
    assert state["page_guides"]["y"] == [0.0, 247.0]


def test_the_page_starts_from_the_margins_when_the_layout_has_no_guides(editable):
    """Four page guides, one per margin: the lines a figure is arranged against first."""
    base, _layout = editable
    state = json.loads(fetch(base + "state.json"))
    sheet = state["sheet"]
    assert state["page_guides_from_margins"] is True
    assert state["page_guides"]["x"] == [
        round(sheet["text"][0] - sheet["area"][0], 2),
        round(sheet["text"][0] + sheet["text"][2] - sheet["area"][0], 2),
    ]
    assert state["page_guides"]["y"][0] == round(sheet["text"][1] - sheet["area"][1], 2)

    post(base + "save", {"variant": "custom", "panels": {}, "page_guides": {"x": [12], "y": []}})
    other = json.loads(fetch(base + "state.json?layout=custom"))
    assert other["page_guides"] == {"x": [12.0], "y": []}  # declared ones win over the margins
    assert other["page_guides_from_margins"] is False


def test_a_guide_dragged_off_the_sheet_is_dropped(editable):
    base, layout = editable
    post(
        base + "save",
        {"variant": "custom", "panels": {}, "page_guides": {"x": [12, -400], "y": [9000]}},
    )
    saved = pp.Layout.load(layout.path.with_name("layout.custom.yaml"))
    assert saved.page_guides == {"x": [12.0], "y": []}


def test_a_panel_can_be_locked_from_the_page(editable):
    """The page's lock is the optimizer's freeze: one promise, kept by both."""
    base, layout = editable
    post(base + "save", {"variant": "custom", "panels": {"A": {"locked": True}}})
    saved = pp.config.load_yaml(layout.path.with_name("layout.custom.yaml"))
    assert saved["optimize"]["panels"]["A"] == {"freeze": True}
    assert json.loads(fetch(base + "state.json?layout=custom"))["panels"][0]["locked"] is True

    answer = post(base + "optimize", {"layout": "custom", "panels": {}, "locked": ["A"]})
    before = layout.panels["A"].box
    assert answer["panels"]["A"][2:] == [before.w, before.h]  # kept its size

    post(base + "save", {"layout": "custom", "variant": "free", "panels": {"A": {"locked": False}}})
    assert "optimize" not in pp.config.load_yaml(layout.path.with_name("layout.free.yaml"))


def test_a_panel_can_be_added_and_given_a_letter(editable):
    base, layout = editable
    post(
        base + "save",
        {"variant": "custom", "panels": {"C": {"box": [0, 62, 88, 40], "label": "c"}}},
    )
    saved = pp.Layout.load(layout.path.with_name("layout.custom.yaml"))
    assert saved.panels["C"].box.to_list() == [0, 62, 88, 40]
    assert saved.panels["C"].label == "c"
    assert list(saved.panels) == ["A", "B", "C"]


def test_renaming_is_allowed_until_the_panel_has_been_drawn(editable, tmp_path):
    base, layout = editable
    post(base + "save", {"variant": "custom", "panels": {"A": {"rename": "S1"}}})
    saved = pp.Layout.load(layout.path.with_name("layout.custom.yaml"))
    assert list(saved.panels) == ["S1", "B"]  # in place: reading order is what letters follow

    (layout.panels_dir).mkdir(exist_ok=True)
    (layout.panels_dir / "B.pdf").write_bytes(b"%PDF-1.4\n")
    with pytest.raises(urllib.error.HTTPError) as caught:
        post(base + "save", {"variant": "other", "panels": {"B": {"rename": "S2"}}})
    message = caught.value.read().decode()
    assert "already drawn" in message and "B.pdf" in message


def test_arrange_reads_the_styles_of_the_layout_it_came_from(tmp_path):
    """A draft must know where it lives: `style_files: [../style.yaml]` is relative to it."""
    from plotplate.config import dump_yaml

    dump_yaml({"font": {"size": 7}}, tmp_path / "style.yaml")
    figure = tmp_path / "figure"
    figure.mkdir()
    dump_yaml(
        {
            "schema": 1,
            "style_files": ["../style.yaml"],
            "area": {"width": 180, "height": 60},
            "panels": {"A": {"box": [0, 0, 88, 60]}, "B": {"box": [92, 0, 88, 60]}},
        },
        figure / "layout.yaml",
    )
    answer = Viewer(figure, "a4", editable=True).arrange(None, {"A": [0, 0, 80, 55]})
    assert set(answer["panels"]) == {"A", "B"}


def test_arrange_respects_the_guides_on_the_page_before_they_are_saved(editable):
    """Drag a guide, press arrange: the guide you are looking at is the one that holds."""
    base, layout = editable
    wide = {name: [*spec.box.to_list()] for name, spec in layout.panels.items()}
    answer = post(
        base + "optimize",
        {"panels": wide, "page_guides": {"x": [layout.width / 2 - 10], "y": []}},
    )
    for box in answer["panels"].values():
        crosses = box[0] < layout.width / 2 - 10.01 and box[0] + box[2] > layout.width / 2 - 9.99
        assert not crosses or box[0] == 0  # only something already spanning it still does


def test_a_panel_added_on_the_page_is_arranged_with_the_others(editable):
    """A box that exists only on the page is a panel to the optimizer, before any save."""
    base, _layout = editable
    answer = post(
        base + "optimize",
        {"panels": {"C": [0, 62, 60, 40]}},  # C is not in the layout yet
    )
    assert set(answer["panels"]) == {"A", "B", "C"}
    assert answer["panels"]["C"][3] > 0


def test_panels_can_be_renumbered_in_one_pass(editable):
    """Renaming is a permutation: C becomes D while the new D becomes C, without colliding."""
    base, layout = editable
    answer = post(
        base + "save",
        {
            "variant": "custom",
            "panels": {
                "A": {"rename": "B"},
                "B": {"rename": "A", "box": [0, 0, 60, 40]},
            },
        },
    )
    assert answer["saved"] == "layout.custom.yaml"
    saved = pp.Layout.load(layout.path.with_name("layout.custom.yaml"))
    assert saved.panels["A"].box.to_list() == [0, 0, 60, 40]  # what was B is now A
    assert saved.panels["B"].box == layout.panels["A"].box  # ... and what was A is now B


def test_two_panels_cannot_be_given_the_same_name(editable):
    base, layout = editable
    with pytest.raises(urllib.error.HTTPError) as caught:
        post(
            base + "save",
            {"variant": "custom", "panels": {"A": {"rename": "X"}, "B": {"rename": "X"}}},
        )
    assert "cannot both be called" in caught.value.read().decode()
    assert not layout.path.with_name("layout.custom.yaml").exists()


def test_saved_panels_are_written_in_reading_order(editable):
    base, layout = editable
    post(
        base + "save",
        {"variant": "custom", "panels": {"C": {"box": [0, 70, 80, 40]}, "A": [0, 0, 80, 60]}},
    )
    saved = pp.config.load_yaml(layout.path.with_name("layout.custom.yaml"))
    assert list(saved["panels"]) == ["A", "B", "C"]  # the new one went where its box puts it
