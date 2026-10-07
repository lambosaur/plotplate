"""Turn a drafted layout into round numbers.

A detector reports what it measured: a left edge at 91.8 mm next to one at 92.1 mm, and panel
boxes that hug the ink instead of owning the white space around it. :func:`snap` grows each box
into the space beside it, then clusters coordinates within ``tolerance`` of each other and
replaces each cluster by one snapped value -- so things that were nearly aligned become exactly
aligned, and the few numbers left are the ones the figure is really made of.

Panel boxes, axes rectangles, axes edges written as numbers, guides and page guides all move
together: snapping boxes alone would push an axes outside its panel.
"""

from __future__ import annotations

import copy
from typing import Any

from .geometry import Rect
from .layout import area_section, split_area_page


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


def _axes_entries(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Every axes mapping of a layout, whatever shape it has."""
    return [
        axes
        for panel in (data.get("panels") or {}).values()
        if isinstance(panel, dict)
        for axes in (panel.get("axes") or {}).values()
        if isinstance(axes, dict)
    ]


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


def scale_layout(data: dict[str, Any], width: float) -> dict[str, Any]:
    """Scale every explicit box (and the page) uniformly so the page is ``width`` mm wide.

    Used to retarget a layout drafted from an existing figure to a journal column width.
    Label offsets and guides scale too; font sizes do not (they are set by the style).
    """
    data = copy.deepcopy(data)
    area = area_section(data)
    factor = width / float(area["width"])
    area["width"] = round(width, 2)
    area["height"] = round(float(area["height"]) * factor, 2)
    for holder, key in _boxes(data):
        holder[key] = [round(float(v) * factor, 2) for v in holder[key]]
    # Axes written as edges keep numbers in page millimetres, and the gaps of an axes grid are
    # millimetres too; a guide reference (a string) is left alone, since the guide itself scales.
    for axes in _axes_entries(data):
        for key in ("left", "top", "right", "bottom", "wgap", "hgap"):
            if isinstance(axes.get(key), int | float):
                axes[key] = round(float(axes[key]) * factor, 2)
    for panel in (data.get("panels") or {}).values():
        label = (panel or {}).get("label")
        if isinstance(label, dict) and label.get("offset") is not None:
            label["offset"] = [round(float(v) * factor, 2) for v in label["offset"]]
    for axis in ("x", "y"):
        page_guides = (data.get("page_guides") or {}).get(axis)
        if page_guides:
            data["page_guides"][axis] = [round(float(v) * factor, 2) for v in page_guides]
        guides = (data.get("guides") or {}).get(axis) or {}
        for name in guides:
            guides[name] = round(float(guides[name]) * factor, 2)
    return data


def _edge_slots(data: dict[str, Any]) -> tuple[list[tuple[Any, Any]], list[tuple[Any, Any]]]:
    """Every x and y coordinate of a layout, as ``(container, key)`` pairs that can be rewritten.

    A box contributes its two edges per axis through a small adapter, since it is stored as
    ``[x, y, w, h]`` rather than as edges.
    """
    xs: list[tuple[Any, Any]] = []
    ys: list[tuple[Any, Any]] = []
    for holder, key in _boxes(data):
        xs += [(holder, (key, "left")), (holder, (key, "right"))]
        ys += [(holder, (key, "top")), (holder, (key, "bottom"))]
    for axes in _axes_entries(data):
        if axes.get("ref", "page") != "page":
            continue
        for key, bucket in (("left", xs), ("right", xs), ("top", ys), ("bottom", ys)):
            if isinstance(axes.get(key), int | float):  # a guide reference is a name, not a number
                bucket.append((axes, key))
    for axis, bucket in (("x", xs), ("y", ys)):
        for name in (data.get("guides") or {}).get(axis) or {}:
            bucket.append(((data["guides"][axis]), name))
        page_guides = (data.get("page_guides") or {}).get(axis) or []
        for index in range(len(page_guides)):
            bucket.append((data["page_guides"][axis], index))
    return xs, ys


def _read(holder: Any, key: Any) -> float:
    if isinstance(key, tuple):
        return float(getattr(Rect.from_list(holder[key[0]]), key[1]))
    return float(holder[key])


def _write(holder: Any, key: Any, value: float) -> None:
    if isinstance(key, tuple):
        rect = Rect.from_list(holder[key[0]])
        edges = {"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom}
        edges[key[1]] = value
        order = ("left", "top", "right", "bottom")
        holder[key[0]] = Rect.from_edges(*(edges[e] for e in order)).to_list()
        return
    holder[key] = round(value, 4)


def snap(
    data: dict[str, Any], tolerance: float = 1.0, gap: float | None = None, step: float = 0.5
) -> dict[str, Any]:
    """Return a copy of a drafted layout with its space filled and its coordinates unified.

    Args:
        data: raw layout mapping, as a detector wrote it.
        tolerance: coordinates closer than this (mm) are made identical.
        gap: the gutter to leave between panels; the layout's own ``gutter:`` by default.
        step: snapping grid (mm); 0 keeps the cluster mean.
    """
    from .pack import fill_white_space

    data = copy.deepcopy(data)
    area, _ = split_area_page(data)
    width, height = float(area["width"]), float(area["height"])
    if gap is None:
        raw = data.get("gutter", 4.0)
        gap = float(raw if isinstance(raw, int | float) else raw[0])

    panels = {
        name: entry
        for name, entry in (data.get("panels") or {}).items()
        if (entry or {}).get("box") is not None
    }
    if panels:
        grown = fill_white_space(
            {name: Rect.from_list(entry["box"]) for name, entry in panels.items()},
            width,
            height,
            gap,
            stretch=float("inf"),
        )
        for name, entry in panels.items():
            entry["box"] = grown[name].to_list()

    xs, ys = _edge_slots(data)
    maps = {}
    for axis, slots, bound in (("x", xs, width), ("y", ys, height)):
        # Read every coordinate first: rewriting one edge of a box recomputes its width, which
        # moves the other edge by a float hair and would make it unrecognisable afterwards.
        measured = [(holder, key, _read(holder, key)) for holder, key in slots]
        maps[axis] = _clusters([value for *_, value in measured] + [0.0, bound], tolerance, step)
        for holder, key, value in measured:
            _write(holder, key, maps[axis][value])
    # The figure's own edges are coordinates too: snapping a box out to 133.5 mm while the area
    # stays 133.4 mm tall would put it outside the page.
    section = area_section(data)
    section["width"] = round(maps["x"][width], 4)
    section["height"] = round(maps["y"][height], 4)
    return data
