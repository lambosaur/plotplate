"""Fit Marsilea boards (annotated heatmaps, oncoprints, UpSet plots…) into a panel box.

Marsilea sizes a plot from the inside out: the main canvas has a size in inches, and
every side plot, label and legend adds its own measured size around it. The figure size
is the result, not an input. ``fit_marsilea`` renders twice: a first pass measures the
space everything around the main canvas needs, and the second pass sets the main canvas
size (and margins) so the whole figure has exactly the panel size.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import matplotlib.pyplot as plt
import numpy as np

from .geometry import MM_PER_INCH, Rect

if TYPE_CHECKING:
    from .panel import Panel


def _main_bounds_in(board: Any, figsize: np.ndarray) -> tuple[float, float, float, float]:
    """Union of the main axes bounds, in inches from the figure's bottom-left corner."""
    axes = board.get_main_ax()
    axes = list(axes) if isinstance(axes, list | tuple | np.ndarray) else [axes]
    boxes = np.array([ax.get_position().extents for ax in axes])  # x0, y0, x1, y1 fractions
    x0, y0 = boxes[:, 0].min() * figsize[0], boxes[:, 1].min() * figsize[1]
    x1, y1 = boxes[:, 2].max() * figsize[0], boxes[:, 3].max() * figsize[1]
    return float(x0), float(y0), float(x1), float(y1)


def fit_marsilea(
    build: Callable[[float, float], Any],
    panel: Panel,
    main: str | Rect | None = None,
) -> Any:
    """Render a Marsilea board so the figure exactly fills ``panel``.

    Args:
        build: function ``(width_in, height_in) -> board`` that creates the (not yet
            rendered) board with its main canvas at the given size, e.g.
            ``lambda w, h: ma.Heatmap(data, width=w, height=h)`` plus ``add_*`` calls.
            It is called twice, so it must not have side effects.
        panel: target panel.
        main: optional layout axes name (or page ``Rect``) where the main canvas must
            land exactly, to align it with other panels. Without it, the main canvas
            takes all the space left by labels, side plots and legends.

    Returns:
        The rendered board; its figure is ``board.figure``.

    Raises:
        ValueError: when the surrounding elements do not fit next to ``main``.
    """
    panel.use_style()
    # Lay out at the export resolution: Marsilea measures labels in pixels, and at screen
    # resolution hinting under-estimates small text, leaving too little room in print.
    dpi = float(panel.layout.style["export"]["dpi"])
    probe_board = build(1.0, 1.0)
    probe = plt.figure(dpi=dpi)
    probe_board.render(figure=probe)
    size0 = probe.get_size_inches()
    x0, y0, x1, y1 = _main_bounds_in(probe_board, size0)
    main_w0, main_h0 = x1 - x0, y1 - y0
    # Space used around the main canvas, margins included.
    used = {"left": x0, "right": size0[0] - x1, "bottom": y0, "top": size0[1] - y1}
    old = probe_board.layout.margin
    margin = {"top": old.top, "right": old.right, "bottom": old.bottom, "left": old.left}
    plt.close(probe)

    box_w, box_h = panel.box.w / MM_PER_INCH, panel.box.h / MM_PER_INCH
    rect: Rect | None = None
    if main is None:
        main_w = main_w0 + box_w - size0[0]
        main_h = main_h0 + box_h - size0[1]
        if main_w <= 0 or main_h <= 0:
            raise ValueError(
                f"panel {panel.name}: labels, side plots and legends alone need "
                f"{(size0[0] - main_w0) * MM_PER_INCH:.1f} x "
                f"{(size0[1] - main_h0) * MM_PER_INCH:.1f} mm"
            )
    else:
        if isinstance(main, str) and panel.spec.axes[main].is_grid:
            raise TypeError(f"axes {main!r} is a grid; give a single rectangle")
        rect = main if isinstance(main, Rect) else panel.axes_rect(main)
        box = panel.box
        wanted = {
            "left": (rect.left - box.left) / MM_PER_INCH,
            "right": (box.right - rect.right) / MM_PER_INCH,
            "top": (rect.top - box.top) / MM_PER_INCH,
            "bottom": (box.bottom - rect.bottom) / MM_PER_INCH,
        }
        for side in margin:
            margin[side] += wanted[side] - used[side]
        short = {side: -value * MM_PER_INCH for side, value in margin.items() if value < -1e-6}
        if short:
            detail = ", ".join(f"{side} {mm:.1f} mm" for side, mm in short.items())
            message = f"panel {panel.name}: not enough room around '{main}': missing {detail}"
            raise ValueError(message)
        main_w, main_h = rect.w / MM_PER_INCH, rect.h / MM_PER_INCH

    board = build(main_w, main_h)
    board.set_margin((margin["top"], margin["right"], margin["bottom"], margin["left"]))
    fig = panel.figure(dpi=dpi)
    board.render(figure=fig)
    fig.set_dpi(100)  # positions are fractions already; keep notebook display reasonable
    if rect is not None:
        axes = board.get_main_ax()
        if not isinstance(axes, list | tuple | np.ndarray):
            placed = panel._placed.setdefault(id(fig), [])
            placed.append((axes, rect, panel.box))
    return board
