"""Runtime handle for drawing one panel of a layout."""

from __future__ import annotations

import json
import warnings
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from .checks import check_figure
from .geometry import Rect, in_to_mm
from .style import rc_params

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

    from .layout import Issue, Layout, PanelSpec

_METADATA = {
    "pdf": {"Creator": "plotplate", "CreationDate": None},
    "svg": {"Creator": "plotplate", "Date": None},
    "png": {"Software": "plotplate"},
}


def _untrimmed_inline_display() -> None:
    """Inside a Jupyter kernel, stop the inline backend from cropping figures."""
    try:
        from IPython import get_ipython
        from matplotlib_inline.config import InlineBackend
    except ImportError:
        return
    if get_ipython() is None:  # type: ignore[no-untyped-call]
        return
    # Same effect as `%config InlineBackend.print_figure_kwargs = {...}`.
    InlineBackend.instance().print_figure_kwargs = {"bbox_inches": None}


@dataclass
class SaveReport:
    """What ``Panel.save`` wrote and what the checks found."""

    panel: str
    files: list[str]
    issues: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """No error-level issue."""
        return not any(issue.level == "error" for issue in self.issues)

    def __str__(self) -> str:
        """Short multi-line summary."""
        head = f"panel {self.panel}: {'OK' if self.ok else 'ERRORS'} -> {', '.join(self.files)}"
        return "\n".join([head, *(f"  {issue}" for issue in self.issues)])

    def _repr_html_(self) -> str:
        """Notebook rendering."""
        color = {"error": "#c0392b", "warning": "#b9770e", "info": "#555"}
        rows = "".join(
            f"<li style='color:{color[i.level]}'><b>{i.code}</b>: {i.message}</li>"
            for i in self.issues
        )
        status = "✅ OK" if self.ok else "❌ errors"
        return f"<div><b>panel {self.panel}</b> {status}<ul>{rows}</ul></div>"


class Panel:
    """Draw, check and save one panel so that it exactly fills its layout box."""

    def __init__(self, layout: Layout, spec: PanelSpec) -> None:
        """Usually obtained with ``Layout.panel(name)``."""
        self.layout = layout
        self.spec = spec
        self._placed: dict[int, list[tuple[Axes, Rect, Rect]]] = {}
        self._names: dict[int, str] = {}  # id(axes) -> layout name
        self._marks: dict[str, tuple[Any, float | None, float | None]] = {}

    # ------------------------------------------------------------------ geometry

    @property
    def name(self) -> str:
        """Panel name, e.g. ``"A"``."""
        return self.spec.name

    @property
    def box(self) -> Rect:
        """Panel box on the page (mm)."""
        return self.spec.box

    @property
    def size_mm(self) -> tuple[float, float]:
        """Panel ``(width, height)`` in mm."""
        return (self.box.w, self.box.h)

    @property
    def figsize(self) -> tuple[float, float]:
        """Panel ``(width, height)`` in inches, for ``figsize=``."""
        return self.box.size_in

    @property
    def colors(self) -> dict[str, str]:
        """Named colors shared by the whole figure set."""
        return self.layout.colors

    def rect(self, x: float, y: float, w: float, h: float) -> tuple[float, float, float, float]:
        """Figure-fraction bounds for a rectangle given in page mm (top-left origin)."""
        return Rect(x, y, w, h).to_figure_fraction(self.box)

    def axes_rect(self, name: str) -> Rect:
        """Page rectangle of named axes (the outer region for a grid of axes)."""
        return self.spec.axes[name].region

    def axes_rects(self, name: str) -> list[Rect]:
        """Page rectangles of every cell of named axes, row by row."""
        return self.spec.axes[name].rects()

    # ------------------------------------------------------------------ drawing

    @property
    def rc(self) -> dict[str, Any]:
        """RcParams derived from the layout style."""
        return rc_params(self.layout.style)

    @contextmanager
    def style(self) -> Iterator[None]:
        """Apply the layout style inside a ``with`` block."""
        with mpl.rc_context(self.rc):  # type: ignore[arg-type]
            yield

    def use_style(self) -> None:
        """Apply the layout style globally, and show notebook figures untrimmed.

        The notebook inline backend crops figures to their content by default, which
        hides clipped labels and unused space; inside IPython this switches it to the
        exact figure box.
        """
        mpl.rcParams.update(self.rc)  # type: ignore[arg-type]
        _untrimmed_inline_display()

    def figure(self, *, layout: str | None = None, **kwargs: Any) -> Figure:
        """Create a figure of exactly the panel size, and apply the layout style globally.

        The style is applied globally (not only inside this call) because legends, titles
        and annotations added later read rcParams when they are created. Use
        ``with panel.style():`` instead when drawing several panels in one process.

        Args:
            layout: matplotlib layout engine. Keep ``None`` when placing axes from the
                layout; ``"constrained"`` is fine for free-form content.
            **kwargs: forwarded to ``plt.figure``.
        """
        self.use_style()
        fig = plt.figure(figsize=self.figsize, layout=layout, **kwargs)
        self._placed[id(fig)] = []
        return fig

    def fit(self, fig: Figure) -> Figure:
        """Resize an externally created figure (seaborn clustermap, jointplot…) to the box."""
        fig.set_size_inches(*self.figsize, forward=True)
        self._placed.setdefault(id(fig), [])
        return fig

    def axes(self, fig: Figure, name: str, **kwargs: Any) -> Any:
        """Add the named axes (or grid of axes, as an array) at their layout position."""
        if name not in self.spec.axes:
            raise KeyError(f"Panel {self.name} has no axes {name!r}; defined: {list(self.spec.axes)}")
        spec = self.spec.axes[name]
        created = []
        with self.style():
            for index, rect in enumerate(spec.rects()):
                ax = fig.add_axes(rect.to_figure_fraction(self.box), **kwargs)
                self._placed.setdefault(id(fig), []).append((ax, rect, self.box))
                self._names[id(ax)] = name if not spec.is_grid else f"{name}{index + 1}"
                created.append(ax)
        if not spec.is_grid:
            return created[0]
        return np.array(created, dtype=object).reshape(spec.nrows, spec.ncols)

    def gridspec(
        self,
        fig: Figure,
        region: str | Rect,
        nrows: int = 1,
        ncols: int = 1,
        *,
        wgap: float = 0.0,
        hgap: float = 0.0,
        **kwargs: Any,
    ) -> Any:
        """A matplotlib ``GridSpec`` filling a layout rectangle, with gaps in mm.

        Use it for free-form arrangements inside an axes region (spans, nested grids with
        ``subgridspec``). Unlike ``panel.axes``, the axes created from it are not position
        checked, and a figure layout engine must stay off (``panel.figure()`` default).

        Args:
            fig: the panel figure.
            region: a layout axes name (its outer region) or a page ``Rect``.
            nrows: rows.
            ncols: columns.
            wgap: horizontal gap between cells, mm.
            hgap: vertical gap between cells, mm.
            **kwargs: forwarded to ``GridSpec`` (``width_ratios``, ``height_ratios``).
        """
        from matplotlib.gridspec import GridSpec

        rect = region if isinstance(region, Rect) else self.axes_rect(region)
        left, bottom, width, height = rect.to_figure_fraction(self.box)
        # GridSpec spacing is a fraction of the average cell size.
        cell_w = (rect.w - wgap * (ncols - 1)) / ncols
        cell_h = (rect.h - hgap * (nrows - 1)) / nrows
        return GridSpec(
            nrows,
            ncols,
            figure=fig,
            left=left,
            right=left + width,
            bottom=bottom,
            top=bottom + height,
            wspace=wgap / cell_w if ncols > 1 else 0.0,
            hspace=hgap / cell_h if nrows > 1 else 0.0,
            **kwargs,
        )

    def subplots(self, **kwargs: Any) -> tuple[Figure, dict[str, Any]]:
        """Figure plus every named axes of this panel (``{"main": ax}`` if none are defined).

        Without axes in the layout, the single axes uses constrained layout to fill the box.
        """
        if not self.spec.axes:
            fig = self.figure(layout="constrained")
            ax = fig.add_subplot(**kwargs)
            return fig, {"main": ax}
        fig = self.figure()
        return fig, {name: self.axes(fig, name, **kwargs) for name in self.spec.axes}

    # ------------------------------------------------------------------ output

    def mark(self, name: str, ax: Any = None, x: float | None = None, y: float | None = None) -> None:
        """Register a reference point, in data coordinates of ``ax``, for alignment checks.

        Use it where no spine marks the feature to align (a boxplot without spines, the
        baseline of a bar chart). The page coordinates are measured when the panel is saved
        and written to ``panels/<panel>.json``.
        """
        self._marks[name] = (ax, x, y)

    def page_point(self, ax: Any, x: float, y: float) -> tuple[float, float]:
        """Page coordinates (mm) of a point given in data coordinates of ``ax``."""
        fx, fy = ax.figure.transFigure.inverted().transform(ax.transData.transform((x, y)))
        return (self.box.x + fx * self.box.w, self.box.y + (1 - fy) * self.box.h)

    def geometry(self, fig: Figure) -> dict[str, Any]:
        """Measured page coordinates of the panel's plotting areas and marks."""
        axes_entries: dict[str, Any] = {}
        for index, ax in enumerate(fig.axes):
            if not ax.get_visible():
                continue
            name = self._names.get(id(ax)) or ax.get_label() or f"ax{index + 1}"
            x0, y0, x1, y1 = ax.get_position().extents
            edges = {
                "left": self.box.x + x0 * self.box.w,
                "right": self.box.x + x1 * self.box.w,
                "top": self.box.y + (1 - y1) * self.box.h,
                "bottom": self.box.y + (1 - y0) * self.box.h,
            }
            axes_entries[str(name)] = {
                "box_edges": {key: round(value, 3) for key, value in edges.items()},
                "spines": [side for side, spine in ax.spines.items() if spine.get_visible()],
            }
        marks = {}
        for name, (ax, x, y) in self._marks.items():
            target = ax if ax is not None else (fig.axes[0] if fig.axes else None)
            if target is None:
                continue
            px, py = self.page_point(target, x if x is not None else 0.0, y if y is not None else 0.0)
            marks[name] = {"x": round(px, 3), "y": round(py, 3)}
        return {"axes": axes_entries, "marks": marks}

    def check(self, fig: Figure) -> list[Issue]:
        """Run the size/font/clipping/overlap/line checks without writing files."""
        with self.style():
            return check_figure(fig, self.layout.style, self.size_mm, self._placed.get(id(fig)))

    def save(
        self,
        fig: Figure,
        formats: Sequence[str] | None = None,
        outdir: str | Path | None = None,
        *,
        source: str | None = None,
        strict: bool = False,
    ) -> SaveReport:
        """Check, then write ``panels/<name>.<fmt>`` plus a ``<name>.json`` report.

        Args:
            fig: the panel figure.
            formats: defaults to the style's ``export.formats`` (pdf, svg, png).
            outdir: defaults to ``<layout dir>/panels``.
            source: free text recorded in the report (e.g. the notebook name).
            strict: raise instead of writing when a check reports an error.
        """
        issues = self.check(fig)
        report = SaveReport(self.name, [], issues)
        if strict and not report.ok:
            raise ValueError(str(report))

        outdir = Path(outdir) if outdir is not None else self.layout.panels_dir
        outdir.mkdir(parents=True, exist_ok=True)
        export = self.layout.style["export"]
        with self.style():
            for fmt in formats or export["formats"]:
                path = outdir / f"{self.name}.{fmt}"
                fig.savefig(
                    path,
                    format=fmt,
                    dpi=export["dpi"],
                    bbox_inches=None,
                    pad_inches=0,
                    transparent=bool(export.get("transparent", False)),
                    metadata=_METADATA.get(fmt),
                )
                report.files.append(path.name)

        w_in, h_in = fig.get_size_inches()
        meta = {
            "panel": self.name,
            "layout": self.layout.name,
            "box_mm": self.box.to_list(),
            "size_mm": [round(in_to_mm(w_in), 2), round(in_to_mm(h_in), 2)],
            "files": report.files,
            "source": source,
            "saved": datetime.now(UTC).isoformat(timespec="seconds"),
            "issues": [asdict(issue) for issue in issues],
            "geometry": self.geometry(fig),
        }
        (outdir / f"{self.name}.json").write_text(json.dumps(meta, indent=2) + "\n")
        for issue in issues:
            if issue.level != "info":
                warnings.warn(f"panel {self.name}: {issue}", stacklevel=2)
        return report

    def context(self, width_px: int = 900) -> Any:
        """Notebook view of the whole figure from the saved panels, this panel outlined.

        Call after ``save``: it shows how the panel reads next to its neighbours, at
        their true relative sizes. Nothing is written next to the layout.
        """
        import tempfile

        from .render import preview

        try:
            from IPython.display import Image
        except ImportError:  # plain script run (e.g. `plotplate build`): nothing to display
            return None

        with tempfile.TemporaryDirectory() as tmp:
            paths = preview(self.layout, tmp, highlight=self.name, png_dpi=150)
            data = paths["png"].read_bytes()
        return Image(data=data, width=width_px)

    def display(self, fig: Figure, zoom: float = 2.0) -> Any:
        """Show the panel in a notebook at its true proportions, untrimmed.

        The inline backend normally crops figures (``bbox_inches="tight"``), which hides
        clipped labels and wasted space; this renders the exact box instead.
        """
        import io

        try:
            from IPython.display import Image
        except ImportError:  # plain script run: nothing to display
            return None

        buffer = io.BytesIO()
        with self.style():
            fig.savefig(buffer, format="png", dpi=96 * zoom, bbox_inches=None)
        width_px = round(self.box.w / 25.4 * 96 * zoom)
        return Image(data=buffer.getvalue(), width=width_px)
