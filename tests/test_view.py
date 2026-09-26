import json
import threading
import urllib.error
import urllib.request

import matplotlib
import pytest

matplotlib.use("Agg")

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
