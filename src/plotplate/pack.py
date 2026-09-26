"""Grow the panels until the white space between them is the gutter you asked for.

A layout read back from an existing figure has its panels wherever they happened to be:
gutters of 7 mm next to gutters of 2 mm, a ragged right edge, sometimes boxes that overlap.
Nothing is wrong with the arrangement -- the panels are in the right order and the right
rows -- but the space is badly used, and every millimetre of white space is a millimetre
not spent on the data.

``optimize`` keeps the arrangement and re-spends the space:

1. the panel edges are clustered into shared boundaries, which turns the panels into spans
   over a grid (a panel may span several columns or rows; a panel nested inside another is
   recorded as an inset and rides along with its host);
2. every gutter of that grid is set to one gap, and the rest of the width (and height) is
   given back to the panels;
3. no panel may change size by more than a factor you choose -- 1.2 by default, so a panel
   can grow by 20 % but not become a different figure. Panels can also be frozen, or kept
   at their aspect ratio.

The solver is Cassowary (``kiwisolver``, a matplotlib dependency), the same one
:mod:`plotplate.solve` uses. The objective is stated as constraints rather than as a cost:
the boundaries must add up to the target width (that *is* "no wasted space"), the gutters
are fixed, and each strip prefers a single overall scale, which is what spreads the
recovered space evenly instead of giving it all to one panel.

What this does not do: it never reorders panels, never changes what is drawn inside them,
and never decides that a panel should be wider *relative to* its neighbour -- that is a
judgement about content, and it stays yours (``--freeze``, ``--keep-aspect``, or an edited
layout). Axes rectangles move with their panel: the margins that hold tick labels keep
their width in millimetres, and the extra space goes to the plotting areas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

from kiwisolver import Solver, UnsatisfiableConstraint, Variable

from .geometry import Rect
from .layout import Layout, area_section

MIN_STRIP_MM = 2.0
AXES = ("x", "y")


class PackError(ValueError):
    """The layout cannot be optimized as asked: not a grid, or no solution in the limits."""


def _boundaries(values: list[float], tolerance: float) -> list[float]:
    """Sorted edge positions, with values within ``tolerance`` of each other merged."""
    reps: list[float] = []
    group: list[float] = []
    for value in sorted(values):
        if group and value - group[-1] > tolerance:
            reps.append(sum(group) / len(group))
            group = []
        group.append(value)
    if group:
        reps.append(sum(group) / len(group))
    return reps


def _overlaps(a: tuple[float, float], b: tuple[float, float]) -> bool:
    """Whether two intervals share more than a point."""
    return min(a[1], b[1]) - max(a[0], b[0]) > 0


def _index(value: float, reps: list[float]) -> int:
    """Which boundary an edge belongs to."""
    return min(range(len(reps)), key=lambda i: abs(reps[i] - value))


@dataclass
class Grid:
    """The panels of a layout as spans over their shared edges.

    ``spans[name]`` is ``(i0, i1, j0, j1)``: the panel runs from boundary ``xs[i0]`` to
    ``xs[i1]`` horizontally and ``ys[j0]`` to ``ys[j1]`` vertically. The bands between two
    consecutive boundaries are *strips*; a strip no panel spans is a gutter.
    """

    xs: list[float]
    ys: list[float]
    spans: dict[str, tuple[int, int, int, int]]
    insets: dict[str, str] = field(default_factory=dict)

    def boundaries(self, axis: str) -> list[float]:
        """The shared edge positions along ``axis``."""
        return self.xs if axis == "x" else self.ys

    def strips(self, axis: str) -> list[tuple[float, bool]]:
        """Each strip along ``axis`` as ``(current size, is a gutter)``.

        A strip is a gutter when no panel covers it (an empty column), and also when it
        separates two panels that face each other -- even if a panel spanning the whole width
        covers it, in which case that panel's width simply includes the gutter.
        """
        reps = self.boundaries(axis)
        low, high = (0, 1) if axis == "x" else (2, 3)
        across = (2, 3) if axis == "x" else (0, 1)
        spans = list(self.spans.values())
        occupied = {i for span in spans for i in range(span[low], span[high])}
        strips = []
        for i in range(len(reps) - 1):
            separates = any(
                one[high] == i
                and other[low] == i + 1
                and _overlaps((one[across[0]], one[across[1]]), (other[across[0]], other[across[1]]))
                for one in spans
                for other in spans
            )
            strips.append((reps[i + 1] - reps[i], i not in occupied or separates))
        return strips

    def span(self, name: str, axis: str) -> tuple[int, int]:
        """The panel's first and last boundary index along ``axis``."""
        i0, i1, j0, j1 = self.spans[name]
        return (i0, i1) if axis == "x" else (j0, j1)


def read_grid(boxes: dict[str, Rect], tolerance: float = 1.0) -> Grid:
    """Recover the grid a set of panel boxes implies.

    Args:
        boxes: panel boxes in layout millimetres.
        tolerance: edges this close (mm) are treated as one shared boundary.

    Raises:
        PackError: two panels overlap without one being nested in the other, so the boxes
            do not describe a grid at all (a pinwheel, or panels that were mis-detected).
    """
    insets: dict[str, str] = {}
    for name, box in boxes.items():
        hosts = [
            other
            for other, host in boxes.items()
            if other != name and host.contains(box, tol=tolerance) and host.w * host.h > box.w * box.h
        ]
        if hosts:
            insets[name] = min(hosts, key=lambda n: boxes[n].w * boxes[n].h)
    for name in list(insets):  # an inset of an inset rides along with the outermost panel
        host = insets[name]
        while host in insets:
            host = insets[host]
        insets[name] = host
    outer = {name: box for name, box in boxes.items() if name not in insets}
    if not outer:
        raise PackError("every panel is nested inside another one; nothing to arrange")

    xs = _boundaries([v for b in outer.values() for v in (b.left, b.right)], tolerance)
    ys = _boundaries([v for b in outer.values() for v in (b.top, b.bottom)], tolerance)
    spans = {
        name: (_index(b.left, xs), _index(b.right, xs), _index(b.top, ys), _index(b.bottom, ys))
        for name, b in outer.items()
    }
    for name, (i0, i1, j0, j1) in spans.items():
        if i1 <= i0 or j1 <= j0:
            raise PackError(
                f"panel {name} has no size at tolerance {tolerance} mm (its edges merge into one "
                "boundary); lower --tolerance"
            )
    clashes = [
        (a, b) for a, b in combinations(sorted(spans), 2) if _cells_overlap(spans[a], spans[b])
    ]
    if clashes:
        pairs = ", ".join(f"{a}/{b}" for a, b in clashes)
        raise PackError(
            f"these panels overlap without being nested: {pairs}. Their boxes do not form a grid, "
            "so there is no white space to redistribute: merge them into one panel "
            "(`plotplate merge`), or fix the boxes first"
        )
    return Grid(xs, ys, spans, insets)


def _cells_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    """Whether two spans share a cell of the grid."""
    return min(a[1], b[1]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[2], b[2])


def _facing(rect: Rect, others: list[Rect], axis: str) -> tuple[list[float], list[float]]:
    """Where the panels facing ``rect`` along ``axis`` stop and start.

    Only panels that overlap ``rect`` in the other direction count as facing it: they are the
    ones whose position limits how far it may grow.
    """
    if axis == "x":
        low, high, span = rect.left, rect.right, (rect.top, rect.bottom)
        sides = [((o.left, o.right), (o.top, o.bottom)) for o in others]
    else:
        low, high, span = rect.top, rect.bottom, (rect.left, rect.right)
        sides = [((o.top, o.bottom), (o.left, o.right)) for o in others]
    before = [end for (_start, end), across in sides if end <= low and _overlaps(span, across)]
    after = [start for (start, _end), across in sides if start >= high and _overlaps(span, across)]
    return before, after


def fill_white_space(
    boxes: dict[str, Rect], width: float, height: float, gap: float, stretch: float
) -> dict[str, Rect]:
    """Grow every panel into the white space beside it, within the stretch limit.

    Each side moves to the middle of the gutter towards the nearest panel facing it (minus
    half the gap), or to the edge of the figure when nothing faces it. The growth is then
    clamped so no panel becomes more than ``stretch`` times its size, sharing what is allowed
    between the sides that asked for it.

    This is the step that recovers a hole -- a narrow panel next to a wide one, a ragged right
    edge, a short last row. The grid solve that follows can only re-spend space that is already
    inside a box, because it moves shared boundaries and never changes which cells a panel
    covers.
    """
    filled = {}
    for name, rect in boxes.items():
        others = [other for key, other in boxes.items() if key != name]
        wanted = {}
        for axis, limit in (("x", width), ("y", height)):
            before, after = _facing(rect, others, axis)
            low, high = (rect.left, rect.right) if axis == "x" else (rect.top, rect.bottom)
            start = (max(before) + low) / 2 + gap / 2 if before else 0.0
            end = (min(after) + high) / 2 - gap / 2 if after else limit
            grow = [max(0.0, low - start), max(0.0, end - high)]
            allowed = (high - low) * (stretch - 1)
            asked = sum(grow)
            if asked > allowed:
                share = max(0.0, allowed) / asked if asked else 0.0
                grow = [g * share for g in grow]
            wanted[axis] = (low - grow[0], high + grow[1])
        filled[name] = Rect.from_edges(wanted["x"][0], wanted["y"][0], wanted["x"][1], wanted["y"][1])
    return filled


@dataclass(frozen=True)
class Target:
    """What the optimized layout must achieve."""

    gap: float = 4.0
    stretch: float = 1.2  # a panel may become this many times bigger
    shrink: float = 1.2  # ... and this many times smaller
    width: float | None = None  # None: keep the current width
    height: float | None = None  # None: let it follow the width, to keep the proportions
    freeze: tuple[str, ...] = ()
    keep_aspect: tuple[str, ...] = ()
    fill: bool = True  # first grow the panels into the white space beside them


@dataclass
class Report:
    """What the optimization changed, in the numbers a user needs to judge it."""

    width: float
    height: float
    before: dict[str, Rect]
    after: dict[str, Rect]
    occupancy: tuple[float, float]  # share of the figure area covered by panels, before/after
    gutters: tuple[tuple[float, float], tuple[float, float]]  # (min, max) gutter, before/after
    overlaps: int  # overlapping pairs in the input
    guides: tuple[int, int]  # named shared edges before/after
    notes: list[str] = field(default_factory=list)

    def factors(self, name: str) -> tuple[float, float]:
        """How much panel ``name`` was stretched horizontally and vertically."""
        old, new = self.before[name], self.after[name]
        return (new.w / old.w, new.h / old.h)


def _expression(variables: list[Variable]) -> Any:
    """Sum of variables, built without starting from the integer 0."""
    total: Any = variables[0]
    for variable in variables[1:]:
        total = total + variable
    return total


def _infeasible(strips: list[tuple[float, bool]], total: float, target: Target) -> str | None:
    """Why the strips of one axis cannot add up to ``total``, or ``None`` when they can."""
    content = sum(size for size, gutter in strips if not gutter)
    gutters = sum(1 for _, gutter in strips if gutter)
    room = total - target.gap * gutters
    if room <= 0:
        return f"{gutters} gutters of {target.gap:g} mm leave no room in {total:g} mm"
    factor = room / content
    if factor > target.stretch + 1e-6:
        return (
            f"the panels would have to grow {factor:.2f}x to fill {total:g} mm "
            f"(limit {target.stretch:.2f}x): raise --max-stretch, or lower --gap"
        )
    if factor < 1 / target.shrink - 1e-6:
        return (
            f"the panels would have to shrink to {factor:.2f}x to fit in {total:g} mm "
            f"(limit {1 / target.shrink:.2f}x): raise --max-shrink"
        )
    return None


def _strip_variables(
    solver: Solver, grid: Grid, target: Target, scale: dict[str, Variable]
) -> dict[str, list[Variable]]:
    """One variable per strip: gutters fixed at the gap, panel strips sharing one scale."""
    strips: dict[str, list[Variable]] = {}
    totals = {"x": target.width, "y": target.height}
    for axis in AXES:
        bands = grid.strips(axis)
        variables = [Variable(f"{axis}{i}") for i in range(len(bands))]
        strips[axis] = variables
        for variable, (size, gutter) in zip(variables, bands, strict=True):
            if gutter:
                solver.addConstraint((variable == target.gap) | "required")
            else:
                solver.addConstraint((variable >= MIN_STRIP_MM) | "required")
                # One scale per axis: the recovered space is shared out in proportion to
                # what each strip already had, instead of landing on one panel.
                solver.addConstraint((variable == size * scale[axis]) | "medium")
        # Nothing else fixes the overall scale when no total is given: keep the current size.
        solver.addConstraint((scale[axis] == 1.0) | "weak")
        total = totals[axis]
        if total is not None:
            solver.addConstraint((_expression(variables) == total) | "required")
    return strips


def _panel_limits(
    solver: Solver,
    grid: Grid,
    limits: dict[str, Rect],
    strips: dict[str, list[Variable]],
    target: Target,
) -> None:
    """How far each panel may be distorted, and which ones may not be.

    ``limits`` holds the panel boxes the limits are measured against: the *original* ones, so
    that growing into the white space first does not buy a second helping of stretch.
    """
    for name in grid.spans:
        old = limits[name]
        sizes = {}
        for axis, extent in (("x", old.w), ("y", old.h)):
            low, high = grid.span(name, axis)
            size = _expression(strips[axis][low:high])
            sizes[axis] = size
            if name in target.freeze:
                solver.addConstraint((size == extent) | "required")
            else:
                solver.addConstraint((size <= extent * target.stretch) | "required")
                solver.addConstraint((size >= extent / target.shrink) | "required")
        if name in target.keep_aspect and name not in target.freeze:
            solver.addConstraint((sizes["x"] == (old.w / old.h) * sizes["y"]) | "required")


def _reachable(grid: Grid, target: Target, current_width: float) -> tuple[Target, list[str]]:
    """The target with sizes that can actually be reached, and what had to give.

    A size the user asked for explicitly is a promise: if the limits cannot deliver it, that is
    an error, with the factor that would. The current width, which is only the default, bends
    instead: the figure then keeps its panels and ends up narrower or shorter, and says so.

    Raises:
        PackError: an explicitly requested width or height is out of reach.
    """
    totals = {"x": current_width if target.width is None else target.width, "y": target.height}
    explicit = {"x": target.width is not None, "y": target.height is not None}
    notes = []
    for axis in AXES:
        wanted = totals[axis]
        if wanted is None:
            continue
        reason = _infeasible(grid.strips(axis), wanted, target)
        if reason is None:
            continue
        if explicit[axis]:
            raise PackError(f"{axis}: {reason}")
        notes.append(
            f"the figure could not keep its {'width' if axis == 'x' else 'height'} of "
            f"{wanted:g} mm: {reason}"
        )
        totals[axis] = None
    reached = Target(
        target.gap, target.stretch, target.shrink, totals["x"], totals["y"],
        target.freeze, target.keep_aspect, target.fill,
    )  # fmt: skip
    return reached, notes


def _solve(grid: Grid, limits: dict[str, Rect], target: Target) -> dict[str, list[float]]:
    """New boundary positions along each axis, with the limits measured against ``limits``."""
    solver = Solver()
    scale = {axis: Variable(f"scale.{axis}") for axis in AXES}
    strips = _strip_variables(solver, grid, target, scale)
    if target.height is None:
        # Nothing pins the height: follow the width, so the figure keeps its proportions.
        solver.addConstraint((scale["y"] == scale["x"]) | "strong")
    _panel_limits(solver, grid, limits, strips, target)
    try:
        solver.updateVariables()
    except UnsatisfiableConstraint as exc:  # pragma: no cover - guarded by _infeasible
        raise PackError(f"no arrangement satisfies the limits: {exc}") from exc

    positions = {}
    for axis in AXES:
        edges = [0.0]
        for variable in strips[axis]:
            edges.append(edges[-1] + variable.value())
        positions[axis] = [round(value, 3) for value in edges]
    return positions


def _map_value(value: float, old: tuple[float, float], new: tuple[float, float]) -> float:
    """Map a coordinate from one interval to another (a shift when the interval is a point)."""
    if old[1] - old[0] <= 1e-9:
        return new[0] + (value - old[0])
    return new[0] + (value - old[0]) * (new[1] - new[0]) / (old[1] - old[0])


def _map_axes(old_box: Rect, new_box: Rect, rects: list[Rect]) -> list[Rect]:
    """Where a panel's axes rectangles go when its box changes size.

    The distance from the panel edge to the outermost axes edge is kept: that space holds
    tick labels, axis titles and the panel letter, which stay the same size in millimetres
    when the panel grows. Everything between those outer edges is stretched, so the extra
    space ends up in the plotting areas (and the gaps inside a panel grow only a little).
    """
    if not rects:
        return []
    bands = {}
    for axis, lows, highs, old_lo, old_hi, new_lo, new_hi in (
        ("x", [r.left for r in rects], [r.right for r in rects],
         old_box.left, old_box.right, new_box.left, new_box.right),
        ("y", [r.top for r in rects], [r.bottom for r in rects],
         old_box.top, old_box.bottom, new_box.top, new_box.bottom),
    ):  # fmt: skip
        inner = (min(lows), max(highs))
        before, after = inner[0] - old_lo, old_hi - inner[1]
        target = (new_lo + before, new_hi - after)
        if target[1] - target[0] < MIN_STRIP_MM:  # margins alone no longer fit: scale instead
            target = (
                _map_value(inner[0], (old_lo, old_hi), (new_lo, new_hi)),
                _map_value(inner[1], (old_lo, old_hi), (new_lo, new_hi)),
            )
        bands[axis] = (inner, target)
    return [
        Rect.from_edges(
            _map_value(r.left, *bands["x"]),
            _map_value(r.top, *bands["y"]),
            _map_value(r.right, *bands["x"]),
            _map_value(r.bottom, *bands["y"]),
        )
        for r in rects
    ]


def _occupancy(boxes: dict[str, Rect], width: float, height: float) -> float:
    """Share of the figure area covered by panels (insets counted once)."""
    return sum(box.w * box.h for box in boxes.values()) / (width * height)


def _gutter_range(grid: Grid, positions: dict[str, list[float]] | None) -> tuple[float, float]:
    """Smallest and largest gutter of the grid: as it is now, or at ``positions``."""
    sizes = []
    for axis in AXES:
        for i, (size, gutter) in enumerate(grid.strips(axis)):
            if not gutter:
                continue
            sizes.append(size if positions is None else positions[axis][i + 1] - positions[axis][i])
    return (min(sizes), max(sizes)) if sizes else (0.0, 0.0)


def _union_length(intervals: list[tuple[float, float]]) -> float:
    """Total length covered by a set of intervals, counting an overlap once."""
    total, reach = 0.0, None
    for start, end in sorted(intervals):
        if reach is None or start > reach:
            total += end - start
            reach = end
        elif end > reach:
            total += end - reach
            reach = end
    return total


def _rows(grid: Grid) -> list[tuple[int, int]]:
    """Rows of the grid as ``(first, last)`` boundary indices: runs between gutters."""
    rows, start = [], None
    bands = grid.strips("y")
    for index, (_size, gutter) in enumerate(bands):
        if gutter:
            if start is not None:
                rows.append((start, index))
                start = None
        elif start is None:
            start = index
    if start is not None:
        rows.append((start, len(bands)))
    return rows


def _row_slack(
    boxes: dict[str, Rect], grid: Grid, positions: dict[str, list[float]], width: float, gap: float
) -> list[tuple[float, float, float, list[str]]]:
    """Rows with width to spare: ``(top, bottom, empty mm, the panels in the row)``.

    A row keeps empty space when its panels are not allowed to grow enough to fill the width.
    That is the stretch limit doing its job -- how much distortion is acceptable is the user's
    call -- so the result is reported, not silently worked around.
    """
    rows = []
    for first, last in _rows(grid):
        top, bottom = positions["y"][first], positions["y"][last]
        inside = [
            (name, box)
            for name, box in boxes.items()
            if box.top < bottom - 0.01 and box.bottom > top + 0.01
        ]
        if not inside:
            continue
        covered = _union_length([(box.left, box.right) for _name, box in inside])
        empty = width - covered - gap * (len(inside) - 1)
        if empty > 1.0:
            rows.append((top, bottom, empty, sorted(name for name, _box in inside)))
    return rows


def _place(
    data: dict[str, Any], layout: Layout, boxes: dict[str, Rect], new_boxes: dict[str, Rect],
    tolerance: float,
) -> int:  # fmt: skip
    """Write the new boxes into ``data``, move the axes with them, and re-derive the guides.

    Returns how many guides were found again: shared axes edges that still coincide.
    """
    from .pdfimport import _extract_guides

    raw_panels = data.get("panels") or {}
    for name, box in new_boxes.items():
        entry = raw_panels[name]
        axes = layout.panels[name].axes
        mapped = _map_axes(boxes[name], box, [spec.region for spec in axes.values()])
        entry["box"] = box.to_list()
        for ax_name, rect in zip(axes, mapped, strict=True):
            entry.setdefault("axes", {}).setdefault(ax_name, {})["box"] = rect.to_list()
    data.pop("guides", None)
    found = _extract_guides(raw_panels, max(0.1, tolerance / 2))
    if found["x"] or found["y"]:
        data["guides"] = found
    return len(found["x"]) + len(found["y"])


def _notes(report: Report, grid: Grid, positions: dict[str, list[float]], target: Target) -> None:
    """Add what the user has to know to judge the result: insets, guides, rows left short."""
    if grid.insets:
        report.notes.append(
            "insets kept their place inside their host: "
            + ", ".join(f"{k} in {v}" for k, v in sorted(grid.insets.items()))
        )
    if report.guides[1] < report.guides[0]:
        report.notes.append(
            f"{report.guides[0] - report.guides[1]} shared axes edges no longer coincide: panels "
            "in different rows grew by different factors; check `plotplate align` after rebuilding"
        )
    for top, bottom, empty, names in _row_slack(
        report.after, grid, positions, report.width, target.gap
    ):
        covered = report.width - empty - target.gap * (len(names) - 1)
        report.notes.append(
            f"the row at {top:.0f}-{bottom:.0f} mm still has {empty:.0f} mm of width to spare: "
            f"{', '.join(names)} hit the {target.stretch:.2f}x limit; about "
            f"--max-stretch {target.stretch * (covered + empty) / covered:.2f} would fill it"
        )
    if report.occupancy[1] <= report.occupancy[0] + 0.005:
        report.notes.append("the panels already used the space: nothing much to gain here")


def optimize(layout: Layout, target: Target, tolerance: float = 1.0) -> tuple[dict[str, Any], Report]:
    """Return an optimized copy of ``layout`` (as a raw mapping) and what changed.

    Args:
        layout: the layout to rearrange; its boxes are read as they resolve.
        target: the gap, the distortion limits and the size to fill.
        tolerance: panel edges this close (mm) count as one shared boundary.

    Raises:
        PackError: the boxes do not form a grid, or the limits leave no solution.
    """
    data = layout.resolved()
    boxes = {name: spec.box for name, spec in layout.panels.items()}
    filled = (
        fill_white_space(boxes, layout.width, layout.height, target.gap, target.stretch)
        if target.fill
        else boxes
    )
    grid = read_grid(filled, tolerance)
    unknown = (set(target.freeze) | set(target.keep_aspect)) - set(grid.spans)
    if unknown:
        raise PackError(f"--freeze/--keep-aspect name panels that are not placed: {sorted(unknown)}")

    target, notes = _reachable(grid, target, layout.width)
    positions = _solve(grid, boxes, target)
    new_boxes: dict[str, Rect] = {}
    for name in grid.spans:
        i0, i1 = grid.span(name, "x")
        j0, j1 = grid.span(name, "y")
        new_boxes[name] = Rect.from_edges(
            positions["x"][i0], positions["y"][j0], positions["x"][i1], positions["y"][j1]
        )
    for name, host in grid.insets.items():  # an inset keeps its place inside its host
        new_boxes[name] = _map_axes(filled[host], new_boxes[host], [boxes[name]])[0]

    width, height = positions["x"][-1], positions["y"][-1]
    area = area_section(data)
    area["width"] = round(width, 2)
    area["height"] = round(height, 2)
    guides = (
        len(layout.guides["x"]) + len(layout.guides["y"]),
        _place(data, layout, boxes, new_boxes, tolerance),
    )
    report = Report(
        width=width,
        height=height,
        before=boxes,
        after=new_boxes,
        occupancy=(
            _occupancy(boxes, layout.width, layout.height),
            _occupancy(new_boxes, width, height),
        ),
        gutters=(_gutter_range(grid, None), _gutter_range(grid, positions)),
        overlaps=sum(
            1
            for a, b in combinations(sorted(boxes), 2)
            if boxes[a].intersection_area(boxes[b]) > 0.01
        ),
        guides=guides,
    )
    report.notes.extend(notes)
    _notes(report, grid, positions, target)
    return data, report
