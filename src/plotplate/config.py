"""Loading YAML presets and merging layered configuration."""

from __future__ import annotations

import copy
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

PRESETS = resources.files("plotplate") / "presets"


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Read a YAML mapping from ``path``; an empty file gives an empty dict."""
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise TypeError(f"{path}: expected a YAML mapping at the top level")
    return data


def dump_yaml(data: dict[str, Any], path: str | Path) -> None:
    """Write ``data`` as block-style YAML, preserving key order."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True, width=100)


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Return ``base`` recursively updated by ``override`` (neither input is modified).

    Mappings merge key by key; any other value (lists included) replaces the base value.
    """
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def default_style() -> dict[str, Any]:
    """The package's baseline style, before any journal or project override."""
    style: dict[str, Any] = yaml.safe_load(
        (PRESETS / "default_style.yaml").read_text(encoding="utf-8")
    )
    return style


def list_journals() -> list[str]:
    """Names of the bundled journal presets."""
    return sorted(
        entry.name.removesuffix(".yaml")
        for entry in (PRESETS / "journals").iterdir()
        if entry.name.endswith(".yaml")
    )


def load_journal(name_or_path: str, base_dir: Path | None = None) -> dict[str, Any]:
    """Load a journal preset by bundled name (e.g. ``nature``) or by YAML path."""
    candidate = Path(name_or_path)
    if base_dir is not None and not candidate.is_absolute():
        candidate = base_dir / candidate
    if candidate.suffix in {".yaml", ".yml"} and candidate.exists():
        return load_yaml(candidate)
    bundled = PRESETS / "journals" / f"{name_or_path}.yaml"
    if not bundled.is_file():
        raise KeyError(
            f"Unknown journal preset {name_or_path!r}. Bundled presets: {', '.join(list_journals())}"
        )
    preset: dict[str, Any] = yaml.safe_load(bundled.read_text(encoding="utf-8"))
    return preset
