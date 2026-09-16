"""Checks on a finished panel figure: size, fonts, clipping, overlaps, line widths.

Everything is measured on what matplotlib actually draws: the checks wrap ``Text.draw``
and ``Line2D.draw`` during one render, so ticks outside the view limits or empty
titles never produce false alarms.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from matplotlib.lines import Line2D
from matplotlib.spines import Spine
from matplotlib.text import Text
from matplotlib.transforms import Bbox

from .geometry import MM_PER_INCH, Rect
from .layout import Issue
from .style import first_available_font

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

SIZE_TOL_MM = 0.05
POSITION_TOL_MM = 0.05
EDGE_TOL_MM = 0.05


@contextmanager
def _record_draws() -> Iterator[dict[str, list[Any]]]:
    """Record every Text/Line2D/Spine actually drawn inside the block."""
    drawn: dict[str, list[Any]] = {"text": [], "line": [], "spine": []}
    originals = {Text: Text.draw, Line2D: Line2D.draw, Spine: Spine.draw}
    keys = {Text: "text", Line2D: "line", Spine: "spine"}

    def wrap(cls: type) -> Any:
        original = originals[cls]

        def draw(self: Any, renderer: Any) -> Any:
            if self.get_visible():
                drawn[keys[cls]].append(self)
            return original(self, renderer)

        return draw

    try:
        for cls in originals:
            cls.draw = wrap(cls)  # type: ignore[attr-defined]
        yield drawn
    finally:
        for cls, original in originals.items():
            cls.draw = original  # type: ignore[attr-defined]


def _describe(artist: Any) -> str:
    if isinstance(artist, Text):
        text = artist.get_text().replace("\n", " ")
        return repr(text[:40] + ("…" if len(text) > 40 else ""))
    return type(artist).__name__


def check_figure(
    fig: Figure,
    style: dict[str, Any],
    expected_size_mm: tuple[float, float],
    expected_axes: list[tuple[Axes, Rect, Rect]] | None = None,
) -> list[Issue]:
    """Run all checks on ``fig`` as it would be saved.

    Args:
        fig: the panel figure.
        style: resolved layout style (font/lines limits).
        expected_size_mm: panel box ``(w, h)``.
        expected_axes: ``(axes, axes rect, panel box)`` triples placed from the layout,
            whose position must not have been changed afterwards.
    """
    issues = _check_size(fig, expected_size_mm) + _check_font_family(style)
    # Measure at the export resolution: at screen resolution (~100 dpi) a 6 pt label is
    # ~8 px tall and font hinting changes its measured length by up to ~10 %, enough to
    # miss a label that is clipped in the printed file.
    original_dpi = fig.dpi
    fig.set_dpi(max(float(original_dpi), float(style["export"]["dpi"])))
    try:
        # Works with every backend, including the notebook inline one (whose canvas has
        # no renderer of its own): draw once with a renderer and measure with the same one.
        renderer = fig._get_renderer()  # type: ignore[attr-defined]
        with _record_draws() as drawn:
            fig.draw(renderer)
        texts, text_issues = _check_texts(fig, renderer, drawn["text"], style)
        issues += text_issues
        issues += _check_spread(texts, style["font"].get("max_spread"))
        issues += _check_overlaps(texts, fig.dpi / MM_PER_INCH)
        issues += _check_lines(drawn["line"], drawn["spine"], style["lines"]["min"])
    finally:
        fig.set_dpi(original_dpi)
    issues += _check_axes(expected_axes or [])
    issues += _check_axes_inside(fig)
    return issues


def _check_axes_inside(fig: Figure) -> list[Issue]:
    """Visible axes (plots, dendrograms, colorbars) must stay inside the panel."""
    issues: list[Issue] = []
    w_mm, h_mm = (v * MM_PER_INCH for v in fig.get_size_inches())
    for ax in fig.axes:
        if not ax.get_visible():
            continue
        x0, y0, x1, y1 = ax.get_position().extents
        beyond = max(-x0 * w_mm, -y0 * h_mm, (x1 - 1) * w_mm, (y1 - 1) * h_mm)
        if beyond > POSITION_TOL_MM:
            label = ax.get_label() or type(ax).__name__
            message = f"axes {label!r} extends {beyond:.1f} mm beyond the panel edge"
            issues.append(Issue("error", "axes-outside-panel", message))
    return issues


def _check_size(fig: Figure, expected_size_mm: tuple[float, float]) -> list[Issue]:
    w_in, h_in = fig.get_size_inches()
    w_mm, h_mm = w_in * MM_PER_INCH, h_in * MM_PER_INCH
    exp_w, exp_h = expected_size_mm
    if abs(w_mm - exp_w) <= SIZE_TOL_MM and abs(h_mm - exp_h) <= SIZE_TOL_MM:
        return []
    message = f"figure is {w_mm:.2f} x {h_mm:.2f} mm, panel box is {exp_w:.2f} x {exp_h:.2f} mm"
    return [Issue("error", "figure-size", message)]


def _check_font_family(style: dict[str, Any]) -> list[Issue]:
    families = list(style["font"]["family"])
    if first_available_font(families[:1]) is not None:
        return []
    fallback = first_available_font(families)
    message = (
        f"font {families[0]!r} not found by matplotlib, using {fallback!r} "
        "(install it, then run `plotplate fonts --rebuild`)"
    )
    return [Issue("warning", "font-missing", message)]


def _check_texts(
    fig: Figure, renderer: Any, drawn: list[Text], style: dict[str, Any]
) -> tuple[list[tuple[Text, Bbox]], list[Issue]]:
    """Font size limits and clipping at the panel edge, for every drawn non-empty text."""
    issues: list[Issue] = []
    width, height = fig.bbox.width, fig.bbox.height
    tol = EDGE_TOL_MM * fig.dpi / MM_PER_INCH
    font_min, font_max = style["font"]["min"], style["font"]["max"]
    texts: list[tuple[Text, Bbox]] = []
    seen: set[int] = set()
    for text in drawn:
        if id(text) in seen or not text.get_text().strip():
            continue
        seen.add(id(text))
        size = text.get_fontsize()
        if size < font_min - 1e-6:
            message = f"{_describe(text)} at {size:g} pt < {font_min} pt"
            issues.append(Issue("error", "font-too-small", message))
        elif size > font_max + 1e-6:
            message = f"{_describe(text)} at {size:g} pt > {font_max} pt"
            issues.append(Issue("warning", "font-too-large", message))
        extent = text.get_window_extent(renderer)
        texts.append((text, extent))
        inside = (
            extent.x0 >= -tol
            and extent.y0 >= -tol
            and extent.x1 <= width + tol
            and extent.y1 <= height + tol
        )
        if not inside:
            message = f"{_describe(text)} extends beyond the panel edge"
            issues.append(Issue("error", "text-clipped", message))
    return texts, issues


def _check_spread(texts: list[tuple[Text, Bbox]], max_spread: float | None) -> list[Issue]:
    """Difference between the largest and smallest font size in the panel.

    Some journals limit it (Genome Research: at most 2 pt within a figure). Panel
    letters are drawn by LaTeX, so they are not part of this measurement.
    """
    if max_spread is None or not texts:
        return []
    sizes = [float(text.get_fontsize()) for text, _ in texts]
    spread = max(sizes) - min(sizes)
    if spread <= max_spread + 1e-6:
        return []
    message = f"font sizes range from {min(sizes):g} to {max(sizes):g} pt (> {max_spread} pt spread)"
    return [Issue("warning", "font-size-spread", message)]


def _check_overlaps(texts: list[tuple[Text, Bbox]], px_per_mm: float) -> list[Issue]:
    """Pairs of texts overlapping by more than ~0.3 mm in both directions."""
    issues: list[Issue] = []
    min_px = 0.3 * px_per_mm
    for i, (text_a, box_a) in enumerate(texts):
        for text_b, box_b in texts[i + 1 :]:
            dx = min(box_a.x1, box_b.x1) - max(box_a.x0, box_b.x0)
            dy = min(box_a.y1, box_b.y1) - max(box_a.y0, box_b.y0)
            if dx > min_px and dy > min_px:
                message = f"{_describe(text_a)} overlaps {_describe(text_b)}"
                issues.append(Issue("warning", "text-overlap", message))
    return issues


def _check_lines(lines: list[Line2D], spines: list[Spine], line_min: float) -> list[Issue]:
    """Visible lines thinner than the minimum width (one issue per kind of artist)."""
    thin: dict[str, float] = {}
    for line in lines:
        lw = line.get_linewidth()
        if 0 < lw < line_min - 1e-6 and line.get_linestyle() not in {"None", "none", ""}:
            thin["Line2D"] = min(lw, thin.get("Line2D", lw))
    for spine in spines:
        lw = spine.get_linewidth()
        if 0 < lw < line_min - 1e-6:
            thin["spine"] = min(lw, thin.get("spine", lw))
    return [
        Issue("warning", "line-too-thin", f"{kind} line width {lw:g} pt < {line_min} pt")
        for kind, lw in thin.items()
    ]


def _check_axes(expected_axes: list[tuple[Axes, Rect, Rect]]) -> list[Issue]:
    """Axes placed from the layout must still be where the layout put them."""
    issues: list[Issue] = []
    for axes, rect, box in expected_axes:
        expected = rect.to_figure_fraction(box)
        actual = axes.get_position().bounds
        scale = (box.w, box.h, box.w, box.h)
        delta_mm = max(abs(a - e) * s for a, e, s in zip(actual, expected, scale, strict=True))
        if delta_mm > POSITION_TOL_MM:
            message = (
                f"axes placed from the layout moved by up to {delta_mm:.2f} mm "
                "(set_position, tight_layout or a helper changed it?)"
            )
            issues.append(Issue("error", "axes-moved", message))
    return issues
