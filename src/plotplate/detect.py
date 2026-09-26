"""Draft panel boxes from a screenshot of an assembled figure (recursive XY-cut).

The algorithm splits the image along blank horizontal/vertical gutters, largest gutter
first, until no gutter wider than ``min_gap_mm`` remains. It is deterministic, so an
agent (or a person) only has to *name and merge* the segments, instead of estimating
coordinates by eye. Over-segmentation is expected for composed panels (e.g. two plots
side by side inside one panel) and for panel letters; merge those afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
from matplotlib import image as mpimg

from .geometry import Rect


@dataclass(frozen=True)
class Segment:
    """A detected content block, in image pixels and page millimetres."""

    px: tuple[int, int, int, int]  # x0, y0, x1, y1 (exclusive)
    box: Rect


def _ink_mask(path: str | Path, threshold: float) -> np.ndarray:
    img = mpimg.imread(path)
    if img.dtype == np.uint8:
        img = img / 255.0
    if img.ndim == 3:
        if img.shape[2] == 4:  # composite transparency onto white
            alpha = img[..., 3:4]
            img = img[..., :3] * alpha + (1 - alpha)
        img = img[..., :3] @ np.array([0.299, 0.587, 0.114])
    return np.asarray(img < threshold)


def _gaps(profile: np.ndarray, min_gap: int) -> list[tuple[int, int]]:
    """Runs of empty positions, strictly inside the profile, at least ``min_gap`` long."""
    empty = profile == 0
    runs, start = [], None
    for i, is_empty in enumerate(empty):
        if is_empty and start is None:
            start = i
        elif not is_empty and start is not None:
            if start > 0 and i - start >= min_gap:
                runs.append((start, i))
            start = None
    return runs


def xy_cut(
    mask: np.ndarray, min_gap_px: int, min_size_px: int, attach_px: int = 0
) -> list[tuple[int, int, int, int]]:
    """Recursive XY-cut on a boolean ink mask; returns ``(x0, y0, x1, y1)`` blocks."""
    blocks: list[tuple[int, int, int, int]] = []

    def recurse(x0: int, y0: int, x1: int, y1: int) -> None:
        sub = mask[y0:y1, x0:x1]
        rows, cols = np.flatnonzero(sub.any(axis=1)), np.flatnonzero(sub.any(axis=0))
        if rows.size == 0:
            return
        x0, x1 = x0 + cols[0], x0 + cols[-1] + 1
        y0, y1 = y0 + rows[0], y0 + rows[-1] + 1
        sub = mask[y0:y1, x0:x1]
        row_gaps = _gaps(sub.sum(axis=1), min_gap_px)
        col_gaps = _gaps(sub.sum(axis=0), min_gap_px)
        best_row = max(row_gaps, key=lambda g: g[1] - g[0], default=None)
        best_col = max(col_gaps, key=lambda g: g[1] - g[0], default=None)
        if best_row is None and best_col is None:
            blocks.append((int(x0), int(y0), int(x1), int(y1)))
            return
        row_width = (best_row[1] - best_row[0]) if best_row else -1
        col_width = (best_col[1] - best_col[0]) if best_col else -1
        if row_width >= col_width:
            cuts = [y0 + (a + b) // 2 for a, b in row_gaps]
            edges = [y0, *cuts, y1]
            for top, bottom in pairwise(edges):
                recurse(x0, top, x1, bottom)
        else:
            cuts = [x0 + (a + b) // 2 for a, b in col_gaps]
            edges = [x0, *cuts, x1]
            for left, right in pairwise(edges):
                recurse(left, y0, right, y1)

    recurse(0, 0, mask.shape[1], mask.shape[0])
    return _absorb_small(blocks, min_size_px, attach_px)


def _distance(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    dx = max(b[0] - a[2], a[0] - b[2], 0)
    dy = max(b[1] - a[3], a[1] - b[3], 0)
    return float(np.hypot(dx, dy))


def _absorb_small(
    blocks: list[tuple[int, int, int, int]], min_size_px: int, attach_px: int
) -> list[tuple[int, int, int, int]]:
    """Merge small blocks (a detached row of tick labels) into the nearest large block.

    Small blocks farther than ``attach_px`` from any large block (typically panel
    letters) are dropped.
    """
    large = [b for b in blocks if b[2] - b[0] >= min_size_px and b[3] - b[1] >= min_size_px]
    small = [b for b in blocks if b not in large]
    for block in small:
        if not large:
            break
        index = min(range(len(large)), key=lambda i: _distance(block, large[i]))
        if _distance(block, large[index]) <= attach_px:
            target = large[index]
            large[index] = (
                min(target[0], block[0]),
                min(target[1], block[1]),
                max(target[2], block[2]),
                max(target[3], block[3]),
            )
    return large


def detect_segments(
    image: str | Path,
    page_width_mm: float,
    *,
    min_gap_mm: float = 1.5,
    min_size_mm: float = 3.0,
    attach_mm: float = 2.5,
    threshold: float = 0.9,
) -> tuple[list[Segment], tuple[float, float]]:
    """Detect content blocks in a figure screenshot.

    Args:
        image: PNG/JPEG cropped to the figure area (left edge = figure left edge).
        page_width_mm: physical width the image's full width corresponds to.
        min_gap_mm: blank gutters narrower than this do not split blocks.
        min_size_mm: blocks smaller than this in either direction are merged into the
            nearest larger block when within ``attach_mm``, else dropped (panel letters).
        attach_mm: distance under which small blocks are merged.
        threshold: luminance below which a pixel counts as ink (0-1).

    Returns:
        Segments sorted in reading order, and the page ``(width, height)`` in mm.
    """
    mask = _ink_mask(image, threshold)
    mm_per_px = page_width_mm / mask.shape[1]
    blocks = xy_cut(
        mask,
        max(1, round(min_gap_mm / mm_per_px)),
        max(1, round(min_size_mm / mm_per_px)),
        round(attach_mm / mm_per_px),
    )
    segments = [
        Segment(
            b,
            Rect(
                b[0] * mm_per_px,
                b[1] * mm_per_px,
                (b[2] - b[0]) * mm_per_px,
                (b[3] - b[1]) * mm_per_px,
            ),
        )
        for b in blocks
    ]
    segments.sort(key=lambda s: (round(s.box.y / 5), s.box.x))
    return segments, (page_width_mm, mask.shape[0] * mm_per_px)


def draft_layout(
    image: str | Path, page_width_mm: float, name: str = "figure", **kwargs: Any
) -> dict[str, Any]:
    """A layout mapping with one panel per detected segment (``S01``, ``S02``…)."""
    segments, (width, height) = detect_segments(image, page_width_mm, **kwargs)
    return {
        "schema": 1,
        "name": name,
        "area": {"width": round(width, 2), "height": round(height, 2)},
        "panels": {
            f"S{i + 1:02d}": {"box": seg.box.to_list(1), "label": False}
            for i, seg in enumerate(segments)
        },
    }
