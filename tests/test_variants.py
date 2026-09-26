"""Layout variants: one figure, several layout files, and folder arguments."""

import pytest

from plotplate.config import dump_yaml
from plotplate.variants import find_layouts, resolve_layout_path, variant_of, variant_path


def test_variant_names_and_siblings():
    assert variant_of("figures/f1/layout.yaml") == "base"
    assert variant_of("layout.optimized.yaml") == "optimized"
    assert variant_of("layout.nature.wide.yml") == "nature.wide"
    assert (
        variant_path("figures/f1/layout.detected.yaml", "optimized").name == "layout.optimized.yaml"
    )
    assert variant_path("layout.optimized.yaml", "base").name == "layout.yaml"


def _write(folder, name):
    dump_yaml({"schema": 1, "area": {"width": 100, "height": 50}, "panels": {}}, folder / name)


def test_find_layouts_lists_the_variants_base_first(tmp_path):
    for name in ("layout.optimized.yaml", "layout.yaml", "layout.detected.yaml", "alignment.yaml"):
        _write(tmp_path, name)
    found = find_layouts(tmp_path)
    assert list(found) == ["base", "detected", "optimized"]  # alignment.yaml is not a layout
    assert found["base"].name == "layout.yaml"
    assert find_layouts(tmp_path / "layout.detected.yaml") == found  # a file finds its siblings


def test_a_folder_resolves_to_its_layout(tmp_path):
    _write(tmp_path, "layout.yaml")
    _write(tmp_path, "layout.optimized.yaml")
    assert resolve_layout_path(tmp_path).name == "layout.yaml"
    assert resolve_layout_path(tmp_path / "layout.optimized.yaml").name == "layout.optimized.yaml"


def test_a_folder_with_one_variant_and_no_base_still_resolves(tmp_path):
    _write(tmp_path, "layout.detected.yaml")
    assert resolve_layout_path(tmp_path).name == "layout.detected.yaml"


def test_an_ambiguous_or_empty_folder_says_so(tmp_path):
    with pytest.raises(FileNotFoundError, match=r"no layout\.yaml"):
        resolve_layout_path(tmp_path)
    _write(tmp_path, "layout.a.yaml")
    _write(tmp_path, "layout.b.yaml")
    with pytest.raises(FileNotFoundError, match="several variants"):
        resolve_layout_path(tmp_path)
