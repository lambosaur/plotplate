"""Check that features of different panels line up, using measured page coordinates.

Each saved panel records where its plotting areas ended up on the page (`geometry` in
`panels/<panel>.json`): the axes rectangle, which spines are visible, the extent of the
drawn content including labels, and any reference point registered with ``Panel.mark``.
Because these are page millimetres, edges of different panels can be compared without
looking at the figure.

``alignment.yaml`` next to the layout declares what must line up::

    tolerance: 0.3          # mm, default for every rule
    rules:
      - match: bottom       # left | right | top | bottom | mark
        of: [A.roc, A.prc, B.heatmap]
      - match: left
        of: [A.roc, C.scatter, D.main]
        tolerance: 0.1
      - match: mark
        of: [D.zero, E.zero]

Without a constraints file, ``plotplate align`` reports groups of edges that are *nearly* equal:
those are the ones that look like mistakes in print.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .layout import Issue, Layout

EDGES = ("left", "right", "top", "bottom")


@dataclass
class Feature:
    """One measurable coordinate of a panel."""

    panel: str
    name: str  # axes name, or mark name
    kind: str  # "axes" or "mark"
    values: dict[str, float]  # left/right/top/bottom (axes) or x/y (mark), page mm
    spines: list[str]

    @property
    def reference(self) -> str:
        """``panel.name``, as used in the constraints file."""
        return f"{self.panel}.{self.name}"


def read_features(layout: Layout) -> tuple[dict[str, Feature], list[Issue]]:
    """Features of every saved panel of ``layout``, keyed by ``panel.name``."""
    features: dict[str, Feature] = {}
    issues: list[Issue] = []
    for panel in layout.panels:
        path = layout.panels_dir / f"{panel}.json"
        if not path.exists():
            issues.append(Issue("warning", "panel-missing", f"panel {panel}: not saved yet"))
            continue
        geometry = json.loads(path.read_text()).get("geometry") or {}
        if not geometry:
            issues.append(
                Issue("warning", "geometry-missing", f"panel {panel}: saved before geometry existed")
            )
        for name, entry in (geometry.get("axes") or {}).items():
            feature = Feature(panel, name, "axes", dict(entry["box_edges"]), entry.get("spines", []))
            features[feature.reference] = feature
        for name, entry in (geometry.get("anchors") or {}).items():
            feature = Feature(panel, name, "anchor", dict(entry["box_edges"]), [])
            features[feature.reference] = feature
        for name, entry in (geometry.get("marks") or {}).items():
            feature = Feature(panel, name, "mark", {"x": entry["x"], "y": entry["y"]}, [])
            features[feature.reference] = feature
    return features, issues


def _value(feature: Feature, match: str) -> float | None:
    if match == "mark":
        return feature.values.get("y") if feature.kind == "mark" else None
    return feature.values.get(match)


def check_rules(
    features: dict[str, Feature], rules: list[dict[str, Any]], tolerance: float
) -> list[Issue]:
    """One issue per rule that is broken, with the deviation in millimetres."""
    issues: list[Issue] = []
    for rule in rules:
        match = str(rule.get("match", "bottom"))
        refs = list(rule.get("of") or [])
        rule_tolerance = float(rule.get("tolerance", tolerance))
        values: dict[str, float] = {}
        for ref in refs:
            feature = features.get(ref)
            if feature is None:
                issues.append(Issue("error", "align-unknown", f"{ref} not found (panel not saved?)"))
                continue
            value = _value(feature, match)
            if value is None:
                issues.append(Issue("error", "align-unknown", f"{ref} has no {match}"))
                continue
            if match in EDGES and feature.kind == "axes" and match not in feature.spines:
                issues.append(
                    Issue(
                        "info",
                        "align-no-spine",
                        f"{ref}: {match} spine is not drawn; the axes edge is used",
                    )
                )
            values[ref] = value
        if len(values) < 2:
            continue
        spread = max(values.values()) - min(values.values())
        if spread > rule_tolerance:
            detail = ", ".join(f"{ref} {value:.2f}" for ref, value in sorted(values.items()))
            issues.append(
                Issue(
                    "error",
                    "align-mismatch",
                    f"{match} of {len(values)} features differs by {spread:.2f} mm "
                    f"(tolerance {rule_tolerance}): {detail}",
                )
            )
    return issues


def near_misses(
    features: dict[str, Feature], tolerance: float, ignore_exact: bool = True
) -> list[Issue]:
    """Edges of different panels that are close but not equal: the ones that look wrong."""
    issues: list[Issue] = []
    for match in EDGES:
        values = [
            (ref, feature.values[match])
            for ref, feature in features.items()
            if feature.kind in ("axes", "anchor") and match in feature.values
        ]
        values.sort(key=lambda item: item[1])
        group: list[tuple[str, float]] = []
        for item in [*values, ("", float("inf"))]:
            if group and item[1] - group[0][1] <= tolerance:  # spread from the first, not chained
                group.append(item)
                continue
            panels = {ref.split(".")[0] for ref, _ in group}
            spread = group[-1][1] - group[0][1] if group else 0.0
            if len(panels) > 1 and (spread > 1e-6 or not ignore_exact):
                level = "warning" if spread > 1e-6 else "info"
                detail = ", ".join(f"{ref} {value:.2f}" for ref, value in group)
                issues.append(
                    Issue(
                        level,
                        "align-near" if spread > 1e-6 else "align-exact",
                        f"{match}: {len(group)} features within {spread:.2f} mm: {detail}",
                    )
                )
            group = [item] if item[0] else []
    return issues


def rule_lines(features: dict[str, Feature], rules: list[dict[str, Any]]) -> dict[str, list[float]]:
    """Page coordinates to draw as rules: ``{"x": [...], "y": [...]}``."""
    lines: dict[str, list[float]] = {"x": [], "y": []}
    for rule in rules:
        match = str(rule.get("match", "bottom"))
        axis = "x" if match in ("left", "right") else "y"
        for ref in rule.get("of") or []:
            feature = features.get(ref)
            value = _value(feature, match) if feature else None
            if value is not None:
                lines[axis].append(round(value, 3))
    return {axis: sorted(set(values)) for axis, values in lines.items()}
