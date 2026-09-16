"""Clean up approximate layouts: unify nearly-equal edges, then snap to a step.

Boxes coming from a screenshot, or drawn by hand in Inkscape, are almost aligned: a
left edge at 91.8 mm next to one at 92.1 mm. ``tidy`` clusters edge coordinates that are
within ``tolerance`` of each other, replaces each cluster by its (snapped) mean, and
rewrites every explicit ``box`` so aligned things are *exactly* aligned.
Guide references and mosaic-derived boxes are left untouched.
"""

from __future__ import annotations

import copy
from typing import Any

from .geometry import Rect


def _clusters(values: list[float], tolerance: float, step: float) -> dict[float, float]:
    mapping: dict[float, float] = {}
    ordered = sorted(set(values))
    group: list[float] = []

    def flush() -> None:
        if group:
            target = sum(group) / len(group)
            if step > 0:
                target = round(target / step) * step
            for value in group:
                mapping[value] = round(target, 4)

    for value in ordered:
        if group and value - group[-1] > tolerance:
            flush()
            group = []
        group.append(value)
    flush()
    return mapping


def _boxes(data: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
    """``(container, key)`` pairs holding an explicit ``box`` list."""
    found = []
    for panel in (data.get("panels") or {}).values():
        if not isinstance(panel, dict):
            continue
        if panel.get("box") is not None:
            found.append((panel, "box"))
        for axes in (panel.get("axes") or {}).values():
            if (
                isinstance(axes, dict)
                and axes.get("box") is not None
                and axes.get("ref", "page") == "page"
            ):
                found.append((axes, "box"))
    return found


def tidy(data: dict[str, Any], tolerance: float = 1.0, step: float = 0.5) -> dict[str, Any]:
    """Return a copy of the layout mapping with aligned, snapped boxes.

    Args:
        data: raw layout mapping.
        tolerance: edges closer than this (mm) are made identical.
        step: snapping grid (mm); 0 disables snapping.
    """
    data = copy.deepcopy(data)
    holders = _boxes(data)
    rects = [Rect.from_list(holder[key]) for holder, key in holders]
    xs = [v for r in rects for v in (r.left, r.right)]
    ys = [v for r in rects for v in (r.top, r.bottom)]
    page = data.get("page") or {}
    for bound, values in ((page.get("width"), xs), (page.get("height"), ys)):
        if isinstance(bound, int | float):
            values.extend([0.0, float(bound)])
    xmap, ymap = _clusters(xs, tolerance, step), _clusters(ys, tolerance, step)
    for (holder, key), rect in zip(holders, rects, strict=True):
        new = Rect.from_edges(xmap[rect.left], ymap[rect.top], xmap[rect.right], ymap[rect.bottom])
        holder[key] = new.to_list()
    return data


def merge_panels(data: dict[str, Any], names: list[str], new_name: str) -> dict[str, Any]:
    """Replace panels ``names`` by one panel ``new_name`` whose box is their union."""
    data = copy.deepcopy(data)
    panels = data.get("panels") or {}
    missing = [n for n in names if n not in panels or (panels[n] or {}).get("box") is None]
    if missing:
        raise KeyError(f"Panels without explicit box (or unknown): {missing}")
    rects = [Rect.from_list(panels[n]["box"]) for n in names]
    union = Rect.from_edges(
        min(r.left for r in rects),
        min(r.top for r in rects),
        max(r.right for r in rects),
        max(r.bottom for r in rects),
    )
    merged: dict[str, Any] = {}
    for key, value in panels.items():
        if key in names:
            if new_name not in merged:
                merged[new_name] = {"box": union.to_list()}
            continue
        merged[key] = value
    data["panels"] = merged
    return data


def fill_gaps(data: dict[str, Any], gap: float) -> dict[str, Any]:
    """Grow panel boxes until they meet their neighbours ``gap`` mm apart, or the page edge.

    Screenshot detection finds *content* bounding boxes; panel boxes also include the
    surrounding white space. Each side moves to the midpoint of the gutter to the nearest
    facing panel (overlapping in the other direction), minus half the gap.
    """
    data = copy.deepcopy(data)
    page = data.get("page") or {}
    width, height = float(page["width"]), float(page["height"])
    panels = {k: v for k, v in (data.get("panels") or {}).items() if (v or {}).get("box") is not None}
    rects = {k: Rect.from_list(v["box"]) for k, v in panels.items()}

    def overlaps(a0: float, a1: float, b0: float, b1: float) -> bool:
        return min(a1, b1) - max(a0, b0) > 0

    for name, r in rects.items():
        others = [o for k, o in rects.items() if k != name]
        left_n = [
            o.right
            for o in others
            if o.right <= r.left and overlaps(r.top, r.bottom, o.top, o.bottom)
        ]
        right_n = [
            o.left for o in others if o.left >= r.right and overlaps(r.top, r.bottom, o.top, o.bottom)
        ]
        top_n = [
            o.bottom
            for o in others
            if o.bottom <= r.top and overlaps(r.left, r.right, o.left, o.right)
        ]
        bottom_n = [
            o.top for o in others if o.top >= r.bottom and overlaps(r.left, r.right, o.left, o.right)
        ]
        left = (max(left_n) + r.left) / 2 + gap / 2 if left_n else 0.0
        right = (min(right_n) + r.right) / 2 - gap / 2 if right_n else width
        top = (max(top_n) + r.top) / 2 + gap / 2 if top_n else 0.0
        bottom = (min(bottom_n) + r.bottom) / 2 - gap / 2 if bottom_n else height
        panels[name]["box"] = Rect.from_edges(left, top, right, bottom).to_list()
    return data


def scale_layout(data: dict[str, Any], width: float) -> dict[str, Any]:
    """Scale every explicit box (and the page) uniformly so the page is ``width`` mm wide.

    Used to retarget a layout drafted from an existing figure to a journal column width.
    Label offsets and guides scale too; font sizes do not (they are set by the style).
    """
    data = copy.deepcopy(data)
    page = data["page"]
    factor = width / float(page["width"])
    page["width"] = round(width, 2)
    page["height"] = round(float(page["height"]) * factor, 2)
    for holder, key in _boxes(data):
        holder[key] = [round(float(v) * factor, 2) for v in holder[key]]
    for panel in (data.get("panels") or {}).values():
        label = (panel or {}).get("label")
        if isinstance(label, dict) and label.get("offset") is not None:
            label["offset"] = [round(float(v) * factor, 2) for v in label["offset"]]
    for axis in ("x", "y"):
        guides = (data.get("guides") or {}).get(axis) or {}
        for name in guides:
            guides[name] = round(float(guides[name]) * factor, 2)
    return data
