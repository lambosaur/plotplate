"""Round-trip layouts through Inkscape SVG files.

Export writes a page-sized SVG whose user unit is 1 mm, with layers:

- ``background`` (locked): optional screenshot to trace over,
- ``guides`` (locked): named guide lines, for orientation only,
- ``panels``: one rectangle per panel, labelled with the panel name,
- ``axes``: one rectangle per axes entry, labelled ``<panel>/<axes>``.

Import reads the rectangles of the ``panels`` and ``axes`` layers back (any transforms,
any document units) and updates the boxes of a layout mapping. Everything else in the
layout (style, guides, grid settings of axes) is kept, so SVG editing only moves boxes.
"""

from __future__ import annotations

import copy
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import numpy as np

from .geometry import Rect
from .layout import Issue, Layout, area_section

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
SODIPODI_NS = "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"
for _prefix, _uri in {
    "": SVG_NS,
    "xlink": XLINK_NS,
    "inkscape": INKSCAPE_NS,
    "sodipodi": SODIPODI_NS,
}.items():
    ET.register_namespace(_prefix, _uri)

_UNIT_MM = {
    "mm": 1.0,
    "cm": 10.0,
    "in": 25.4,
    "pt": 25.4 / 72,
    "pc": 25.4 / 6,
    "px": 25.4 / 96,
    "": 25.4 / 96,
}
_LABEL = f"{{{INKSCAPE_NS}}}label"
_GROUPMODE = f"{{{INKSCAPE_NS}}}groupmode"


def _q(tag: str) -> str:
    return f"{{{SVG_NS}}}{tag}"


def _layer(parent: ET.Element, label: str, locked: bool = False) -> ET.Element:
    attrs = {"id": f"layer-{label}", _GROUPMODE: "layer", _LABEL: label}
    if locked:
        attrs[f"{{{SODIPODI_NS}}}insensitive"] = "true"
    return ET.SubElement(parent, _q("g"), attrs)


def _rect(parent: ET.Element, rect: Rect, label: str, style: str, element_id: str) -> None:
    attrs = {"id": element_id, _LABEL: label, "style": style}
    attrs.update(
        {k: f"{v:g}" for k, v in zip(["x", "y", "width", "height"], rect.to_list(3), strict=True)}
    )
    ET.SubElement(parent, _q("rect"), attrs)


def _safe_id(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", text)


def export_svg(layout: Layout, path: str | Path, background: str | Path | None = None) -> Path:
    """Write ``layout`` as an Inkscape-editable SVG (1 user unit = 1 mm)."""
    path = Path(path)
    w, h = layout.width, layout.height
    root = ET.Element(
        _q("svg"),
        {"width": f"{w:g}mm", "height": f"{h:g}mm", "viewBox": f"0 0 {w:g} {h:g}", "version": "1.1"},
    )
    ET.SubElement(
        root,
        f"{{{SODIPODI_NS}}}namedview",
        {"id": "namedview", f"{{{INKSCAPE_NS}}}document-units": "mm", "pagecolor": "#ffffff"},
    )
    if background is not None:
        href = os.path.relpath(Path(background).resolve(), path.resolve().parent)
        layer = _layer(root, "background", locked=True)
        ET.SubElement(
            layer,
            _q("image"),
            {
                "id": "background-image",
                f"{{{XLINK_NS}}}href": href,
                "x": "0",
                "y": "0",
                "width": f"{w:g}",
                "height": f"{h:g}",
                "preserveAspectRatio": "none",
                "style": "opacity:0.5",
            },
        )

    guides = _layer(root, "guides", locked=True)
    line = "stroke:#888888;stroke-width:0.15;stroke-dasharray:0.8,0.8"
    for name, x in layout.guides["x"].items():
        ET.SubElement(
            guides,
            _q("line"),
            {
                "id": f"guide-x-{_safe_id(name)}",
                _LABEL: name,
                "x1": f"{x:g}",
                "y1": "0",
                "x2": f"{x:g}",
                "y2": f"{h:g}",
                "style": line,
            },
        )
    for name, y in layout.guides["y"].items():
        ET.SubElement(
            guides,
            _q("line"),
            {
                "id": f"guide-y-{_safe_id(name)}",
                _LABEL: name,
                "x1": "0",
                "y1": f"{y:g}",
                "x2": f"{w:g}",
                "y2": f"{y:g}",
                "style": line,
            },
        )

    panels = _layer(root, "panels")
    axes_layer = _layer(root, "axes")
    for name, spec in layout.panels.items():
        _rect(
            panels,
            spec.box,
            name,
            "fill:#3b82f6;fill-opacity:0.12;stroke:#1d4ed8;stroke-width:0.3",
            f"panel-{_safe_id(name)}",
        )
        for ax_name, ax in spec.axes.items():
            _rect(
                axes_layer,
                ax.region,
                f"{name}/{ax_name}",
                "fill:#f59e0b;fill-opacity:0.15;stroke:#b45309;stroke-width:0.2",
                f"axes-{_safe_id(name)}-{_safe_id(ax_name)}",
            )

    tree = ET.ElementTree(root)
    ET.indent(tree)
    tree.write(path, encoding="utf-8", xml_declaration=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("\n")
    return path


# ---------------------------------------------------------------------- import

_TRANSFORM = re.compile(r"(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)")


def _parse_transform(text: str | None) -> np.ndarray:
    matrix = np.eye(3)
    for kind, args_text in _TRANSFORM.findall(text or ""):
        args = [float(a) for a in re.split(r"[\s,]+", args_text.strip()) if a]
        if kind == "matrix":
            a, b, c, d, e, f = args
            step = np.array([[a, c, e], [b, d, f], [0, 0, 1]])
        elif kind == "translate":
            step = np.array([[1, 0, args[0]], [0, 1, args[1] if len(args) > 1 else 0], [0, 0, 1]])
        elif kind == "scale":
            sy = args[1] if len(args) > 1 else args[0]
            step = np.diag([args[0], sy, 1.0])
        elif kind == "rotate" and abs(args[0]) % 360 < 1e-9:
            step = np.eye(3)
        else:
            raise ValueError(f"Unsupported SVG transform {kind}({args_text}); keep boxes unrotated")
        matrix = matrix @ step
    return matrix


def _length_mm(text: str) -> float:
    match = re.fullmatch(r"\s*([0-9.eE+-]+)\s*([a-z]*)\s*", text)
    if not match or match.group(2) not in _UNIT_MM:
        raise ValueError(f"Cannot parse SVG length {text!r}")
    return float(match.group(1)) * _UNIT_MM[match.group(2)]


_ILLUSTRATOR_ESCAPE = re.compile(r"_x([0-9A-Fa-f]{2})_")


def _object_name(element: ET.Element) -> str:
    """Inkscape label, else the id (Illustrator stores object names there, escaping `/` as _x2F_).

    Illustrator appends ``_1_``, ``_2_``… to duplicate names; those suffixes are removed.
    """
    label = element.get(_LABEL)
    if label:
        return label.strip()
    raw = element.get("id") or ""
    if re.fullmatch(r"(rect|g|path|layer)[-_]?\d*", raw):  # generated ids are not names
        return ""
    name = _ILLUSTRATOR_ESCAPE.sub(lambda m: chr(int(m.group(1), 16)), raw)
    return re.sub(r"_\d+_$", "", name).strip()


def _page_units(root: ET.Element) -> tuple[float, float, np.ndarray]:
    """Page size in mm and the matrix from SVG user units to mm."""
    width_mm, height_mm = _length_mm(root.get("width", "0")), _length_mm(root.get("height", "0"))
    view_box = root.get("viewBox")
    if not view_box:
        return width_mm, height_mm, np.diag([_UNIT_MM["px"], _UNIT_MM["px"], 1.0])
    vx, vy, vw, vh = (float(v) for v in re.split(r"[\s,]+", view_box.strip()))
    if not width_mm:
        width_mm, height_mm = vw * _UNIT_MM["px"], vh * _UNIT_MM["px"]
    unit = np.array(
        [
            [width_mm / vw, 0, -vx * width_mm / vw],
            [0, height_mm / vh, -vy * height_mm / vh],
            [0, 0, 1],
        ]
    )
    return width_mm, height_mm, unit


def _rect_box(element: ET.Element, matrix: np.ndarray) -> Rect:
    """Axis-aligned box (mm) of an SVG rect after its accumulated transform."""
    x, y = float(element.get("x", 0)), float(element.get("y", 0))
    w, h = float(element.get("width", 0)), float(element.get("height", 0))
    corners = matrix @ np.array([[x, x + w, x, x + w], [y, y, y + h, y + h], [1, 1, 1, 1]])
    box = Rect.from_edges(corners[0].min(), corners[1].min(), corners[0].max(), corners[1].max())
    return Rect(*(float(round(v, 3)) for v in (box.x, box.y, box.w, box.h)))


def _known_ids(base: dict[str, Any] | None) -> dict[str, str]:
    """The ids ``export_svg`` writes, mapped back to the names they stand for.

    Inkscape's "Plain SVG" and "Optimised SVG" drop ``inkscape:label`` and keep only the id,
    and Illustrator has its own ideas about names. The ids are ours (``panel-a``,
    ``axes-a-roc``), so as long as the layout being updated still lists the panel, its name can
    be recovered instead of being read as a new panel called ``panel-a``.
    """
    names: dict[str, str] = {}
    for name, panel in (base or {}).get("panels", {}).items():
        names[f"panel-{_safe_id(str(name))}"] = str(name)
        for axes in (panel or {}).get("axes") or {}:
            names[f"axes-{_safe_id(str(name))}-{_safe_id(str(axes))}"] = f"{name}/{axes}"
    return names


def _axes_label(label: str, names: dict[str, str]) -> str:
    """Turn the id of an axes rectangle back into ``panel/axes``.

    ``axes-A-main`` is what the exporter writes for a panel whose axes comes from ``margins:``,
    and such an axes has no entry of its own in the layout; the panel does, so its name is
    enough to split the id.
    """
    if "/" in label or not label.startswith("axes-"):
        return label
    rest = label.removeprefix("axes-")
    for key, name in names.items():
        prefix = key.removeprefix("panel-") + "-"
        if key.startswith("panel-") and rest.startswith(prefix):
            return f"{name}/{rest[len(prefix) :]}"
    return label


def read_svg_boxes(path: str | Path, names: dict[str, str] | None = None) -> dict[str, Any]:
    """Read page size and labelled rectangles from an SVG (all in mm).

    Args:
        path: the SVG file.
        names: ids to read as names, for files saved without labels (see :func:`_known_ids`).

    Returns:
        ``{"width", "height", "panels": {name: Rect}, "axes": {(panel, axes): Rect},
        "issues": [Issue]}``.
    """
    root = ET.parse(path).getroot()
    width_mm, height_mm, unit = _page_units(root)
    result: dict[str, Any] = {
        "width": width_mm,
        "height": height_mm,
        "panels": {},
        "axes": {},
        "issues": [],
    }

    def record(element: ET.Element, matrix: np.ndarray, layer: str) -> None:
        label = (names or {}).get(element.get("id") or "") or _object_name(element)
        if not label:
            message = f"rect {element.get('id')} in layer {layer} has no label; skipped"
            result["issues"].append(Issue("warning", "svg-unlabelled", message))
        elif layer == "panels":
            result["panels"][label] = _rect_box(element, matrix)
        elif "/" in (label := _axes_label(label, names or {})):
            panel, axes = label.split("/", 1)
            result["axes"][(panel, axes)] = _rect_box(element, matrix)
        else:
            message = f"axes rect {label!r} must be labelled <panel>/<axes>"
            result["issues"].append(Issue("warning", "svg-axes-label", message))

    def walk(element: ET.Element, matrix: np.ndarray, layer: str | None) -> None:
        matrix = matrix @ _parse_transform(element.get("transform"))
        if element.tag == _q("g"):
            # Inkscape marks layers with inkscape:groupmode; Illustrator exports layers as
            # groups whose id is the layer name. A file saved without labels ("Plain SVG")
            # keeps only the id this exporter wrote, `layer-panels`.
            name = _object_name(element).lower().removeprefix("layer-")
            if element.get(_GROUPMODE) == "layer" or name in {"panels", "axes"}:
                layer = name
        if element.tag == _q("rect") and layer in {"panels", "axes"}:
            record(element, matrix, layer)
            return
        for child in element:
            walk(child, matrix, layer)

    walk(root, unit, None)
    return result


def import_svg(
    path: str | Path, base: dict[str, Any] | None = None
) -> tuple[dict[str, Any], list[Issue]]:
    """Update (a copy of) the layout mapping ``base`` with the boxes drawn in ``path``.

    Panels and axes found in the SVG get explicit page-coordinate ``box`` entries (guide
    references on edited axes are replaced by numbers). Panels missing from the SVG are
    reported, not deleted, and a rectangle whose label was lost by the drawing program is
    recognised by the id ``plotplate svg-export`` gave it.
    """
    found = read_svg_boxes(path, _known_ids(base))
    issues: list[Issue] = list(found["issues"])
    data: dict[str, Any] = copy.deepcopy(base) if base else {"schema": 1, "name": Path(path).stem}
    area = area_section(data)
    area["width"] = round(found["width"], 2)
    area["height"] = round(found["height"], 2)
    data.pop("mosaic", None)

    panels = data.setdefault("panels", {}) or {}
    data["panels"] = panels
    for name, box in found["panels"].items():
        entry = panels.get(name) or {}
        entry["box"] = box.to_list()
        entry.pop("margins", None)
        panels[name] = entry
    for name in list(panels):
        if name not in found["panels"]:
            issues.append(
                Issue("warning", "svg-panel-missing", f"panel {name} not in the SVG; kept as is")
            )

    for (panel, axes), box in found["axes"].items():
        if panel not in panels:
            issues.append(
                Issue("warning", "svg-axes-orphan", f"axes {panel}/{axes} has no panel; skipped")
            )
            continue
        axes_map = panels[panel].setdefault("axes", {})
        entry = axes_map.get(axes)
        entry = dict(entry) if isinstance(entry, dict) else {}
        for key in ("left", "top", "right", "bottom", "ref"):
            entry.pop(key, None)
        entry["box"] = box.to_list()
        axes_map[axes] = entry
    return data, issues
