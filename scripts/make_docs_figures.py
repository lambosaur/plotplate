"""Regenerate the images used in README.md and docs/ from a fresh demo build.

Run with `pixi run -e dev docs-figures`. Writes docs/images/*.png.
"""

import tempfile
from itertools import pairwise
from pathlib import Path

import matplotlib

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


def run() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        demo = Path(tmp) / "demo"
        if main(["demo", "figure", "--dir", str(demo), "--build"]) != 0:
            raise SystemExit("demo build reported errors")

        figure = demo / "figures" / "figure_1"
        with pymupdf.open(demo / "legacy" / "manuscript.pdf") as doc:
            doc[0].get_pixmap(dpi=90).save(OUT / "step1-source-page.png")
        _thumbnail(figure / "detected.wireframe.png", OUT / "step2-draft-layout.png", 900)
        _thumbnail(figure / "wireframe.png", OUT / "step3-refined-layout.png", 900)
        _thumbnail(figure / "preview.png", OUT / "step4-final-figure.png", 1100)
        _thumbnail(figure / "preview-page.png", OUT / "step4-final-page.png", 600)

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
    run()
