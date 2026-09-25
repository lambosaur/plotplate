"""Compute panel boxes from constraints instead of numbers.

A layout can state relations between panels (this row shares a baseline, these panels
have equal widths, leave 4 mm between them) and let a solver find the boxes. The relations
survive edits: changing the page width, a gap or one panel's height re-solves the rest,
instead of leaving the near-misses that hand-written numbers accumulate.

The solver is Cassowary (`kiwisolver`), which matplotlib already installs, so this costs
no dependency. Constraints are linear, and each can be `required` (default) or a
preference (`strong`, `medium`, `weak`) that bends when it conflicts.

```yaml
page: {width: double, height: solve}   # height can be solved from the constraints
constraints:
  defaults: {gap: 4}
  rules:
    - row: {panels: [A, B], top: 0, height: 55, equal: true}
    - row: {panels: [C], height: 42}
    - row: {panels: [D, E], equal: true, bottom: page}
    - column: {panels: [A, C, D], left: 0}
    - align: {edge: right, of: [B, C, E]}
    - size: {panel: C, height: 42}
    - aspect: {panel: B, ratio: 1.6}          # width = ratio * height
    - pin: {panel: A, left: 0, top: 0}
    - gap: {after: A, before: B, value: 4}    # horizontal
    - gap: {below: A, above: C, value: 4}     # vertical
```

`row` and `column` are shorthand that expand into those primitives.
"""

from __future__ import annotations

from itertools import pairwise
from typing import Any

from kiwisolver import Solver, UnsatisfiableConstraint, Variable

from .geometry import Rect

EDGES = ("left", "right", "top", "bottom")
STRENGTHS = ("required", "strong", "medium", "weak")
MIN_SIZE_MM = 5.0


class ConstraintError(ValueError):
    """A constraint set that cannot be satisfied, or that is written wrongly."""


class _Page:
    """Variables of one page: every panel's edges, plus the page size."""

    def __init__(self, names: list[str], width: float, height: float | None) -> None:
        self.solver = Solver()
        self.panels = {name: {edge: Variable(f"{name}.{edge}") for edge in EDGES} for name in names}
        self.width = Variable("page.width")
        self.height = Variable("page.height")
        self.require(self.width == width)
        if height is not None:
            self.require(self.height == height)
        for edges in self.panels.values():
            self.require(edges["right"] - edges["left"] >= MIN_SIZE_MM)
            self.require(edges["bottom"] - edges["top"] >= MIN_SIZE_MM)
            self.require(edges["left"] >= 0)
            self.require(edges["top"] >= 0)
            self.require(self.width - edges["right"] >= 0)
            self.require(self.height - edges["bottom"] >= 0)
            # Without other constraints, prefer a panel that fills the page: it makes an
            # under-constrained layout obvious instead of collapsing it to the minimum.
            self.prefer(edges["right"] - edges["left"] == self.width, "weak")
            self.prefer(edges["bottom"] - edges["top"] == self.height, "weak")

    def require(self, constraint: Any) -> None:
        """Add a constraint that must hold."""
        try:
            self.solver.addConstraint(constraint | "required")
        except UnsatisfiableConstraint as exc:
            raise ConstraintError(f"constraints conflict: {constraint}") from exc

    def prefer(self, constraint: Any, strength: str) -> None:
        """Add a constraint that bends when it conflicts with a stronger one."""
        self.solver.addConstraint(constraint | strength)

    def edge(self, panel: str, edge: str) -> Variable:
        """The variable of one panel edge."""
        if panel not in self.panels:
            raise ConstraintError(f"unknown panel {panel!r} in constraints")
        if edge not in EDGES:
            raise ConstraintError(f"unknown edge {edge!r}; use one of {EDGES}")
        return self.panels[panel][edge]

    def value(self, expression: Any) -> Variable | float:
        """Resolve ``page`` and numbers used as an edge position."""
        if expression == "page":
            return self.width  # replaced by the caller for vertical edges
        return float(expression)


def _rule_align(page: _Page, spec: dict[str, Any], put: Any, _defaults: dict[str, Any]) -> None:
    """Same edge for several panels."""
    edge, panels = str(spec["edge"]), [str(p) for p in spec["of"]]
    for other in panels[1:]:
        put(page.edge(other, edge) == page.edge(panels[0], edge))


def _rule_equal(page: _Page, spec: dict[str, Any], put: Any, _defaults: dict[str, Any]) -> None:
    """Same width (default) or height for several panels."""
    what, panels = str(spec.get("what", "width")), [str(p) for p in spec["of"]]
    if what not in {"width", "height"}:
        raise ConstraintError(f"equal.what must be width or height, got {what!r}")
    low, high = ("left", "right") if what == "width" else ("top", "bottom")
    first: Any = page.edge(panels[0], high) - page.edge(panels[0], low)
    for other in panels[1:]:
        put((page.edge(other, high) - page.edge(other, low)) == first)


def _rule_gap(page: _Page, spec: dict[str, Any], put: Any, defaults: dict[str, Any]) -> None:
    """Space between two panels, horizontally (after/before) or vertically (below/above)."""
    value = float(spec.get("value", defaults.get("gap", 0.0)))
    if "after" in spec:
        put(page.edge(str(spec["before"]), "left") - page.edge(str(spec["after"]), "right") == value)
    elif "below" in spec:
        put(page.edge(str(spec["above"]), "top") - page.edge(str(spec["below"]), "bottom") == value)
    else:
        raise ConstraintError("gap needs after/before (horizontal) or below/above (vertical)")


def _rule_size(page: _Page, spec: dict[str, Any], put: Any, _defaults: dict[str, Any]) -> None:
    """Fixed width and/or height of one panel."""
    panel = str(spec["panel"])
    if "width" in spec:
        put(page.edge(panel, "right") - page.edge(panel, "left") == float(spec["width"]))
    if "height" in spec:
        put(page.edge(panel, "bottom") - page.edge(panel, "top") == float(spec["height"]))


def _rule_aspect(page: _Page, spec: dict[str, Any], put: Any, _defaults: dict[str, Any]) -> None:
    """Width / height ratio of one panel."""
    panel, ratio = str(spec["panel"]), float(spec["ratio"])
    width: Any = page.edge(panel, "right") - page.edge(panel, "left")
    height: Any = page.edge(panel, "bottom") - page.edge(panel, "top")
    put(width == ratio * height)


def _rule_pin(page: _Page, spec: dict[str, Any], put: Any, _defaults: dict[str, Any]) -> None:
    """One or more edges of a panel at a number, or at the page edge (``page``)."""
    spec = dict(spec)
    panel = str(spec.pop("panel"))
    for edge, value in spec.items():
        limit = page.width if edge in ("left", "right") else page.height
        put(page.edge(panel, edge) == (limit if value == "page" else float(value)))


_HANDLERS = {
    "align": _rule_align,
    "equal": _rule_equal,
    "gap": _rule_gap,
    "size": _rule_size,
    "aspect": _rule_aspect,
    "pin": _rule_pin,
}


def _add(page: _Page, rule: dict[str, Any], defaults: dict[str, Any]) -> None:
    """Translate one primitive rule into solver constraints."""
    strength = str(rule.get("strength", "required"))
    if strength not in STRENGTHS:
        raise ConstraintError(f"unknown strength {strength!r}; use one of {STRENGTHS}")

    def put(constraint: Any) -> None:
        if strength == "required":
            page.require(constraint)
        else:
            page.prefer(constraint, strength)

    for key, handler in _HANDLERS.items():
        if key in rule:
            handler(page, dict(rule[key]), put, defaults)
            return
    raise ConstraintError(f"unknown rule {sorted(rule)}; see docs/constraints.md")


def _sequence_pins(
    spec: dict[str, Any], panels: list[str], along: tuple[str, str], across: tuple[str, str],
    along_size: str, across_size: str, fill: bool,
) -> list[dict[str, Any]]:  # fmt: skip
    """The pins and sizes a row/column spec asks for."""
    rules: list[dict[str, Any]] = []
    for edge in across:  # shared by the whole row, so pinning the first panel is enough
        if edge in spec:
            rules.append({"pin": {"panel": panels[0], edge: spec.pop(edge)}})
    if across_size in spec:
        rules.append({"size": {"panel": panels[0], across_size: spec.pop(across_size)}})
    if along[0] in spec:
        rules.append({"pin": {"panel": panels[0], along[0]: spec.pop(along[0])}})
    if along[1] in spec:
        rules.append({"pin": {"panel": panels[-1], along[1]: spec.pop(along[1])}})
    if along_size in spec:
        value = spec.pop(along_size)
        rules += [{"size": {"panel": panel, along_size: value}} for panel in panels]
    if fill:
        rules.append({"pin": {"panel": panels[0], along[0]: 0}})
        rules.append({"pin": {"panel": panels[-1], along[1]: "page"}})
    return rules


def _sequence_rules(
    spec: dict[str, Any], horizontal: bool, defaults: dict[str, Any]
) -> list[dict[str, Any]]:
    """Primitive rules of one row (``horizontal``) or column."""
    panels = [str(p) for p in spec.pop("panels")]
    if not panels:
        raise ConstraintError("a row/column needs panels")
    gap = float(spec.pop("gap", defaults.get("gap", 0.0)))
    equal = bool(spec.pop("equal", False))
    fill = bool(spec.pop("fill", False))
    along = ("left", "right") if horizontal else ("top", "bottom")
    across = ("top", "bottom") if horizontal else ("left", "right")
    along_size, across_size = ("width", "height") if horizontal else ("height", "width")

    rules: list[dict[str, Any]] = [
        {
            "gap": ({"after": a, "before": b} if horizontal else {"below": a, "above": b})
            | {"value": gap}
        }
        for a, b in pairwise(panels)
    ]
    if len(panels) > 1:
        rules += [{"align": {"edge": edge, "of": panels}} for edge in across]
        if equal:
            rules.append({"equal": {"what": along_size, "of": panels}})
    rules += _sequence_pins(spec, panels, along, across, along_size, across_size, fill)
    if spec:
        raise ConstraintError(f"unknown keys {sorted(spec)} in a {'row' if horizontal else 'column'}")
    return rules


def _expand(rule: dict[str, Any], defaults: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand the ``row``/``column`` shorthands into primitive rules.

    A row places its panels left to right with a gap, shares their top and bottom edges,
    and accepts pins for the row as a whole (``top``, ``bottom``, ``height``) or for its
    ends (``left`` on the first panel, ``right`` on the last). A column is the transpose.
    """
    for key, horizontal in (("row", True), ("column", False)):
        if key in rule:
            return _sequence_rules(dict(rule[key]), horizontal, defaults)
    return [rule]


def solve_boxes(
    panel_names: list[str],
    constraints: dict[str, Any],
    width: float,
    height: float | None,
    pinned: dict[str, Rect] | None = None,
) -> tuple[dict[str, Rect], float]:
    """Boxes of every panel, and the page height (solved when it was not given).

    Args:
        panel_names: every panel of the layout.
        constraints: the layout's ``constraints`` mapping (``defaults`` and ``rules``).
        width: page width in mm.
        height: page height in mm, or ``None`` to solve it.
        pinned: panels that already have an explicit box; they constrain the rest.

    Raises:
        ConstraintError: the rules conflict, refer to unknown panels, or are malformed.
    """
    page = _Page(panel_names, width, height)
    for name, box in (pinned or {}).items():
        for edge, value in (
            ("left", box.left), ("top", box.top), ("right", box.right), ("bottom", box.bottom)
        ):  # fmt: skip
            page.require(page.edge(name, edge) == value)
    defaults = dict(constraints.get("defaults") or {})
    for rule in constraints.get("rules") or []:
        for primitive in _expand(dict(rule), defaults):
            _add(page, primitive, defaults)
    page.solver.updateVariables()

    boxes = {}
    for name, edges in page.panels.items():
        rect = Rect.from_edges(
            round(edges["left"].value(), 3),
            round(edges["top"].value(), 3),
            round(edges["right"].value(), 3),
            round(edges["bottom"].value(), 3),
        )
        boxes[name] = rect
    return boxes, round(page.height.value(), 3)


def unconstrained(boxes: dict[str, Rect], width: float, height: float) -> list[str]:
    """Panels whose box looks like the solver had nothing to go on."""
    loose = []
    for name, box in boxes.items():
        at_minimum = box.w <= MIN_SIZE_MM + 1e-6 or box.h <= MIN_SIZE_MM + 1e-6
        fills_page = abs(box.w - width) < 1e-6 and abs(box.h - height) < 1e-6
        if at_minimum or fills_page:
            loose.append(name)
    return loose
