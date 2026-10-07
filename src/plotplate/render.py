"""Visual outputs of a layout: wireframes (for checking a spec) and full-figure previews.

The preview places each panel's PDF at its *natural size* at the top-left of its box,
exactly as the generated LaTeX does, so what you see locally is what Overleaf produces
(apart from the panel-letter font). Panels with a wrong size are outlined in red.
"""

from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Rectangle

from .geometry import Rect, mm_to_pt, pt_to_mm
from .layout import PAPERS as PAPER_MM, Issue, Layout
from .style import label_text

SIZE_TOL_MM = 0.1


def wireframe(
    layout: Layout,
    out: str | Path,
    background: str | Path | None = None,
    dpi: int = 200,
    show_axes: bool = True,
    show_guides: bool = True,
) -> Path:
    """Draw panel boxes (blue), axes (orange) and guides (grey), optionally over a screenshot."""
    out = Path(out)
    w, h = layout.width, layout.height
    fig = plt.figure(figsize=(w / 25.4 * 2, h / 25.4 * 2))  # 2x so labels stay legible
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, w)
    ax.set_ylim(h, 0)
    ax.set_axis_off()
    ax.add_patch(Rectangle((0, 0), w, h, fill=False, edgecolor="black", linewidth=0.8))
    if background is not None:
        ax.imshow(plt.imread(background), extent=(0, w, h, 0), alpha=0.6, zorder=0, aspect="auto")
    if show_guides:
        for name, x in layout.guides["x"].items():
            ax.axvline(x, color="0.5", linestyle=":", linewidth=0.8)
            ax.text(x, h, f" {name}", rotation=90, va="bottom", ha="right", fontsize=6, color="0.4")
        for name, y in layout.guides["y"].items():
            ax.axhline(y, color="0.5", linestyle=":", linewidth=0.8)
            ax.text(w, y, f"{name} ", va="bottom", ha="right", fontsize=6, color="0.4")
    for name, spec in layout.panels.items():
        box = spec.box
        ax.add_patch(Rectangle((box.x, box.y), box.w, box.h, facecolor="#3b82f6", alpha=0.12))
        ax.add_patch(
            Rectangle((box.x, box.y), box.w, box.h, fill=False, edgecolor="#1d4ed8", linewidth=1.2)
        )
        ax.text(
            box.x + box.w / 2,
            box.y + box.h / 2,
            name,
            ha="center",
            va="center",
            fontsize=14,
            color="#1d4ed8",
            weight="bold",
        )
        ax.text(
            box.x + 0.8,
            box.bottom - 0.8,
            f"{box.w:.1f} x {box.h:.1f}",
            fontsize=6,
            color="#1d4ed8",
            va="bottom",
        )
        if show_axes:
            for ax_spec in spec.axes.values():
                for r in ax_spec.rects():
                    ax.add_patch(
                        Rectangle(
                            (r.x, r.y),
                            r.w,
                            r.h,
                            fill=False,
                            edgecolor="#d97706",
                            linewidth=0.8,
                            linestyle="--",
                        )
                    )
                ax.text(
                    ax_spec.region.x + 0.5,
                    ax_spec.region.y + 0.5,
                    ax_spec.name,
                    fontsize=6,
                    color="#b45309",
                    va="top",
                )
    fig.savefig(out, dpi=dpi)
    plt.close(fig)
    return out


def _font_file(family: list[str], bold: bool) -> str | None:
    props = FontProperties(family=family, weight="bold" if bold else "normal")
    try:
        return font_manager.findfont(props, fallback_to_default=False)
    except ValueError:
        return None


def panel_status(layout: Layout) -> dict[str, dict[str, Any]]:
    """For each panel: file presence, PDF natural size, stale report, and issues."""
    import pymupdf

    status: dict[str, dict[str, Any]] = {}
    for name, spec in layout.panels.items():
        pdf = layout.panels_dir / f"{name}.pdf"
        info: dict[str, Any] = {"pdf": pdf, "exists": pdf.exists(), "issues": []}
        if pdf.exists():
            with pymupdf.open(pdf) as doc:
                page_rect = doc[0].rect
            size = (pt_to_mm(page_rect.width), pt_to_mm(page_rect.height))
            info["size_mm"] = size
            if abs(size[0] - spec.box.w) > SIZE_TOL_MM or abs(size[1] - spec.box.h) > SIZE_TOL_MM:
                info["issues"].append(
                    Issue(
                        "error",
                        "panel-size",
                        f"panel {name}: file is {size[0]:.2f}x{size[1]:.2f} mm, "
                        f"box is {spec.box.w:.2f}x{spec.box.h:.2f} mm",
                    )
                )
            report = layout.panels_dir / f"{name}.json"
            if report.exists():
                meta = json.loads(report.read_text())
                for issue in meta.get("issues", []):
                    if issue["level"] != "info":
                        info["issues"].append(
                            Issue(issue["level"], issue["code"], f"panel {name}: {issue['message']}")
                        )
                if report.stat().st_mtime + 1 < pdf.stat().st_mtime:
                    info["issues"].append(
                        Issue(
                            "warning",
                            "panel-report-stale",
                            f"panel {name}: PDF newer than its report",
                        )
                    )
            if layout.path is not None and layout.path.stat().st_mtime > pdf.stat().st_mtime:
                info["issues"].append(
                    Issue(
                        "info",
                        "panel-older-than-layout",
                        f"panel {name}: layout changed after the panel was saved",
                    )
                )
        else:
            info["issues"].append(
                Issue("warning", "panel-missing", f"panel {name}: {pdf.name} not found")
            )
        status[name] = info
    return status


def compose(
    layout: Layout,
    *,
    labels: bool = True,
    outlines: bool = False,
    highlight: str | None = None,
    strict: bool = False,
) -> Any:
    """Build the full figure as an in-memory PDF (``pymupdf.Document``) from panel PDFs.

    Panels are placed at their natural size at the top-left of their box, exactly like
    the generated LaTeX. Panel letters use the style's font (embedded).

    Args:
        layout: the figure layout.
        labels: draw panel letters.
        outlines: outline every panel box.
        highlight: outline only this panel (thicker).
        strict: raise instead of drawing placeholders for missing or wrongly sized panels.
    """
    import pymupdf

    status = panel_status(layout)
    if strict:
        # Reported as errors here, whatever level they carry elsewhere: they stop the export.
        problems = [
            str(Issue("error", issue.code, issue.message))
            for info in status.values()
            for issue in info["issues"]
            if issue.code in {"panel-missing", "panel-size"}
        ]
        if problems:
            raise ValueError(
                "cannot export the figure:\n  "
                + "\n  ".join(problems)
                + "\n  draw the panels first, or use --allow-missing for a draft"
            )
    label_style = layout.style["panel_label"]
    families = list(layout.style["font"]["family"])
    label_font = _font_file(families, bold=label_style["weight"] == "bold")

    doc = pymupdf.open()
    page = doc.new_page(width=mm_to_pt(layout.width), height=mm_to_pt(layout.height))
    font = pymupdf.Font(fontfile=label_font) if label_font else pymupdf.Font("helv")

    def pt_rect(r: Rect) -> pymupdf.Rect:
        return pymupdf.Rect(mm_to_pt(r.left), mm_to_pt(r.top), mm_to_pt(r.right), mm_to_pt(r.bottom))

    for name, spec in layout.panels.items():
        info = status[name]
        if info["exists"]:
            w_mm, h_mm = info["size_mm"]
            natural = Rect(spec.box.x, spec.box.y, w_mm, h_mm)
            with pymupdf.open(info["pdf"]) as src:
                page.show_pdf_page(pt_rect(natural), src, 0)
            bad = any(i.code == "panel-size" for i in info["issues"])
            if bad or outlines:
                page.draw_rect(
                    pt_rect(spec.box), color=(0.8, 0.1, 0.1) if bad else (0.2, 0.4, 0.9), width=0.5
                )
        else:
            page.draw_rect(
                pt_rect(spec.box),
                color=(0.6, 0.6, 0.6),
                fill=(0.95, 0.95, 0.95),
                width=0.5,
                dashes="[2 2] 0",
            )
            page.insert_text(
                pymupdf.Point(mm_to_pt(spec.box.x + 2), mm_to_pt(spec.box.y + 6)),
                f"{name} (missing)",
                fontsize=8,
                color=(0.4, 0.4, 0.4),
            )
        if labels and spec.label:
            size = float(label_style["size"])
            x = mm_to_pt(spec.box.x + spec.label_offset[0])
            top = mm_to_pt(spec.box.y + spec.label_offset[1])
            writer = pymupdf.TextWriter(page.rect)
            writer.append(
                pymupdf.Point(x, top + font.ascender * size),
                label_text(layout.style, spec.label),
                font=font,
                fontsize=size,
            )
            writer.write_text(page)

    if highlight is not None and highlight in layout.panels:
        page.draw_rect(pt_rect(layout.panels[highlight].box), color=(0.1, 0.45, 0.95), width=1.2)
    return doc


def preview(
    layout: Layout,
    out_dir: str | Path | None = None,
    *,
    labels: bool = True,
    outlines: bool = False,
    highlight: str | None = None,
    rules: dict[str, list[float]] | None = None,
    png_dpi: int = 200,
) -> dict[str, Path]:
    """Compose the figure, cropped, into ``figure.pdf``/``figure.png``/``figure.svg``.

    This is the composer behind :func:`page_view`, :func:`export_figure` and
    :meth:`plotplate.Panel.context`, which call it with a folder of their own; a build writes
    the page view instead, so nothing lands in the figure folder unless a caller asks for it.

    ``outlines`` draws every panel box, ``highlight`` only the named panel's box (thicker).
    """
    out_dir = Path(out_dir) if out_dir is not None else layout.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = compose(layout, labels=labels, outlines=outlines, highlight=highlight)
    if rules:
        import pymupdf

        page = doc[0]
        for value in rules.get("x", []):
            page.draw_line(
                pymupdf.Point(mm_to_pt(value), 0),
                pymupdf.Point(mm_to_pt(value), mm_to_pt(layout.height)),
                color=(0.85, 0.2, 0.2), width=0.3, dashes="[2 2] 0",
            )  # fmt: skip
        for value in rules.get("y", []):
            page.draw_line(
                pymupdf.Point(0, mm_to_pt(value)),
                pymupdf.Point(mm_to_pt(layout.width), mm_to_pt(value)),
                color=(0.85, 0.2, 0.2), width=0.3, dashes="[2 2] 0",
            )  # fmt: skip
    pdf_path, png_path = out_dir / "figure.pdf", out_dir / "figure.png"
    doc.save(pdf_path, garbage=3, deflate=True)
    doc[0].get_pixmap(dpi=png_dpi).save(png_path)
    doc.close()
    svg_path = _preview_svg(layout, out_dir / "figure.svg", labels=labels)
    return {"pdf": pdf_path, "png": png_path, "svg": svg_path}


def export_figure(
    layout: Layout, out: str | Path, dpi: int | None = None, allow_missing: bool = False
) -> tuple[Path, list[Issue]]:
    """Write the final composite figure file (one file, all panels, letters included).

    This is the only command that writes the figure as one cropped file -- for a journal's
    upload form, for a co-author, or to hand-finish in a drawing program.

    The format follows the file extension: ``.pdf`` (vector, fonts embedded), ``.png``,
    ``.tif``/``.tiff`` (LZW-compressed, RGB, as PLOS requires), or ``.svg``, which links the
    panel SVGs so Inkscape can open it and every panel stays editable. Missing or wrongly
    sized panels are an error, because the file is a deliverable; ``allow_missing`` turns them
    into empty boxes and a warning instead, for a draft to show someone. Returns the path and
    the warnings (the journal's accepted formats, and the holes when any were allowed).
    """
    from PIL import Image

    out = Path(out)
    fmt = out.suffix.lower().lstrip(".")
    fmt = "tiff" if fmt == "tif" else fmt
    if fmt not in {"pdf", "png", "tiff", "svg"}:
        raise ValueError(f"unsupported export format {out.suffix!r}; use .pdf, .png, .tif or .svg")
    issues: list[Issue] = []
    deliverable = (layout.journal or {}).get("deliverable") or {}
    accepted = [str(f).lower() for f in deliverable.get("formats") or []]
    if accepted and fmt not in accepted and not (fmt == "tiff" and "tif" in accepted):
        journal = (layout.journal or {}).get("name")
        message = f"{journal} accepts {accepted} for final figures, not {fmt}"
        issues.append(Issue("warning", "export-format", message))
    if allow_missing:
        issues += [
            Issue("warning", issue.code, f"{issue.message} (drawn as an empty box)")
            for info in panel_status(layout).values()
            for issue in info["issues"]
            if issue.code in {"panel-missing", "panel-size"}
        ]
    dpi = dpi or int(deliverable.get("raster_dpi") or layout.style["export"]["dpi"])
    out.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "svg":
        return _preview_svg(layout, out, labels=True), issues
    doc = compose(layout, strict=not allow_missing)
    if fmt == "pdf":
        doc.save(out, garbage=3, deflate=True)
    else:
        pix = doc[0].get_pixmap(dpi=dpi, alpha=False)
        image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        if fmt == "tiff":
            image.save(out, format="TIFF", compression="tiff_lzw", dpi=(dpi, dpi))
        else:
            image.save(out, format="PNG", dpi=(dpi, dpi))
    doc.close()
    return out, issues


def page_view(
    layout: Layout,
    out_dir: str | Path | None = None,
    paper: str = "a4",
    *,
    outlines: bool = False,
) -> dict[str, Path]:
    """Show the figure as it would sit on a printed page: centred, with a caption and text lines.

    This is what a build leaves to look at (``page.pdf``, ``page.png``, ``page.svg``): the
    figure at its real size, where a float would put it, with grey bars standing in for the
    body text. A figure has no margins of its own -- margins and the caption belong to the
    manuscript -- so this is the only rendering that shows whether it fits the printed sheet.

    ``plotplate export`` writes the figure itself, cropped, when one file is what is needed.

    ``outlines`` draws every panel box, for checking the geometry rather than the content.
    """
    import pymupdf

    out_dir = Path(out_dir) if out_dir is not None else layout.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    # The layout's own `page:` section wins; `paper` only supplies one when it declares none.
    sheet = layout.sheet_geometry(paper)
    if sheet is None:
        raise ValueError(f"unknown paper {paper!r}; use one of {list(PAPER_MM)}")
    paper_w, paper_h = sheet.size
    left, top = sheet.area.left, sheet.area.top
    if left < 0:
        raise ValueError(f"figure width {layout.width} mm does not fit on {sheet.paper} paper")
    figure = compose(layout, outlines=outlines)
    doc = pymupdf.open()
    page = doc.new_page(width=mm_to_pt(paper_w), height=mm_to_pt(paper_h))
    target = Rect(left, top, layout.width, layout.height)
    page.show_pdf_page(
        pymupdf.Rect(
            mm_to_pt(target.left),
            mm_to_pt(target.top),
            mm_to_pt(target.right),
            mm_to_pt(target.bottom),
        ),
        figure,
        0,
    )
    figure.close()
    text_left, text_right = min(left, 25.0), max(target.right, paper_w - 25.0)
    y = target.bottom + 6
    page.insert_text(
        pymupdf.Point(mm_to_pt(text_left), mm_to_pt(y)),
        f"Figure 1 | Caption of {layout.name} ({layout.width:g} x {layout.height:g} mm).",
        fontsize=8,
        fontname="hebo",
    )
    y += 6
    while y < paper_h - 20:  # grey bars standing in for body text
        page.draw_rect(
            pymupdf.Rect(mm_to_pt(text_left), mm_to_pt(y), mm_to_pt(text_right), mm_to_pt(y + 1.2)),
            color=None,
            fill=(0.85, 0.85, 0.85),
        )
        y += 4.5
    pdf_path, png_path = out_dir / "page.pdf", out_dir / "page.png"
    svg_path = out_dir / "page.svg"
    doc.save(pdf_path, garbage=3, deflate=True)
    page.get_pixmap(dpi=200).save(png_path)
    # Text stays text, as in every other SVG this package writes, so the page view can be
    # opened in a drawing program and read.
    svg_path.write_text(page.get_svg_image(text_as_path=False), encoding="utf-8")
    doc.close()
    return {"pdf": pdf_path, "png": png_path, "svg": svg_path}


#: Inkscape reads these: a labelled layer is a layer a person can hide, lock and pick in the UI.
SVG_NS = "http://www.w3.org/2000/svg"
INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
_LABEL = f"{{{INKSCAPE_NS}}}label"


def _q(tag: str) -> str:
    """One SVG tag name, namespaced."""
    return f"{{{SVG_NS}}}{tag}"


def _layer(parent: ET.Element, label: str) -> ET.Element:
    """An Inkscape layer: a group a drawing program shows by name."""
    return ET.SubElement(
        parent,
        _q("g"),
        {
            "id": label,
            f"{{{INKSCAPE_NS}}}groupmode": "layer",
            _LABEL: label,
        },
    )


def _preview_svg(layout: Layout, path: Path, labels: bool) -> Path:
    """The figure as one SVG that *links* the panel SVGs, so every panel stays editable."""
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("inkscape", INKSCAPE_NS)
    w, h = layout.width, layout.height
    root = ET.Element(
        _q("svg"), {"width": f"{w:g}mm", "height": f"{h:g}mm", "viewBox": f"0 0 {w:g} {h:g}"}
    )
    panels = _layer(root, "panels")
    letters = _layer(root, "labels")
    label_style = layout.style["panel_label"]
    for name, spec in layout.panels.items():
        svg = layout.panels_dir / f"{name}.svg"
        href = os.path.relpath(svg, path.parent)
        ET.SubElement(
            panels,
            _q("image"),
            {
                "id": f"panel-{name}",
                _LABEL: name,
                "{http://www.w3.org/1999/xlink}href": href,
                "x": f"{spec.box.x:g}",
                "y": f"{spec.box.y:g}",
                "width": f"{spec.box.w:g}",
                "height": f"{spec.box.h:g}",
                "preserveAspectRatio": "none",
            },
        )
        if labels and spec.label:
            size_mm = pt_to_mm(float(label_style["size"]))
            text = ET.SubElement(
                letters,
                _q("text"),
                {
                    "x": f"{spec.box.x + spec.label_offset[0]:g}",
                    "y": f"{spec.box.y + spec.label_offset[1] + 0.72 * size_mm:g}",
                    "style": f"font-family:{layout.style['font']['family'][0]};"
                    f"font-size:{size_mm:.3f}px;font-weight:{label_style['weight']}",
                },
            )
            text.text = label_text(layout.style, spec.label)
    tree = ET.ElementTree(root)
    ET.indent(tree)
    tree.write(path, encoding="utf-8", xml_declaration=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("\n")
    return path
