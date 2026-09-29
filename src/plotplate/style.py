"""Translate a resolved style mapping into matplotlib rcParams."""

from __future__ import annotations

from typing import Any

import yaml
from cycler import cycler
from matplotlib import font_manager

from .config import PRESETS


def label_text(style: dict[str, Any], letter: str) -> str:
    """What a panel letter looks like once drawn: ``a``, ``(a)``, ``a)``...

    The letter itself stays what the layout says, so renaming and formatting never get mixed
    up: ``panel_label.format`` is applied at drawing time, by LaTeX, the preview and the
    viewer alike. A format that cannot be applied is ignored rather than raised: a figure with
    a misspelt template still has its letters.
    """
    template = str((style.get("panel_label") or {}).get("format") or "{letter}")
    try:
        return template.format(letter=letter)
    except (KeyError, IndexError, ValueError):
        return letter


def rc_params(style: dict[str, Any]) -> dict[str, Any]:
    """Matplotlib rcParams for panels drawn at final print size."""
    font = style["font"]
    lines = style["lines"]
    ticks = style["ticks"]
    families = list(font["family"])
    rc: dict[str, Any] = {
        "font.family": "sans-serif",
        "font.sans-serif": families,
        "font.size": font["size"],
        "axes.labelsize": font["size"],
        "axes.titlesize": font["large"],
        "figure.titlesize": font["large"],
        "figure.labelsize": font["size"],
        "xtick.labelsize": font["small"],
        "ytick.labelsize": font["small"],
        "legend.fontsize": font["small"],
        "legend.title_fontsize": font["size"],
        "mathtext.fontset": "custom",
        "mathtext.rm": families[0],
        "mathtext.sf": families[0],
        "mathtext.it": f"{families[0]}:italic",
        "mathtext.bf": f"{families[0]}:bold",
        "lines.linewidth": lines["width"],
        "axes.linewidth": lines["axes"],
        "patch.linewidth": lines["axes"],
        "grid.linewidth": lines["axes"],
        "hatch.linewidth": lines["axes"],
        # Keep text as text: editable in Illustrator/Inkscape, required by journals.
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "none",
        "svg.hashsalt": "plotplate",  # stable SVG ids across re-renders
        "savefig.dpi": style["export"]["dpi"],
        "savefig.bbox": None,  # never "tight": the file size must equal the panel box
        "savefig.pad_inches": 0.0,
        "figure.constrained_layout.w_pad": 0.02,
        "figure.constrained_layout.h_pad": 0.02,
    }
    for axis in ("xtick", "ytick"):
        rc[f"{axis}.major.size"] = ticks["length"]
        rc[f"{axis}.minor.size"] = ticks["length"] * 0.6
        rc[f"{axis}.major.width"] = ticks["width"]
        rc[f"{axis}.minor.width"] = ticks["width"] * 0.8
        rc[f"{axis}.major.pad"] = ticks["pad"]
        rc[f"{axis}.minor.pad"] = ticks["pad"]
    cycle = style.get("color_cycle")
    if cycle:
        colors = palette(cycle) if isinstance(cycle, str) else list(cycle)
        rc["axes.prop_cycle"] = cycler(color=colors)
    rc.update(style.get("rc") or {})
    return rc


def palette(name: str) -> list[str]:
    """Colors of a bundled palette (``plotplate palettes`` lists them), e.g. ``palette("wong")``."""
    palettes = yaml.safe_load((PRESETS / "palettes.yaml").read_text(encoding="utf-8"))
    if name not in palettes:
        raise KeyError(f"Unknown palette {name!r}; bundled: {', '.join(palettes)}")
    return list(palettes[name]["colors"])


def first_available_font(families: list[str]) -> str | None:
    """The first family matplotlib can resolve without falling back, if any."""
    for family in families:
        try:
            font_manager.findfont(family, fallback_to_default=False)
        except ValueError:
            continue
        return family
    return None


def rebuild_font_cache() -> None:
    """Rescan system fonts (needed once after installing new fonts, e.g. Arial)."""
    font_manager.fontManager = font_manager._load_fontmanager(try_read_cache=False)  # type: ignore[attr-defined]
