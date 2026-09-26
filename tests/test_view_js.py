"""The viewer's page is JavaScript, so it is run in node against a DOM shim.

Without this, the 300 lines that drag, snap and save panel boxes would be the only code in the
project nothing exercises. `tests/fixtures/view_harness.js` provides just enough DOM to load the
real script out of `view.PAGE`, drives pointer and keyboard events over a real `state.json`, and
exits non-zero on the first failed expectation.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from plotplate.config import dump_yaml
from plotplate.view import PAGE, Viewer

HARNESS = Path(__file__).parent / "fixtures" / "view_harness.js"
FIGURE = {
    "schema": 1,
    "name": "js",
    "page": {"paper": "a4", "margins": 13.5},
    "area": {"width": 183, "height": 120},
    "guides": {"x": {"left": 11}, "y": {"bottom": 52}},
    "panels": {
        "A": {"box": [0, 0, 89.5, 62], "axes": {"roc": {"box": [11, 8, 33, 44]}}},
        "B": {"box": [93.5, 0, 89.5, 62], "axes": {"heat": {"box": [104.5, 8, 70, 44]}}},
        "C": {"box": [0, 66, 183, 54], "axes": {"scatter": {"box": [11, 76, 170, 36]}}},
    },
}


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_page_drags_snaps_and_saves(tmp_path):
    node = shutil.which("node") or "node"
    figure = tmp_path / "figure"
    figure.mkdir()
    dump_yaml(FIGURE, figure / "layout.yaml")
    (tmp_path / "state.json").write_text(
        json.dumps(Viewer(figure, "a4", editable=True).state()), encoding="utf-8"
    )
    script = re.search(r"<script>(.*)</script>", PAGE, re.DOTALL)
    assert script, "the page no longer has one script block"
    (tmp_path / "page.js").write_text(script.group(1), encoding="utf-8")

    done = subprocess.run(
        [node, str(HARNESS), str(tmp_path)],
        capture_output=True,
        check=False,
        text=True,
        timeout=60,
    )
    assert done.returncode == 0, done.stdout + done.stderr
