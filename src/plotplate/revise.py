"""Compare two layouts and write a revision plan.

A revision (moving, resizing, merging, splitting, adding or removing panels) changes the
layout and the notebooks that draw the panels. ``diff_layouts`` computes what changed,
deterministically: panels are matched by their key when it exists in both layouts, and
otherwise by how much their boxes overlap. The result is a plan (YAML) listing every
change with the notebooks it affects, which a person or an agent reviews before editing
any code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import dump_yaml
from .geometry import Rect
from .layout import Layout

MATCH_IOU = 0.25


@dataclass
class Change:
    """One entry of a revision plan."""

    change: str  # unchanged | moved | relabelled | merged | split | added | removed
    old: list[str] = field(default_factory=list)
    new: list[str] = field(default_factory=list)
    detail: str = ""
    sources: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Plan entry, ready for YAML."""
        entry: dict[str, Any] = {"change": self.change}
        if self.old:
            entry["old"] = self.old
        if self.new:
            entry["new"] = self.new
        if self.detail:
            entry["detail"] = self.detail
        if self.sources:
            entry["sources"] = self.sources
        return entry


def _iou(a: Rect, b: Rect) -> float:
    inter = a.intersection_area(b)
    union = a.w * a.h + b.w * b.h - inter
    return inter / union if union else 0.0


def _links(
    old_boxes: dict[str, Rect], new_boxes: dict[str, Rect], mapping: dict[str, list[str]] | None
) -> list[tuple[str, str]]:
    """Pairs of (old key, new key) that refer to the same content.

    Keys present in both layouts are linked, unless ``mapping`` says otherwise for that key.
    Remaining panels are linked when their boxes overlap enough, which is what reveals a
    split (one old panel overlapping two new ones) or a merge.
    """
    mapped = {o: [n for n in news if n in new_boxes] for o, news in (mapping or {}).items()}
    links = [(old_key, new_key) for old_key, news in mapped.items() for new_key in news]
    taken_new = {n for _, n in links}
    for key in old_boxes.keys() & new_boxes.keys():
        if key not in mapped and key not in taken_new:
            links.append((key, key))
    if mapping:
        return links
    linked = set(links)
    for old_key, old_box in old_boxes.items():
        for new_key, new_box in new_boxes.items():
            if (old_key, new_key) in linked:
                continue
            if _iou(old_box, new_box) >= MATCH_IOU:
                links.append((old_key, new_key))
    return links


def _components(
    old_boxes: dict[str, Rect], new_boxes: dict[str, Rect], mapping: dict[str, list[str]] | None
) -> list[tuple[list[str], list[str]]]:
    """Groups of (old keys, new keys) that belong together."""
    parent: dict[tuple[str, str], tuple[str, str]] = {}

    def find(node: tuple[str, str]) -> tuple[str, str]:
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    nodes = [("old", k) for k in old_boxes] + [("new", k) for k in new_boxes]
    for node in nodes:
        find(node)
    for old_key, new_key in _links(old_boxes, new_boxes, mapping):
        parent[find(("old", old_key))] = find(("new", new_key))

    groups: dict[tuple[str, str], tuple[list[str], list[str]]] = {}
    for side, key in nodes:
        olds, news = groups.setdefault(find((side, key)), ([], []))
        (olds if side == "old" else news).append(key)
    return sorted(groups.values(), key=lambda g: g[0] or g[1])


def _describe(old: Layout, new: Layout, old_key: str, new_key: str) -> tuple[str, str]:
    """Change kind and detail for a one-to-one match."""
    old_spec, new_spec = old.panels[old_key], new.panels[new_key]
    a, b = old_spec.box, new_spec.box
    moved = max(abs(a.left - b.left), abs(a.top - b.top))
    resized = max(abs(a.w - b.w), abs(a.h - b.h))
    parts = []
    if moved > 0.05:
        parts.append(f"moved by {moved:.1f} mm")
    if resized > 0.05:
        parts.append(f"resized {a.w:.1f}x{a.h:.1f} -> {b.w:.1f}x{b.h:.1f} mm")
    if old_spec.label != new_spec.label:
        parts.append(f"label {old_spec.label} -> {new_spec.label}")
    if old_key != new_key:
        parts.append(f"key {old_key} -> {new_key}")
    old_axes, new_axes = set(old_spec.axes), set(new_spec.axes)
    if old_axes - new_axes:
        parts.append(f"axes removed: {sorted(old_axes - new_axes)}")
    if new_axes - old_axes:
        parts.append(f"axes added: {sorted(new_axes - old_axes)}")
    for name in sorted(old_axes & new_axes):
        before, after = old_spec.axes[name].region, new_spec.axes[name].region
        if max(abs(before.left - after.left), abs(before.top - after.top),
               abs(before.w - after.w), abs(before.h - after.h)) > 0.05:  # fmt: skip
            parts.append(f"axes {name}: {before.to_list(1)} -> {after.to_list(1)}")
    if not parts:
        return "unchanged", ""
    kind = "relabelled" if all(p.startswith(("label", "key")) for p in parts) else "moved"
    return kind, "; ".join(parts)


def diff_layouts(
    old: Layout, new: Layout, mapping: dict[str, list[str]] | None = None
) -> list[Change]:
    """Changes between two layouts, matched by key, by box overlap, or by ``mapping``."""
    from .cli import panel_sources

    old_boxes = {k: v.box for k, v in old.panels.items()}
    new_boxes = {k: v.box for k, v in new.panels.items()}
    sources = {k: v.name for k, v in panel_sources(old).items()}
    changes: list[Change] = []
    for olds, news in _components(old_boxes, new_boxes, mapping):
        entry_sources = [sources[k] for k in olds if k in sources]
        if olds and not news:
            changes.append(Change("removed", olds, [], "panel is gone", entry_sources))
        elif news and not olds:
            boxes = ", ".join(new.panels[k].box.to_list(1).__str__() for k in news)
            changes.append(Change("added", [], news, f"new panel at {boxes}"))
        elif len(olds) == 1 and len(news) == 1:
            kind, detail = _describe(old, new, olds[0], news[0])
            changes.append(Change(kind, olds, news, detail, entry_sources))
        elif len(olds) == 1:
            changes.append(
                Change(
                    "split",
                    olds,
                    sorted(news),
                    f"{olds[0]} becomes {len(news)} panels",
                    entry_sources,
                )
            )
        else:
            changes.append(
                Change(
                    "merged",
                    sorted(olds),
                    news,
                    f"{len(olds)} panels become {news[0]}",
                    entry_sources,
                )
            )
    return changes


def write_plan(changes: list[Change], old: Layout, new: Layout, path: str | Path) -> Path:
    """Write the revision plan as YAML, for review and for an agent to work from."""
    data = {
        "from": str(old.path or old.name),
        "to": str(new.path or new.name),
        "summary": {
            kind: sum(1 for c in changes if c.change == kind)
            for kind in ("unchanged", "moved", "relabelled", "merged", "split", "added", "removed")
            if any(c.change == kind for c in changes)
        },
        "changes": [c.as_dict() for c in changes if c.change != "unchanged"],
        "unchanged": [c.old[0] for c in changes if c.change == "unchanged"],
    }
    dump_yaml(data, path)
    return Path(path)


def diff_wireframe(old: Layout, new: Layout, out: str | Path, dpi: int = 130) -> Path:
    """Before/after wireframes side by side, for visual review."""
    import tempfile

    import matplotlib.pyplot as plt

    from .render import wireframe

    with tempfile.TemporaryDirectory() as tmp:
        images = [
            plt.imread(wireframe(layout, Path(tmp) / f"{side}.png"))
            for side, layout in (("before", old), ("after", new))
        ]
    heights = [image.shape[0] / image.shape[1] for image in images]
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.5 * max(heights)))
    for ax, image, title in zip(axes, images, ("before", "after"), strict=True):
        ax.imshow(image)
        ax.set_title(title, fontsize=13, weight="bold", loc="left")
        ax.set_xticks([])
        ax.set_yticks([])
    fig.savefig(out, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return Path(out)
