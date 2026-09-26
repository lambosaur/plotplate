import matplotlib

matplotlib.use("Agg")

import pytest

import plotplate as pp


@pytest.fixture
def layout_data():
    return {
        "schema": 1,
        "name": "t",
        "journal": "nature",
        "page": {"paper": "a4", "margins": {"left": 13.5, "right": 13.5, "top": 25, "bottom": 25}},
        "area": {"width": "double", "height": 60},
        "guides": {"x": {"left": 10}, "y": {"bottom": 50}},
        "mosaic": {"rows": ["AB"], "gap": 4},
        "panels": {
            "A": {
                "axes": {
                    "roc": {"left": "left", "top": 4, "right": 40, "bottom": "bottom"},
                    "grid": {
                        "left": 50,
                        "top": 4,
                        "right": 88,
                        "bottom": "bottom-10",
                        "ncols": 2,
                        "wgap": 4,
                    },
                }
            },
            "B": {"margins": [10, 4, 2, 10]},
        },
    }


@pytest.fixture
def layout(layout_data, tmp_path):
    path = tmp_path / "layout.yaml"
    pp.config.dump_yaml(layout_data, path)
    return pp.Layout.load(path)
