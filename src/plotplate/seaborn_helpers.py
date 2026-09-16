"""Helpers for seaborn figure-level plots that build their own axes (e.g. clustermap)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .geometry import Rect

if TYPE_CHECKING:
    from .panel import Panel


def _resolve(panel: Panel, target: str | Rect) -> Rect:
    if isinstance(target, Rect):
        return target
    if panel.spec.axes[target].is_grid:
        raise TypeError(f"axes {target!r} is a grid; give a single rectangle")
    return panel.axes_rect(target)


def _label_clustermap_axes(grid: Any, heatmap: str | Rect) -> None:
    """Name the clustermap's axes, so alignment checks can refer to them."""
    for ax, label in (
        (grid.ax_heatmap, heatmap if isinstance(heatmap, str) else "heatmap"),
        (grid.ax_row_dendrogram, "row_dendrogram"),
        (grid.ax_col_dendrogram, "col_dendrogram"),
        (grid.ax_cbar, "cbar"),
        (getattr(grid, "ax_row_colors", None), "row_colors"),
        (getattr(grid, "ax_col_colors", None), "col_colors"),
    ):
        if ax is not None:
            ax.set_label(str(label))


def _placer(panel: Panel, frac: Rect) -> Any:
    """Return a function placing an axes at a page rectangle, refusing to leave the panel."""

    def put(ax: Any, rect: Rect) -> None:
        if ax is None:
            return
        if not panel.box.contains(rect, tol=0.05):
            box = panel.box
            missing = max(box.left - rect.left, box.top - rect.top, rect.right - box.right,
                          rect.bottom - box.bottom)  # fmt: skip
            raise ValueError(
                f"panel {panel.name}: clustermap part at {rect.to_list(1)} mm falls {missing:.1f} mm "
                "outside the panel; move the heatmap rectangle or reduce dendrogram/colour sizes"
            )
        ax.set_position(rect.to_figure_fraction(frac))

    return put


def place_clustermap(
    grid: Any,
    panel: Panel,
    heatmap: str | Rect,
    *,
    row_dendrogram_mm: float = 6.0,
    col_dendrogram_mm: float = 6.0,
    colors_mm: float = 2.0,
    gap_mm: float = 0.5,
    cbar: str | Rect | None = None,
) -> Any:
    """Fit a ``sns.clustermap`` into ``panel`` with its heatmap at a layout rectangle.

    The heatmap goes exactly at ``heatmap`` (an axes name of the panel, or a page
    ``Rect``), so its edges can align with other panels. Dendrograms and row/column
    color strips are stacked to the left of and above it; ``cbar`` places the colorbar.

    Call after ``sns.clustermap(..., figsize=panel.figsize)``. Returns ``grid``.
    """
    fig = panel.fit(grid.figure)
    heat = _resolve(panel, heatmap)
    frac = panel.box

    def put(ax: Any, rect: Rect) -> None:
        if ax is None:
            return
        if not panel.box.contains(rect, tol=0.05):
            box = panel.box
            missing = max(box.left - rect.left, box.top - rect.top, rect.right - box.right,
                          rect.bottom - box.bottom)  # fmt: skip
            raise ValueError(
                f"panel {panel.name}: clustermap part at {rect.to_list(1)} mm falls {missing:.1f} mm "
                "outside the panel; move the heatmap rectangle or reduce dendrogram/colour sizes"
            )
        ax.set_position(rect.to_figure_fraction(frac))

    put(grid.ax_heatmap, heat)
    _label_clustermap_axes(grid, heatmap)
    left = heat.left
    if getattr(grid, "ax_row_colors", None) is not None:
        left -= gap_mm + colors_mm
        put(grid.ax_row_colors, Rect(left, heat.y, colors_mm, heat.h))
    if grid.ax_row_dendrogram is not None and row_dendrogram_mm > 0:
        put(
            grid.ax_row_dendrogram,
            Rect(left - gap_mm - row_dendrogram_mm, heat.y, row_dendrogram_mm, heat.h),
        )
    top = heat.top
    if getattr(grid, "ax_col_colors", None) is not None:
        top -= gap_mm + colors_mm
        put(grid.ax_col_colors, Rect(heat.x, top, heat.w, colors_mm))
    if grid.ax_col_dendrogram is not None and col_dendrogram_mm > 0:
        put(
            grid.ax_col_dendrogram,
            Rect(heat.x, top - gap_mm - col_dendrogram_mm, heat.w, col_dendrogram_mm),
        )
    if grid.ax_cbar is not None:
        if cbar is None:
            grid.ax_cbar.set_visible(False)
        else:
            put(grid.ax_cbar, _resolve(panel, cbar))
    placed = panel._placed.setdefault(id(fig), [])
    placed.append((grid.ax_heatmap, heat, panel.box))
    return grid
