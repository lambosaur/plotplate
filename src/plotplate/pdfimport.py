r"""Draft a layout from a PDF page where panels were placed as graphics.

When a figure was assembled by *placing* files (LaTeX ``\includegraphics``, "Place" in
Illustrator or InDesign, imported images in Inkscape), the PDF records each placed graphic
as an XObject drawn with a transformation matrix. Reading those gives the exact box of every
panel, with no image analysis. Single bold letters next to the boxes (panel labels, when
they are real text) name the panels and group several graphics into one panel.

When the page has no placed graphics (everything flattened into paths, as after
"expand"/"ungroup" in a drawing program, or a scanned page), fall back to rendering the
page and running the gutter detection of :mod:`plotplate.detect`.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .geometry import Rect, pt_to_mm

_TOKEN = re.compile(
    rb"%[^\r\n]*"  # comment
    rb"|\((?:\\.|[^\\)])*\)"  # literal string (no nested parentheses)
    rb"|<<|>>|<[0-9A-Fa-f\s]*>"  # dict delimiters, hex string
    rb"|\[|\]"  # array delimiters
    rb"|/[^\s/\[\]()<>{}%]*"  # name
    rb"|[+-]?(?:\d+\.?\d*|\.\d+)"  # number
    rb"|[A-Za-z'\"*]+"  # operator
)
_NUMBER = re.compile(rb"[+-]?(?:\d+\.?\d*|\.\d+)")
CORNER_MM = 6.0  # a letter this close to a graphic's top-left corner can be its label


@dataclass
class Placed:
    """A graphic placed on the page."""

    name: str
    kind: str  # "form" (vector, e.g. an included PDF) or "image" (raster)
    box: Rect  # mm, page coordinates, top-left origin
    scale: float | None  # placed size / natural size (forms only)
    dpi: float | None  # effective resolution (images only)


@dataclass
class Letter:
    """A single-character text span that may be a panel label."""

    text: str
    box: Rect
    size_pt: float
    bold: bool


@dataclass
class PdfLayout:
    """Result of reading a PDF page."""

    data: dict[str, Any]
    placed: list[Placed] = field(default_factory=list)
    letters: list[Letter] = field(default_factory=list)
    method: str = "placed"  # "placed" or "detected"
    notes: list[str] = field(default_factory=list)
    area: Rect | None = None  # figure area on the page (mm), origin of the layout coordinates
    paper: str | None = None  # the sheet the source page was, when it is a known paper size


def _pdf_matrix(values: list[float]) -> np.ndarray:
    a, b, c, d, e, f = values
    # Row-vector convention of the PDF specification: [x y 1] * M.
    return np.array([[a, b, 0.0], [c, d, 0.0], [e, f, 1.0]])


def _bbox_through(bbox: tuple[float, float, float, float], matrix: np.ndarray) -> tuple[float, ...]:
    x0, y0, x1, y1 = bbox
    corners = np.array([[x0, y0, 1], [x1, y0, 1], [x0, y1, 1], [x1, y1, 1]]) @ matrix
    return tuple(
        float(v)
        for v in (corners[:, 0].min(), corners[:, 1].min(), corners[:, 0].max(), corners[:, 1].max())
    )


def _numbers(text: str) -> list[float]:
    return [float(v) for v in re.findall(r"[-+]?\d*\.?\d+", text)]


def _resolve_do(page: Any, name: str, ctm: np.ndarray, forms: dict, images: dict) -> Placed | None:
    """Box, in page mm, of XObject ``name`` drawn with the current transformation ``ctm``."""
    doc = page.parent
    if name in forms:
        xref = forms[name]
        bbox = _numbers(doc.xref_get_key(xref, "BBox")[1])[:4]
        kind, matrix_text = doc.xref_get_key(xref, "Matrix")
        form_matrix = _pdf_matrix(_numbers(matrix_text)) if kind == "array" else np.eye(3)
        x0, y0, x1, y1 = _bbox_through(tuple(bbox), form_matrix @ ctm)  # type: ignore[arg-type]
        natural_w = abs(bbox[2] - bbox[0])
        scale, dpi, what = ((x1 - x0) / natural_w if natural_w else None), None, "form"
    elif name in images:
        x0, y0, x1, y1 = _bbox_through((0.0, 0.0, 1.0, 1.0), ctm)
        width_px = images[name][2]
        scale, dpi, what = None, (width_px / ((x1 - x0) / 72.0) if x1 > x0 else None), "image"
    else:
        return None
    height, origin_x, origin_y = page.mediabox.height, page.mediabox.x0, page.mediabox.y0
    box = Rect.from_edges(
        pt_to_mm(x0 - origin_x),
        pt_to_mm(height - (y1 - origin_y)),
        pt_to_mm(x1 - origin_x),
        pt_to_mm(height - (y0 - origin_y)),
    )
    return Placed(name, what, box, scale, dpi)


def _placed_graphics(page: Any, min_size_mm: float) -> list[Placed]:
    """Interpret the page content stream: follow q/Q/cm and record every top-level Do."""
    forms = {name: xref for xref, name, invoker, _ in page.get_xobjects() if invoker == 0}
    images = {img[7]: img for img in page.get_images(full=True) if img[-1] == 0}
    # Remove inline images (binary data between ID and EI) before tokenizing.
    content = re.sub(rb"\bBI\b.*?\bID\b.*?\bEI\b", b" ", page.read_contents(), flags=re.DOTALL)

    ctm = np.eye(3)
    stack: list[np.ndarray] = []
    operands: list[bytes] = []
    placed: list[Placed] = []
    for match in _TOKEN.finditer(content):
        token = match.group(0)
        if token.startswith(b"%"):
            continue
        if _NUMBER.fullmatch(token) or token.startswith((b"/", b"(", b"<", b"[", b"]")):
            operands.append(token)
            continue
        if token == b"q":
            stack.append(ctm.copy())
        elif token == b"Q":
            ctm = stack.pop() if stack else np.eye(3)
        elif token == b"cm" and len(operands) >= 6:
            ctm = _pdf_matrix([float(v) for v in operands[-6:]]) @ ctm
        elif token == b"Do" and operands:
            name = operands[-1].decode("latin-1").lstrip("/")
            item = _resolve_do(page, name, ctm, forms, images)
            if item is not None and item.box.w >= min_size_mm and item.box.h >= min_size_mm:
                placed.append(item)
        operands.clear()
    return placed


def _inner_rects(page: Any, box: Rect, min_area: float = 0.04) -> list[Rect]:
    """Filled rectangles inside ``box``: the plotting areas of matplotlib axes.

    A matplotlib axes paints its background as a single rectangle, so a vector panel keeps
    its axes rectangles in the PDF. Raster panels (PNG) contain no such information.
    """
    found: list[Rect] = []
    for item in page.get_drawings():
        if item["type"] not in {"f", "fs"} or len(item["items"]) != 1:
            continue
        r = item["rect"]
        if r.x1 - r.x0 <= 0 or r.y1 - r.y0 <= 0:  # lines, not areas
            continue
        rect = Rect.from_edges(pt_to_mm(r.x0), pt_to_mm(r.y0), pt_to_mm(r.x1), pt_to_mm(r.y1))
        if rect.w < 1 or rect.h < 1 or not box.contains(rect, tol=0.2):
            continue
        area = rect.w * rect.h
        if area < min_area * box.w * box.h or area > 0.98 * box.w * box.h:
            continue  # too small, or the panel background itself
        if any(other.intersection_area(rect) > 0.5 * min(area, other.w * other.h) for other in found):
            continue  # nested duplicate (axes patch drawn twice)
        found.append(rect)
    return sorted(found, key=lambda r: (round(r.top / 5), r.left))


def _letters(page: Any, min_size_pt: float = 6.0) -> list[Letter]:
    found = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                text = span["text"].strip().strip("()")
                if len(text) != 1 or not text.isalpha() or span["size"] < min_size_pt:
                    continue
                x0, y0, x1, y1 = span["bbox"]
                bold = bool(span["flags"] & 16) or "bold" in span["font"].lower()
                box = Rect.from_edges(pt_to_mm(x0), pt_to_mm(y0), pt_to_mm(x1), pt_to_mm(y1))
                found.append(Letter(text, box, span["size"], bold))
    return found


def _union(rects: list[Rect]) -> Rect:
    return Rect.from_edges(
        min(r.left for r in rects),
        min(r.top for r in rects),
        max(r.right for r in rects),
        max(r.bottom for r in rects),
    )


def _group_by_letter(placed: list[Placed], letters: list[Letter]) -> dict[str, list[Any]]:
    """Assign each graphic to the nearest label letter above-left of it."""

    def in_corner(letter: Letter, box: Rect) -> bool:
        # Labels are often drawn over the top-left corner of the panel graphic itself.
        return letter.box.left - box.left < CORNER_MM and letter.box.top - box.top < CORNER_MM

    # A letter is a label when it sits at the top-left corner of some graphic, or outside
    # every graphic. Letters deep inside a graphic are part of the plot, not labels. A label
    # can lie inside a *neighbouring* panel's box when panels interlock, hence the "any".
    candidates = [
        letter
        for letter in letters
        if any(in_corner(letter, p.box) for p in placed)
        or not any(p.box.contains(letter.box, tol=0.5) for p in placed)
    ]
    # Prefer bold letters when some exist (body text also contains single letters).
    if any(letter.bold for letter in candidates):
        candidates = [letter for letter in candidates if letter.bold]
    groups: dict[str, list[Any]] = {}
    for item in placed:
        best, best_distance = None, math.inf
        for letter in candidates:
            if (
                letter.box.left > item.box.left + CORNER_MM
                or letter.box.top > item.box.top + CORNER_MM
            ):
                continue  # a label sits above, left of, or in the top-left corner of its panel
            distance = math.hypot(item.box.left - letter.box.left, item.box.top - letter.box.top)
            if distance < best_distance:
                best, best_distance = letter, distance
        key = best.text if best else f"S{len(groups) + 1:02d}"
        groups.setdefault(key, [best] if best else []).append(item)
    return groups


def _panels_from_groups(groups: dict[str, list[Any]]) -> tuple[dict[str, Any], Rect]:
    """Panel entries (coordinates relative to the figure area) and that area on the page."""
    boxes: dict[str, Rect] = {}
    label_offsets: dict[str, tuple[float, float]] = {}
    for key, members in groups.items():
        letter = members[0] if members and isinstance(members[0], Letter) else None
        rects = [m.box for m in members if isinstance(m, Placed)] + ([letter.box] if letter else [])
        boxes[key] = _union(rects)
        if letter:
            label_offsets[key] = (letter.box.left - boxes[key].left, letter.box.top - boxes[key].top)

    def order(key: str) -> tuple[int, float, float, str]:
        # Lettered panels in label order, then unnamed segments in reading order.
        if key in label_offsets:
            return (0, 0.0, 0.0, key.lower())
        return (1, round(boxes[key].top / 5), boxes[key].left, key)

    area = _union(list(boxes.values()))
    panels: dict[str, Any] = {}
    for key in sorted(boxes, key=order):
        entry: dict[str, Any] = {"box": boxes[key].translated(-area.left, -area.top).to_list(1)}
        if key in label_offsets:
            dx, dy = label_offsets[key]
            entry["label"] = {"text": key, "offset": [round(float(dx), 1), round(float(dy), 1)]}
        else:
            entry["label"] = False
        panels[key] = entry
    return panels, area


def _add_axes_entries(
    panels: dict[str, Any],
    groups: dict[str, list[Any]],
    inner: dict[str, list[Rect]],
    area: Rect,
    notes: list[str],
) -> None:
    """Add one axes entry per plotting area found inside a panel's graphics."""
    for key, entry in panels.items():
        rects = [
            rect.translated(-area.left, -area.top)
            for member in groups.get(key, [])
            if isinstance(member, Placed)
            for rect in inner.get(member.name, [])
        ]
        if not rects:
            continue
        rects.sort(key=lambda r: (round(r.top / 5), r.left))
        entry["axes"] = {f"ax{i + 1}": {"box": rect.to_list(1)} for i, rect in enumerate(rects)}
    without = [k for k in panels if not panels[k].get("axes")]
    if without:
        notes.append(f"no plotting areas found in {without} (raster panels keep no vector shapes)")


def _extract_guides(panels: dict[str, Any], tolerance: float) -> dict[str, dict[str, float]]:
    """Turn axes edges shared by several panels into named guides, and reference them.

    An edge used by axes of at least two different panels is what makes a figure look
    aligned; naming it keeps the alignment through later edits.
    """
    edges: dict[str, dict[float, set[str]]] = {"x": {}, "y": {}}
    for key, panel in panels.items():
        for axes in (panel.get("axes") or {}).values():
            x, y, w, h = axes["box"]
            for axis, values in (("x", (x, x + w)), ("y", (y, y + h))):
                for value in values:
                    match = next(
                        (v for v in edges[axis] if abs(v - value) <= tolerance), round(value, 2)
                    )
                    edges[axis].setdefault(match, set()).add(key)

    guides: dict[str, dict[str, float]] = {"x": {}, "y": {}}
    names: dict[str, dict[float, str]] = {"x": {}, "y": {}}
    for axis in ("x", "y"):
        shared = sorted(v for v, keys in edges[axis].items() if len(keys) > 1)
        for i, value in enumerate(shared, start=1):
            name = f"{'x' if axis == 'x' else 'y'}{i}"
            guides[axis][name] = value
            names[axis][value] = name

    for panel in panels.values():
        for axes in (panel.get("axes") or {}).values():
            x, y, w, h = axes.pop("box")
            edges_named = {}
            for key, axis, value in (
                ("left", "x", x), ("right", "x", x + w), ("top", "y", y), ("bottom", "y", y + h)
            ):  # fmt: skip
                hit = next((v for v in names[axis] if abs(v - value) <= tolerance), None)
                edges_named[key] = names[axis][hit] if hit is not None else round(value, 1)
            axes.update(edges_named)
    return guides


def layout_from_pdf(
    path: str | Path,
    page_number: int = 1,
    *,
    name: str | None = None,
    min_size_mm: float = 5.0,
    use_letters: bool = True,
    detect: bool = False,
    axes: bool = False,
    guides: float | None = None,
    paper: str | None = "a4",
) -> PdfLayout:
    """Draft a layout from placed graphics on one page of a PDF.

    Args:
        path: PDF file (a manuscript page, or a figure-only PDF).
        page_number: 1-based page number.
        name: layout name (default: file stem).
        min_size_mm: ignore placed graphics smaller than this (icons, markers).
        use_letters: name and group panels by nearby single-letter labels.
        detect: skip placed graphics and use gutter detection on the rendered page.
        axes: also read the plotting areas inside each panel (vector panels only).
        guides: with ``axes``, name edges shared by several panels within this tolerance (mm).
        paper: sheet to record when the PDF is a figure on its own (``None`` for no sheet).

    Returns:
        The layout mapping (coordinates relative to the figure area), the placed graphics
        with their scale, the letters found, and notes. ``method`` is ``"detected"`` when
        the page had no placed graphics and gutter detection on the rendered page was used.
    """
    import pymupdf

    path = Path(path)
    with pymupdf.open(path) as doc:
        page = doc[page_number - 1]
        placed = [] if detect else _placed_graphics(page, min_size_mm)
        letters = _letters(page) if use_letters else []
        notes: list[str] = []
        if not placed:
            return _detect_fallback(page, path, name, notes, paper)
        coverage = _placed_coverage(page, placed)
        inner = (
            {name: _inner_rects(page, item.box) for name, item in ((p.name, p) for p in placed)}
            if axes
            else {}
        )

        groups = (
            _group_by_letter(placed, letters)
            if use_letters
            else {f"S{i + 1:02d}": [p] for i, p in enumerate(placed)}
        )
        panels, area = _panels_from_groups(groups)
        sheet, sheet_paper = _sheet_section(page, area, paper)
    if axes:
        _add_axes_entries(panels, groups, inner, area, notes)
        if guides is not None:
            found = _extract_guides(panels, guides)
            count = len(found["x"]) + len(found["y"])
            notes.append(
                f"{count} guides from edges shared by several panels (tolerance {guides} mm)"
            )

    for item in placed:
        if item.scale is not None and abs(item.scale - 1) > 0.02:
            notes.append(
                f"{item.name}: vector graphic placed at {item.scale:.0%} of its size "
                f"(its fonts print at {item.scale:.2f}x their nominal size)"
            )
        if item.dpi is not None and item.dpi < 300:
            notes.append(f"{item.name}: raster image at {item.dpi:.0f} dpi (< 300 dpi)")

    if coverage < 0.5:
        notes.append(
            f"placed graphics cover only {coverage:.0%} of the drawn content: parts of the figure "
            "are flattened into paths; check the wireframe, or use --detect"
        )
    data: dict[str, Any] = {"schema": 1, "name": name or path.stem}
    if sheet:
        data["page"] = sheet  # the sheet; `area` is the figure on it
    data["area"] = {"width": round(float(area.w), 1), "height": round(float(area.h), 1)}
    if axes and guides is not None:
        data["guides"] = found
    data["panels"] = panels
    return PdfLayout(data, placed, letters, "placed", notes, area, sheet_paper)


def _placed_coverage(page: Any, placed: list[Placed]) -> float:
    """Share of drawn content (paths, text, images) near the placed graphics that they cover."""
    area = _union([p.box for p in placed])
    margin = 20.0  # mm around the placed graphics, to catch flattened neighbours
    region = Rect.from_edges(
        area.left - margin, area.top - margin, area.right + margin, area.bottom + margin
    )
    drawn = 0.0
    covered = 0.0
    for _kind, bbox in page.get_bboxlog():
        x0, y0, x1, y1 = (pt_to_mm(v) for v in bbox)
        if x1 - x0 <= 0 or y1 - y0 <= 0:
            continue
        rect = Rect.from_edges(x0, y0, x1, y1)
        if not region.contains(rect):
            continue
        size = rect.w * rect.h
        drawn += size
        if any(p.box.contains(rect, tol=0.5) for p in placed):
            covered += size
    return covered / drawn if drawn else 1.0


def _paper_of(page: Any) -> str | None:
    """The paper name of a PDF page, when its size is one plotplate knows."""
    from .layout import PAPERS

    width, height = pt_to_mm(page.rect.width), pt_to_mm(page.rect.height)
    return next(
        (name for name, (w, h) in PAPERS.items() if abs(w - width) < 2 and abs(h - height) < 2),
        None,
    )


def _sheet_section(page: Any, area: Rect, paper: str | None) -> tuple[dict[str, Any], str | None]:
    """The ``page:`` section for a drafted layout, and the paper it came from.

    A manuscript page tells us its own paper size, so the draft records it. A figure-only
    PDF (the whole page is the figure) says nothing about the sheet, and then ``paper`` --
    what the caller asked for -- is used. Margins are made to fit the figure width; edit
    them to match the manuscript.
    """
    from .layout import sheet_for

    found = _paper_of(page)
    whole_page = area.w > pt_to_mm(page.rect.width) - 10 and area.h > pt_to_mm(page.rect.height) - 10
    name = paper if (found is None or whole_page) else found
    return sheet_for(name, area.w), name


def _detect_fallback(
    page: Any, path: Path, name: str | None, notes: list[str], paper: str | None = None
) -> PdfLayout:
    import tempfile

    from .detect import draft_layout
    from .layout import sheet_for

    notes.append("used gutter detection on the rendered page (no placed graphics were used)")
    width_mm = pt_to_mm(page.rect.width)
    with tempfile.TemporaryDirectory() as tmp:
        image = Path(tmp) / "page.png"
        page.get_pixmap(dpi=300).save(image)
        data = draft_layout(image, width_mm, name=name or path.stem)
    page_area = Rect(0.0, 0.0, width_mm, pt_to_mm(page.rect.height))
    found = _paper_of(page) or paper
    sheet = sheet_for(found, width_mm)
    if sheet:
        data = {"schema": data["schema"], "name": data["name"], "page": sheet, **data}
    notes.append("whole page used: body text and captions become segments; delete or merge them")
    return PdfLayout(data, [], [], "detected", notes, page_area, found)


def render_area(
    path: str | Path, out: str | Path, area: Rect, page_number: int = 1, dpi: int = 200
) -> Path:
    """Render the figure area of a PDF page to PNG (for wireframe backgrounds)."""
    import pymupdf

    from .geometry import mm_to_pt

    clip = pymupdf.Rect(
        mm_to_pt(area.left), mm_to_pt(area.top), mm_to_pt(area.right), mm_to_pt(area.bottom)
    )
    with pymupdf.open(path) as doc:
        doc[page_number - 1].get_pixmap(dpi=dpi, clip=clip).save(out)
    return Path(out)
