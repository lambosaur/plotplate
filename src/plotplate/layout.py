"""The layout model: a page, named guides, and panels with optional axes rectangles.

A layout file (YAML) looks like::

    schema: 1
    name: fig1
    journal: nature            # bundled preset name or path to a preset YAML
    style_files: [../style.yaml]
    style: {font: {size: 7}}   # inline overrides, applied last
    page: {width: double, height: 150}   # mm, or a named width from the journal
    guides:                    # named alignment lines, page coordinates (mm)
      x: {plots_left: 12}
      y: {row1_bottom: 55}
    mosaic:                    # optional shorthand to compute panel boxes
      rows: ["AAB", "CDD"]
      gap: [4, 4]              # [horizontal, vertical] mm
    panels:
      A:
        axes:
          roc: {left: plots_left, top: 4, right: 42, bottom: row1_bottom}
          prc: {left: 52, top: 4, right: 84, bottom: row1_bottom}
      B:
        box: [92, 0, 91, 60]   # explicit [x, y, w, h] wins over the mosaic

Axes edges accept a number (mm) or a guide name with an optional offset
(``plots_left``, ``row1_bottom-2.5``). Numbers are page coordinates unless the axes entry
sets ``ref: panel``. See ``docs/layout-spec.md`` for the full reference.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from string import ascii_lowercase, ascii_uppercase
from typing import TYPE_CHECKING, Any

from .config import deep_merge, default_style, dump_yaml, load_journal, load_yaml
from .geometry import Rect

if TYPE_CHECKING:
    from .panel import Panel

SCHEMA_VERSION = 1
_GUIDE_REF = re.compile(r"^\s*([A-Za-z_][\w.]*)\s*(?:([+-])\s*([0-9.]+))?\s*$")


@dataclass(frozen=True)
class AxesSpec:
    """A named plotting area inside a panel: one rectangle, or a grid of them."""

    name: str
    region: Rect
    nrows: int = 1
    ncols: int = 1
    wgap: float = 0.0
    hgap: float = 0.0
    width_ratios: tuple[float, ...] | None = None
    height_ratios: tuple[float, ...] | None = None

    @property
    def is_grid(self) -> bool:
        """Whether this entry describes several axes."""
        return self.nrows * self.ncols > 1

    def _sizes(self) -> tuple[list[float], list[float]]:
        """Column widths and row heights (mm) after gaps, following the ratios."""
        wr = self.width_ratios or (1.0,) * self.ncols
        hr = self.height_ratios or (1.0,) * self.nrows
        free_w = self.region.w - self.wgap * (self.ncols - 1)
        free_h = self.region.h - self.hgap * (self.nrows - 1)
        return [free_w * r / sum(wr) for r in wr], [free_h * r / sum(hr) for r in hr]

    def rects(self) -> list[Rect]:
        """Individual axes rectangles, row by row (top-left first)."""
        widths, heights = self._sizes()
        xs = [self.region.x + sum(widths[:c]) + self.wgap * c for c in range(self.ncols)]
        ys = [self.region.y + sum(heights[:r]) + self.hgap * r for r in range(self.nrows)]
        return [
            Rect(xs[col], ys[row], widths[col], heights[row])
            for row in range(self.nrows)
            for col in range(self.ncols)
        ]


def _ratios(values: Any, count: Any, key: str, name: str) -> tuple[float, ...] | None:
    if values is None:
        return None
    ratios = tuple(float(v) for v in values)
    if count is not None and len(ratios) != int(count):
        raise ValueError(f"axes {name!r}: {key} has {len(ratios)} values for {count} cells")
    return ratios


@dataclass(frozen=True)
class PanelSpec:
    """A panel: one matplotlib figure placed at ``box`` on the page."""

    name: str
    box: Rect
    label: str | None
    label_offset: tuple[float, float]
    axes: dict[str, AxesSpec] = field(default_factory=dict)


@dataclass
class Issue:
    """A problem found by a validation or a check."""

    level: str  # "error" | "warning" | "info"
    code: str
    message: str

    def __str__(self) -> str:
        """One-line human-readable form."""
        return f"[{self.level}] {self.code}: {self.message}"


class Layout:
    """A figure layout loaded from a YAML file (or a dict)."""

    def __init__(self, data: dict[str, Any], path: Path | None = None) -> None:
        """Build a layout from its raw mapping; ``path`` anchors relative file paths."""
        self.raw = data
        self.path = path.resolve() if path is not None else None
        base_dir = self.base_dir
        schema = data.get("schema", SCHEMA_VERSION)
        if schema != SCHEMA_VERSION:
            raise ValueError(f"Unsupported layout schema {schema!r}; expected {SCHEMA_VERSION}")

        self.name: str = str(data.get("name") or (path.stem if path else "figure"))
        self.journal: dict[str, Any] | None = (
            load_journal(str(data["journal"]), base_dir) if data.get("journal") else None
        )
        self.style = self._resolve_style(data, base_dir)

        page = data.get("page") or {}
        self.width = self._resolve_width(page.get("width"))
        if page.get("height") is None:
            raise ValueError("page.height is required (mm)")
        self.height = float(page["height"])
        self.page = Rect(0.0, 0.0, self.width, self.height)

        guides = data.get("guides") or {}
        self.guides: dict[str, dict[str, float]] = {
            "x": {k: float(v) for k, v in (guides.get("x") or {}).items()},
            "y": {k: float(v) for k, v in (guides.get("y") or {}).items()},
        }
        self.panels: dict[str, PanelSpec] = self._resolve_panels(data)

    # ------------------------------------------------------------------ loading

    @classmethod
    def load(cls, path: str | Path) -> Layout:
        """Load a layout YAML file."""
        path = Path(path)
        return cls(load_yaml(path), path)

    def save(self, path: str | Path | None = None) -> Path:
        """Write the raw mapping back to YAML (at ``path`` or the original location)."""
        target = Path(path) if path is not None else self.path
        if target is None:
            raise ValueError("No path given and the layout was not loaded from a file")
        dump_yaml(self.raw, target)
        return target

    @property
    def base_dir(self) -> Path:
        """Directory relative paths are resolved against."""
        return self.path.parent if self.path is not None else Path.cwd()

    @property
    def panels_dir(self) -> Path:
        """Where panel files are written: ``<layout dir>/panels``."""
        return self.base_dir / "panels"

    @property
    def colors(self) -> dict[str, str]:
        """Named colors from the resolved style."""
        return dict(self.style.get("colors") or {})

    def panel(self, name: str) -> Panel:
        """Runtime handle to create, check and save the figure of panel ``name``."""
        from .panel import Panel

        if name not in self.panels:
            raise KeyError(f"No panel {name!r} in layout {self.name!r}; have {list(self.panels)}")
        return Panel(self, self.panels[name])

    # ------------------------------------------------------------------ resolution

    def _resolve_style(self, data: dict[str, Any], base_dir: Path) -> dict[str, Any]:
        style = default_style()
        if self.journal:
            style = deep_merge(style, self.journal.get("style") or {})
        for style_file in data.get("style_files") or []:
            style = deep_merge(style, load_yaml(base_dir / style_file))
        return deep_merge(style, data.get("style") or {})

    def _resolve_width(self, width: Any) -> float:
        if width is None:
            raise ValueError("page.width is required (mm, or a named journal width)")
        if isinstance(width, int | float):
            return float(width)
        widths = ((self.journal or {}).get("page") or {}).get("widths") or {}
        if width not in widths or widths[width] is None:
            raise ValueError(f"page.width {width!r} is not a number nor a journal width {widths}")
        return float(widths[width])

    def _mosaic_boxes(self, mosaic: dict[str, Any]) -> dict[str, Rect]:
        rows = [list(r) if isinstance(r, str) else [str(c) for c in r] for r in mosaic["rows"]]
        ncols = len(rows[0])
        if any(len(r) != ncols for r in rows):
            raise ValueError("mosaic.rows must all have the same length")
        gap = mosaic.get("gap", [0.0, 0.0])
        hgap, vgap = (gap, gap) if isinstance(gap, int | float) else gap
        wr = mosaic.get("widths") or [1.0] * ncols
        hr = mosaic.get("heights") or [1.0] * len(rows)
        col_w = [(self.width - hgap * (ncols - 1)) * r / sum(wr) for r in wr]
        row_h = [(self.height - vgap * (len(rows) - 1)) * r / sum(hr) for r in hr]
        col_x = [sum(col_w[:i]) + hgap * i for i in range(ncols)]
        row_y = [sum(row_h[:i]) + vgap * i for i in range(len(rows))]

        boxes: dict[str, Rect] = {}
        names = {c for r in rows for c in r} - {"."}
        for name in sorted(names):
            cells = [(i, j) for i, r in enumerate(rows) for j, c in enumerate(r) if c == name]
            i0, i1 = min(c[0] for c in cells), max(c[0] for c in cells)
            j0, j1 = min(c[1] for c in cells), max(c[1] for c in cells)
            if len(cells) != (i1 - i0 + 1) * (j1 - j0 + 1):
                raise ValueError(f"mosaic panel {name!r} is not a rectangle")
            boxes[name] = Rect.from_edges(
                col_x[j0], row_y[i0], col_x[j1] + col_w[j1], row_y[i1] + row_h[i1]
            )
        return boxes

    def _resolve_panels(self, data: dict[str, Any]) -> dict[str, PanelSpec]:
        mosaic = self._mosaic_boxes(data["mosaic"]) if data.get("mosaic") else {}
        raw_panels = dict(data.get("panels") or {})
        for name in mosaic:
            raw_panels.setdefault(name, {})

        label_style = self.style["panel_label"]
        auto_labels = self._auto_labels(data, raw_panels, mosaic, label_style)
        panels: dict[str, PanelSpec] = {}
        for name, raw in raw_panels.items():
            name = str(name)
            raw = raw or {}
            if raw.get("box") is not None:
                box = Rect.from_list(raw["box"])
            elif name in mosaic:
                box = mosaic[name]
            else:
                raise ValueError(f"Panel {name!r} has no box and is not in the mosaic")

            label_raw = raw.get("label", {})
            if label_raw is False:
                label = None
                offset = (0.0, 0.0)
            else:
                label_raw = {} if label_raw is True else (label_raw or {})
                default_text = auto_labels.get(name, name)
                default_text = (
                    default_text.lower() if label_style["case"] == "lower" else default_text.upper()
                )
                label = str(label_raw.get("text", default_text))
                offset = tuple(label_raw.get("offset", label_style["offset"]))  # type: ignore[assignment]

            axes = {
                str(ax_name): self._resolve_axes(str(ax_name), ax_raw, box)
                for ax_name, ax_raw in (raw.get("axes") or {}).items()
            }
            if raw.get("margins") is not None:
                left, top, right, bottom = (float(v) for v in raw["margins"])
                axes.setdefault(
                    "main",
                    AxesSpec(
                        "main",
                        Rect.from_edges(
                            box.left + left, box.top + top, box.right - right, box.bottom - bottom
                        ),
                    ),
                )
            panels[name] = PanelSpec(name, box, label, (float(offset[0]), float(offset[1])), axes)
        return panels

    def _auto_labels(
        self,
        data: dict[str, Any],
        raw_panels: dict[str, Any],
        mosaic: dict[str, Rect],
        label_style: dict[str, Any],
    ) -> dict[str, str]:
        """Letters assigned in reading order when ``labels: auto``.

        With ``labels: id`` (the default) a panel's key is also its letter, so the key must
        be renamed to re-letter a figure. With ``labels: auto`` the key is a stable id
        (e.g. ``roc_prc``) and letters follow the reading order of the boxes.
        """
        mode = str(data.get("labels", "id")).lower()
        if mode not in {"id", "auto"}:
            raise ValueError(f"labels must be 'id' or 'auto', got {mode!r}")
        if mode == "id":
            return {}
        boxes = {}
        for name, raw in raw_panels.items():
            raw = raw or {}
            if raw.get("label") is False:
                continue
            box = Rect.from_list(raw["box"]) if raw.get("box") is not None else mosaic.get(name)
            if box is not None:
                boxes[name] = box
        order = sorted(boxes, key=lambda n: (round(boxes[n].top / 5), boxes[n].left))
        alphabet = ascii_lowercase if label_style["case"] == "lower" else ascii_uppercase
        return {name: alphabet[i] for i, name in enumerate(order) if i < len(alphabet)}

    def _edge(self, value: Any, axis: str, origin: float) -> float:
        """Resolve one edge: a number (plus ``origin``) or ``guide[+-offset]``."""
        if isinstance(value, int | float):
            return origin + float(value)
        match = _GUIDE_REF.match(str(value))
        if not match or match.group(1) not in self.guides[axis]:
            raise ValueError(
                f"Unknown {axis}-guide reference {value!r}; defined: {list(self.guides[axis])}"
            )
        position = self.guides[axis][match.group(1)]
        if match.group(2):
            delta = float(match.group(3))
            position += delta if match.group(2) == "+" else -delta
        return position

    def _resolve_axes(self, name: str, raw: Any, box: Rect) -> AxesSpec:
        if isinstance(raw, list):
            raw = {"box": raw}
        ref = raw.get("ref", "page")
        if ref not in {"page", "panel"}:
            raise ValueError(f"axes {name!r}: ref must be 'page' or 'panel', got {ref!r}")
        ox, oy = (box.x, box.y) if ref == "panel" else (0.0, 0.0)
        if raw.get("box") is not None:
            region = Rect.from_list(raw["box"]).translated(ox, oy)
        else:
            try:
                region = Rect.from_edges(
                    self._edge(raw["left"], "x", ox),
                    self._edge(raw["top"], "y", oy),
                    self._edge(raw["right"], "x", ox),
                    self._edge(raw["bottom"], "y", oy),
                )
            except KeyError as exc:
                raise ValueError(
                    f"axes {name!r} needs either box or all of left/top/right/bottom"
                ) from exc
        return AxesSpec(
            name,
            region,
            nrows=int(raw.get("nrows", len(raw.get("height_ratios") or [1]))),
            ncols=int(raw.get("ncols", len(raw.get("width_ratios") or [1]))),
            wgap=float(raw.get("wgap", 0.0)),
            hgap=float(raw.get("hgap", 0.0)),
            width_ratios=_ratios(raw.get("width_ratios"), raw.get("ncols"), "width_ratios", name),
            height_ratios=_ratios(raw.get("height_ratios"), raw.get("nrows"), "height_ratios", name),
        )

    # ------------------------------------------------------------------ validation

    def validate(self) -> list[Issue]:
        """Geometry sanity checks that need no panel files."""
        issues: list[Issue] = []
        page_cfg = (self.journal or {}).get("page") or {}
        max_height = page_cfg.get("max_height")
        if max_height and self.height > max_height + 1e-6:
            issues.append(
                Issue(
                    "warning",
                    "page-height",
                    f"page height {self.height} mm exceeds the journal maximum {max_height} mm",
                )
            )
        widths = [w for w in (page_cfg.get("widths") or {}).values() if w]
        if widths and all(abs(self.width - w) > 0.5 for w in widths):
            issues.append(
                Issue(
                    "info",
                    "page-width",
                    f"page width {self.width} mm is not a journal column width {widths}",
                )
            )

        names = list(self.panels)
        for i, name in enumerate(names):
            spec = self.panels[name]
            if not self.page.contains(spec.box, tol=0.05):
                issues.append(Issue("error", "panel-outside-page", f"panel {name} {spec.box}"))
            for other in names[i + 1 :]:
                overlap = spec.box.intersection_area(self.panels[other].box)
                if overlap > 0.01:
                    issues.append(
                        Issue(
                            "warning",
                            "panel-overlap",
                            f"panels {name} and {other} overlap by {overlap:.1f} mm²",
                        )
                    )
            for axes in spec.axes.values():
                if not spec.box.contains(axes.region, tol=0.05):
                    issues.append(
                        Issue(
                            "error",
                            "axes-outside-panel",
                            f"axes {name}/{axes.name} {axes.region} not inside panel box {spec.box}",
                        )
                    )
        return issues
