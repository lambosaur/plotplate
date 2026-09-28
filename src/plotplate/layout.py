"""The layout model: a page, named guides, and panels with optional axes rectangles.

A layout file (YAML) looks like::

    schema: 1
    name: fig1
    journal: nature            # bundled preset name or path to a preset YAML
    style_files: [../style.yaml]
    style: {font: {size: 7}}   # inline overrides, applied last
    page: {paper: a4, margins: 25, caption: 25}   # the sheet the figure is printed on
    area: {width: double, height: 150}   # the figure itself: mm, or a journal width name
    guides:                    # named alignment lines an axes can be placed against (mm)
      x: {plots_left: 12}
      y: {row1_bottom: 55}
    page_guides:               # unnamed lines to arrange panels against; drawn across the page
      x: [91.5]
      y: [62]
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

import copy
import re
from dataclasses import dataclass, field
from pathlib import Path
from string import ascii_lowercase, ascii_uppercase
from typing import TYPE_CHECKING, Any

from .config import deep_merge, default_style, dump_yaml, load_journal, load_yaml
from .geometry import Rect
from .variants import resolve_layout_path

if TYPE_CHECKING:
    from .panel import Panel

SCHEMA_VERSION = 1
_GUIDE_REF = re.compile(r"^\s*([A-Za-z_][\w.]*)\s*(?:([+-])\s*([0-9.]+))?\s*$")

#: Sheet sizes (mm) usable in ``page.paper``.
PAPERS: dict[str, tuple[float, float]] = {"a4": (210.0, 297.0), "letter": (215.9, 279.4)}
DEFAULT_MARGIN_MM = 25.0


def split_area_page(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Separate the figure area from the sheet in a raw layout mapping.

    ``area:`` is the figure's own box and ``page:`` the sheet it is printed on. Layouts
    written before that split put the box in ``page:``, which is still read as the area.
    """
    area = data.get("area")
    page = data.get("page") if isinstance(data.get("page"), dict) else None
    if area is not None:
        return dict(area or {}), page
    if page is not None and (page.get("width") is not None or page.get("height") is not None):
        return dict(page), None
    return {}, page


def area_section(data: dict[str, Any]) -> dict[str, Any]:
    """The mapping inside ``data`` that holds the figure size, created if absent.

    Returns the live sub-mapping, so a writer can set width/height in place without
    caring whether the layout uses ``area:`` or the older ``page:`` box.
    """
    page = data.get("page")
    if (
        data.get("area") is None
        and isinstance(page, dict)
        and (page.get("width") is not None or page.get("height") is not None)
    ):
        return page
    if not isinstance(data.get("area"), dict):
        data["area"] = {}
    section: dict[str, Any] = data["area"]
    return section


def sheet_for(paper: str | None, width: float | None = None) -> dict[str, Any]:
    """A ``page:`` section for ``paper``, with margins that leave room for ``width`` mm.

    The commands that draft a layout use this: a figure of a known width on a known sheet
    determines the side margins, so the layout records where the figure will sit.
    """
    if not paper or str(paper).lower() == "none":
        return {}
    name = str(paper).lower()
    if name not in PAPERS:
        raise ValueError(f"unknown paper {paper!r}; use one of {list(PAPERS)} or 'none'")
    side = DEFAULT_MARGIN_MM
    if width is not None and 0 < width < PAPERS[name][0]:
        side = min(DEFAULT_MARGIN_MM, round((PAPERS[name][0] - width) / 2, 2))
    return {"paper": name, "margins": {"left": side, "right": side, "top": 25, "bottom": 25}}


@dataclass(frozen=True)
class Sheet:
    """Where the figure sits on the printed sheet, all in millimetres."""

    paper: str
    size: tuple[float, float]
    margins: dict[str, float]
    text: Rect  # the text block: what the figure has to fit in
    area: Rect  # the figure itself, at the top of the text block
    caption: float  # space kept under the figure for its caption
    assumed: bool = False  # the layout declares no sheet; this one was supplied by a command


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

        # `area:` is the figure's own box; `page:` then describes the sheet it must fit on.
        # Layouts written before that split used `page:` for the box, which still works.
        area, self.sheet = split_area_page(data)
        self.width = self._resolve_width(area.get("width"))
        if area.get("height") is None:
            raise ValueError("area.height is required (mm, or 'solve' with constraints)")
        raw_height = area["height"]
        solve_height = isinstance(raw_height, str) and raw_height.lower() in {"solve", "auto"}
        height = None if solve_height else float(raw_height)
        self.constraint_boxes: dict[str, Rect] = {}
        if data.get("constraints"):
            self.constraint_boxes, solved = self._solve_constraints(data, height)
            height = solved if solve_height else height
        elif solve_height:
            raise ValueError("area.height: 'solve' needs a constraints section")
        self.height = float(height)  # type: ignore[arg-type]
        self.page = Rect(0.0, 0.0, self.width, self.height)

        guides = data.get("guides") or {}
        self.guides: dict[str, dict[str, float]] = {
            "x": {k: float(v) for k, v in (guides.get("x") or {}).items()},
            "y": {k: float(v) for k, v in (guides.get("y") or {}).items()},
        }
        # Page guides are scaffolding for the author, not references: nothing can be placed
        # against them, so they are plain numbers, they need no names, and dropping one changes
        # no panel. They are in layout millimetres like everything else, and `plotplate view`
        # draws them across the whole sheet.
        page_guides = data.get("page_guides") or {}
        self.page_guides: dict[str, list[float]] = {
            axis: sorted({round(float(v), 3) for v in (page_guides.get(axis) or [])})
            for axis in ("x", "y")
        }
        self.panels: dict[str, PanelSpec] = self._resolve_panels(data)

    # ------------------------------------------------------------------ loading

    @classmethod
    def load(cls, path: str | Path) -> Layout:
        """Load a layout YAML file, or the ``layout.yaml`` of a figure folder."""
        path = resolve_layout_path(path)
        return cls(load_yaml(path), path)

    def save(self, path: str | Path | None = None) -> Path:
        """Write the raw mapping back to YAML (at ``path`` or the original location)."""
        target = Path(path) if path is not None else self.path
        if target is None:
            raise ValueError("No path given and the layout was not loaded from a file")
        dump_yaml(self.raw, target)
        return target

    @property
    def file(self) -> Path:
        """The file this layout was loaded from; layouts built in memory have none."""
        if self.path is None:
            raise ValueError(f"layout {self.name!r} was not loaded from a file")
        return self.path

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

    def resolved(self) -> dict[str, Any]:
        """The same figure as plain numbers: every box explicit, no mosaic, no constraints.

        Name, journal, style, sheet, guides, labels and axes grids are kept, so the result
        loads to the same figure. ``plotplate resolve`` writes this, and the commands that
        move boxes around (``optimize``) start from it. A layout still using ``page:`` for the
        figure box is migrated to ``area:`` on the way.
        """
        data = copy.deepcopy(self.raw)
        data.pop("mosaic", None)
        data.pop("constraints", None)  # the solved boxes replace the rules
        area, sheet = split_area_page(self.raw)
        data["area"] = {**area, "width": self.width, "height": self.height}
        if sheet is None:
            data.pop("page", None)
        panels: dict[str, Any] = {}
        for name, spec in self.panels.items():
            entry = dict((self.raw.get("panels") or {}).get(name) or {})
            entry["box"] = spec.box.to_list()
            entry.pop("margins", None)
            axes = {}
            for ax_name, ax in spec.axes.items():
                ax_raw = dict((entry.get("axes") or {}).get(ax_name) or {})
                if not isinstance(ax_raw, dict):
                    ax_raw = {}
                for key in ("left", "top", "right", "bottom", "ref"):
                    ax_raw.pop(key, None)
                ax_raw["box"] = ax.region.to_list()
                axes[ax_name] = ax_raw
            if axes:
                entry["axes"] = axes
            panels[name] = entry
        data["panels"] = panels
        return data

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

    def _solve_constraints(
        self, data: dict[str, Any], height: float | None
    ) -> tuple[dict[str, Rect], float]:
        """Boxes computed from the ``constraints`` section, and the page height."""
        from .solve import solve_boxes

        raw_panels = data.get("panels") or {}
        if not raw_panels:
            raise ValueError(
                "constraints need panels; declare them in `panels:` (an empty entry is fine)"
            )
        pinned = {
            name: Rect.from_list(spec["box"])
            for name, spec in raw_panels.items()
            if (spec or {}).get("box") is not None
        }
        return solve_boxes(list(raw_panels), data["constraints"], self.width, height, pinned)

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
            elif name in self.constraint_boxes:
                box = self.constraint_boxes[name]
            elif name in mosaic:
                box = mosaic[name]
            else:
                raise ValueError(f"Panel {name!r} has no box, constraints or mosaic cell")

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

    def sheet_geometry(self, paper: str | None = None) -> Sheet | None:
        """Where this figure sits on its sheet, or ``None`` when no sheet is known.

        The sheet comes from the layout's ``page:`` section. ``paper`` supplies one when the
        layout declares none (what ``plotplate view --paper a4`` does), and the result is then
        marked ``assumed``.

        The figure is placed at the top of the text block, centred between the side margins:
        that is where a LaTeX float puts it, and the caption goes underneath.
        """
        sheet = self.sheet
        assumed = False
        if not sheet:
            if paper is None:
                return None
            # No sheet was declared: assume one with margins that fit this figure, so the view
            # is about where the figure sits rather than about margins nobody chose.
            sheet, assumed = sheet_for(paper, self.width), True
        raw_paper = sheet.get("paper", "a4")
        if isinstance(raw_paper, str):
            size = PAPERS.get(raw_paper.lower())
            name = raw_paper.lower()
        else:
            values = [float(v) for v in raw_paper]
            size, name = (values[0], values[1]), "custom"
        if size is None:
            raise ValueError(f"unknown paper {raw_paper!r}; use a4, letter or [width, height] in mm")
        margins_raw = sheet.get("margins")
        if isinstance(margins_raw, int | float):
            margins_raw = dict.fromkeys(("top", "bottom", "left", "right"), float(margins_raw))
        margins_raw = margins_raw or {}
        margins = {
            edge: float(margins_raw.get(edge, DEFAULT_MARGIN_MM))
            for edge in ("left", "right", "top", "bottom")
        }
        text = Rect.from_edges(
            margins["left"], margins["top"], size[0] - margins["right"], size[1] - margins["bottom"]
        )
        area = Rect(text.x + max(0.0, (text.w - self.width) / 2), text.y, self.width, self.height)
        return Sheet(
            name, size, margins, text, area, float(sheet.get("caption", 0) or 0), assumed=assumed
        )

    def sheet_size(self) -> tuple[float, float, float, float] | None:
        """The sheet as ``(width, height, text width, text height)`` in mm, if one is declared."""
        geometry = self.sheet_geometry()
        if geometry is None:
            return None
        return (*geometry.size, geometry.text.w, geometry.text.h)

    def _sheet_issues(self) -> list[Issue]:
        """Does the figure fit on the sheet, with room for its caption?"""
        sizes = self.sheet_size()
        if sizes is None:
            return []
        _, _, text_width, text_height = sizes
        caption = float((self.sheet or {}).get("caption", 0))
        issues: list[Issue] = []
        if self.width > text_width + 1e-6:
            issues.append(
                Issue(
                    "warning",
                    "wider-than-text",
                    f"the figure is {self.width} mm wide, the text block is {text_width:.1f} mm",
                )
            )
        needed = self.height + caption
        if needed > text_height + 1e-6:
            detail = f" plus {caption:g} mm of caption" if caption else ""
            issues.append(
                Issue(
                    "warning",
                    "taller-than-page",
                    f"the figure is {self.height} mm tall{detail}, the text block is "
                    f"{text_height:.1f} mm: the caption would move to the next page",
                )
            )
        return issues

    def _journal_issues(self) -> list[Issue]:
        """Page size against the journal's column widths and maximum height."""
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
        return issues

    def _constraint_issues(self) -> list[Issue]:
        """Panels the constraint rules do not pin down."""
        if not self.constraint_boxes:
            return []
        from .solve import unconstrained

        loose = unconstrained(self.constraint_boxes, self.width, self.height)
        if not loose:
            return []
        return [
            Issue(
                "warning",
                "under-constrained",
                f"the constraints leave {loose} free: they take the minimum size or the whole "
                "page; add a size, an equal or a pin rule",
            )
        ]

    def validate(self) -> list[Issue]:
        """Geometry sanity checks that need no panel files."""
        issues = self._journal_issues() + self._sheet_issues() + self._constraint_issues()
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
