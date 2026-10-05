"""Regenerate the images used in README.md and docs/ from a fresh demo build.

Run with `pixi run -e dev docs-figures`. Writes docs/images/*.png, and docs/images/glossary.svg
the first time: the glossary is meant to be corrected by hand afterwards, so an existing SVG is
left alone unless `--force` is given.
"""

import sys
import tempfile
from itertools import pairwise
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.patches

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pymupdf

from plotplate.cli import main

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images"


def _thumbnail(source: Path, target: Path, width_px: int) -> Path:
    from PIL import Image

    with Image.open(source) as image:
        ratio = width_px / image.width
        image.convert("RGB").resize((width_px, round(image.height * ratio))).save(target)
    return target


def _pipeline(steps: list[tuple[str, str, Path]], target: Path) -> None:
    fig, axes = plt.subplots(1, len(steps), figsize=(16, 5.6), gridspec_kw={"wspace": 0.12})
    for ax, (title, command, image) in zip(axes, steps, strict=True):
        ax.imshow(plt.imread(image))
        ax.set_title(title, fontsize=13, weight="bold", loc="left")
        ax.set_xlabel(command, fontsize=10, family="monospace")
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_color("0.7")
    for left, right in pairwise(axes):
        start = left.get_position()
        end = right.get_position()
        y = (start.y0 + start.y1) / 2
        fig.patches.append(
            matplotlib.patches.FancyArrowPatch(
                (start.x1 + 0.002, y), (end.x0 - 0.002, y), transform=fig.transFigure,
                arrowstyle="-|>", mutation_scale=22, color="#1d4ed8", linewidth=2,
            )
        )  # fmt: skip
    fig.savefig(target, dpi=110, bbox_inches="tight")
    plt.close(fig)


# The glossary picture: every word docs/coordinates.md defines, drawn once.
# Two views side by side -- the sheet, and the figure area magnified -- so that no callout
# has to reach across the drawing.
SHEET = (210.0, 297.0)  # A4
MARGINS = {"left": 13.5, "right": 13.5, "top": 25.0, "bottom": 25.0}
AREA = (13.5, 25.0, 183.0, 120.0)  # x, y, w, h in sheet mm
CAPTION = 18.0
ZOOM = 1.55
ZOOM_AT = (268.0, 34.0)  # where the magnified area starts on the canvas
PANELS = {  # layout mm: origin at the area's top-left corner
    "A": (0.0, 0.0, 89.5, 62.0),
    "B": (93.5, 0.0, 89.5, 62.0),
    "C": (0.0, 66.0, 183.0, 54.0),
}
PANEL_AXES = {
    "A": {"roc": (11.0, 8.0, 33.0, 44.0), "prc": (55.0, 8.0, 33.0, 44.0)},
    "B": {"heatmap": (104.5, 8.0, 70.0, 44.0)},
    "C": {"scatter": (11.0, 76.0, 170.0, 36.0)},
}
GUIDE_Y = 52.0  # layout mm: the bottom spine shared by the axes of the first row
GUIDE_X = 11.0  # layout mm: the left spine shared by A/roc and C/scatter
BLUE, AMBER, GREY, INK, SLATE = "#1d4ed8", "#b45309", "#9ca3af", "#111827", "#4b5563"


class View:
    """Maps millimetres of one coordinate system to the canvas."""

    def __init__(self, origin: tuple[float, float] = (0.0, 0.0), scale: float = 1.0) -> None:
        """Place this view at ``origin``, magnified by ``scale``."""
        self.origin = origin
        self.scale = scale

    def point(self, x: float, y: float) -> tuple[float, float]:
        """One point, in canvas coordinates."""
        return (self.origin[0] + x * self.scale, self.origin[1] + y * self.scale)

    def rect(self, rect: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        """One ``(x, y, w, h)``, in canvas coordinates."""
        x, y, w, h = rect
        return (*self.point(x, y), w * self.scale, h * self.scale)


def _box(ax: Any, view: View, rect: tuple[float, float, float, float], **kwargs: Any) -> None:
    x, y, w, h = view.rect(rect)
    ax.add_patch(matplotlib.patches.Rectangle((x, y), w, h, **kwargs))


def _callout(
    ax: Any,
    text: str,
    xy: tuple[float, float],
    xytext: tuple[float, float],
    color: str = INK,
    weight: str = "normal",
    align: str = "left",
    va: str = "center",
    gid: str | None = None,
) -> None:
    annotation = ax.annotate(
        text, xy=xy, xytext=xytext, fontsize=9.5, color=color, weight=weight, ha=align, va=va,
        arrowprops={"arrowstyle": "-", "color": color, "lw": 0.8, "shrinkA": 3, "shrinkB": 3},
    )  # fmt: skip
    if gid:
        annotation.set_gid(gid)


def _dimension(
    ax: Any,
    start: tuple[float, float],
    end: tuple[float, float],
    text: str,
    color: str = BLUE,
    size: int = 8,
) -> None:
    """A double arrow with a label in the middle."""
    ax.annotate("", xy=end, xytext=start, arrowprops={"arrowstyle": "<->", "color": color, "lw": 0.8})
    mid = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
    ax.text(
        mid[0], mid[1], text, fontsize=size, color=color, ha="center", va="center",
        family="monospace", bbox={"fc": "white", "ec": "none", "pad": 1.0},
    )  # fmt: skip


def _draw_sheet(ax: Any, view: View) -> None:
    """The sheet: paper, text block, the figure on it, the caption, some body text."""
    _box(ax, view, (0.0, 0.0, *SHEET), fc="white", ec=GREY, lw=1.0, gid="sheet-paper")
    _box(
        ax, view,
        (MARGINS["left"], MARGINS["top"], SHEET[0] - MARGINS["left"] - MARGINS["right"],
         SHEET[1] - MARGINS["top"] - MARGINS["bottom"]),
        fc="none", ec=GREY, lw=0.7, ls=(0, (4, 3)), gid="sheet-text-block",
    )  # fmt: skip
    _box(ax, view, AREA, fc="#eff6ff", ec=BLUE, lw=1.2, gid="sheet-area")
    for name, rect in PANELS.items():
        _box(
            ax, view, (AREA[0] + rect[0], AREA[1] + rect[1], rect[2], rect[3]),
            fc="white", ec=BLUE, lw=0.5, gid=f"sheet-panel-{name.lower()}",
        )  # fmt: skip
        ax.text(
            *view.point(AREA[0] + rect[0] + 2, AREA[1] + rect[1] + 5.5), name.lower(),
            fontsize=6, weight="bold", color=BLUE,
        )  # fmt: skip
    _box(
        ax, view, (AREA[0], AREA[1] + AREA[3] + 3, AREA[2], CAPTION),
        fc="#f3f4f6", ec="none", gid="sheet-caption",
    )  # fmt: skip
    ax.text(
        *view.point(AREA[0] + 2, AREA[1] + AREA[3] + 3 + CAPTION / 2),
        "Figure 1 | Caption of the figure.", fontsize=6, color="#6b7280", va="center",
    )  # fmt: skip
    for y in range(int(AREA[1] + AREA[3] + CAPTION + 12), int(SHEET[1] - MARGINS["bottom"]), 5):
        ax.plot(
            [view.point(MARGINS["left"], y)[0], view.point(SHEET[0] - MARGINS["right"], y)[0]],
            [view.point(0, y)[1]] * 2, color="#e5e7eb", lw=1.8,
        )  # fmt: skip


def _draw_area(ax: Any, view: View) -> None:
    """The figure area magnified: panels, their letters, their axes, the guides."""
    _box(ax, view, (0.0, 0.0, 183.0, 120.0), fc="#eff6ff", ec=BLUE, lw=1.4, gid="area")
    for name, rect in PANELS.items():
        _box(ax, view, rect, fc="white", ec=BLUE, lw=1.0, gid=f"panel-{name.lower()}")
        ax.text(
            *view.point(rect[0] + 2.5, rect[1] + 7), name.lower(), fontsize=12, weight="bold",
            color=BLUE,
        )  # fmt: skip
        for axes_name, axes_rect in PANEL_AXES[name].items():
            _box(
                ax, view, axes_rect, fc="#fffbeb", ec=AMBER, lw=1.0, ls=(0, (3, 2)),
                gid=f"axes-{name.lower()}-{axes_name}",
            )  # fmt: skip
            ax.text(
                *view.point(axes_rect[0] + 2, axes_rect[1] + 5), axes_name, fontsize=8,
                color=AMBER, family="monospace",
            )  # fmt: skip
    guides = (((-5.0, GUIDE_Y), (188.0, GUIDE_Y)), ((GUIDE_X, -5.0), (GUIDE_X, 125.0)))
    for axis, (start, end) in zip("yx", guides, strict=True):
        first, second = view.point(*start), view.point(*end)
        line = ax.plot(
            [first[0], second[0]], [first[1], second[1]], color=SLATE, lw=1.0, ls=(0, (3, 2))
        )
        line[0].set_gid(f"guide-{axis}")


def _zoom_lines(ax: Any, sheet: View, zoom: View) -> None:
    """The two lines that say the right-hand drawing is the left one, magnified."""
    for corner in ((183.0, 0.0), (183.0, 120.0)):
        start = sheet.point(AREA[0] + corner[0], AREA[1] + corner[1])
        end = zoom.point(*corner)
        ax.plot([start[0], end[0]], [start[1], end[1]], color=GREY, lw=0.7, ls=(0, (2, 3)))


def _glossary_callouts(ax: Any, sheet: View, zoom: View, left: float, right: float) -> None:
    """Every term of docs/coordinates.md, pointing at what it names."""
    page = "page — the sheet the figure\nis printed on: paper size,\nmargins, room for a caption"
    margins = "margins — the text block.\nvalidate warns when the\nfigure is wider than it"
    area = "area — the figure itself,\nand the only thing the\nfigure file contains"
    caption = "caption — kept free under the\nfigure. It belongs to the\nmanuscript, not to the file"
    panel = "panel — one matplotlib figure,\nsaved as one file (panels/b.pdf),\ncarrying one letter"
    axes = (
        "axes — a plotting area inside\na panel. Named, and placed by\nthe layout, not by matplotlib"
    )
    guide = (
        "guide — one shared line. Axes\nin different panels that\nreference it line up once the"
        "\npanels are assembled"
    )
    gutter = (
        "gutter — the space between\npanels. optimize makes them\nequal, and gives the rest"
        "\nback to the panels"
    )
    _callout(ax, page, sheet.point(105, 1), (left, 24), INK, "bold", gid="callout-page")
    _callout(
        ax, margins, sheet.point(MARGINS["left"], SHEET[1] - MARGINS["bottom"]), (left, 250), SLATE,
        gid="callout-margins",
    )  # fmt: skip
    _callout(
        ax, area, sheet.point(AREA[0], AREA[1] + 30), (left, 128), BLUE, "bold", gid="callout-area"
    )
    _callout(
        ax, caption, sheet.point(AREA[0] + 40, AREA[1] + AREA[3] + 3 + CAPTION / 2), (left, 186),
        SLATE, gid="callout-caption",
    )  # fmt: skip
    _callout(ax, panel, zoom.point(183, 3), (right, 12), BLUE, "bold", "right", gid="callout-panel")
    _callout(
        ax, axes, zoom.point(174.5, 30), (right, 84), AMBER, "normal", "right", gid="callout-axes"
    )
    _callout(
        ax, guide, zoom.point(186, GUIDE_Y), (right, 150), SLATE, "normal", "right",
        gid="callout-guide",
    )  # fmt: skip
    _callout(
        ax, gutter, zoom.point(183, 64), (right, 224), SLATE, "normal", "right",
        gid="callout-gutter",
    )  # fmt: skip


def _glossary(target: Path) -> Path:
    """One picture of every word in docs/coordinates.md."""
    sheet, zoom = View((46.0, 0.0)), View(ZOOM_AT, ZOOM)
    fig, ax = plt.subplots(figsize=(15.5, 7.0))
    right_edge = ZOOM_AT[0] + 183 * ZOOM
    ax.set_xlim(-252, right_edge + 250)
    ax.set_ylim(SHEET[1] + 6, -30)  # y downwards, as in the layout
    ax.set_aspect("equal")
    ax.axis("off")
    _draw_sheet(ax, sheet)
    _zoom_lines(ax, sheet, zoom)
    _draw_area(ax, zoom)
    _glossary_callouts(ax, sheet, zoom, -246.0, right_edge + 248)

    origin = zoom.point(0, 0)
    ax.plot([origin[0]], [origin[1]], marker="+", color=BLUE, ms=12, mew=1.8)
    _callout(
        ax,
        "(0, 0) of every number in layout.yaml:\npanel boxes, axes rectangles, guides and"
        "\nmeasured geometry are millimetres from here",
        origin, (ZOOM_AT[0] - 6, -22), BLUE, "normal", "left", va="bottom", gid="callout-origin",
    )  # fmt: skip
    _dimension(ax, zoom.point(0, 126), zoom.point(183, 126), "area.width = 183 mm")
    _dimension(ax, zoom.point(-9, 0), zoom.point(-9, 120), "area.height", size=7)
    ax.text(-246.0, -28, "The levels of a figure", fontsize=15, weight="bold", color=INK, va="top")
    # svg.fonttype "none" keeps text as text rather than outlines, so the labels of the SVG can
    # be corrected in Inkscape (or any editor) instead of being a pile of paths.
    with plt.rc_context({"svg.fonttype": "none"}):
        fig.savefig(target, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return target


def _write_glossary(force: bool) -> None:
    """Draw the glossary, unless the SVG in the repository has been edited by hand since.

    The picture is a drawing, not a measurement: once it is right, it is worth correcting by
    hand in Inkscape (the text is text, and every box carries the name of what it stands for).
    Redrawing would throw those corrections away, so it happens only on request.
    """
    target = OUT / "glossary.svg"
    if target.exists() and not force:
        print(f"kept {target.relative_to(ROOT)} as it is (--force redraws it)")
        return
    _glossary(target)


def run(force: bool = False) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    _write_glossary(force)
    with tempfile.TemporaryDirectory() as tmp:
        demo = Path(tmp) / "demo"
        if main(["demo", "figure", "--dir", str(demo), "--build"]) != 0:
            raise SystemExit("demo build reported errors")

        figure = demo / "figures" / "figure_1"
        with pymupdf.open(demo / "legacy" / "manuscript.pdf") as doc:
            doc[0].get_pixmap(dpi=90).save(OUT / "step1-source-page.png")
        _thumbnail(figure / "detected.wireframe.png", OUT / "step2-draft-layout.png", 900)
        _thumbnail(figure / "wireframe.png", OUT / "step3-refined-layout.png", 900)
        _thumbnail(figure / "figure.png", OUT / "step4-final-figure.png", 1100)
        _thumbnail(figure / "page.png", OUT / "step4-final-page.png", 600)

        _pipeline(
            [
                ("1. Existing figure", "a PDF page (or screenshot)", OUT / "step1-source-page.png"),
                ("2. Draft layout", "plotplate from-pdf", OUT / "step2-draft-layout.png"),
                ("3. Refined layout", "layout.yaml (+guides)", OUT / "step3-refined-layout.png"),
                (
                    "4. Final figure",
                    "plotplate build / plotplate export",
                    OUT / "step4-final-page.png",
                ),
            ],
            OUT / "pipeline.png",
        )
    for image in sorted(OUT.glob("*.png")):
        print(f"wrote {image.relative_to(ROOT)}")


if __name__ == "__main__":
    run(force="--force" in sys.argv[1:])
