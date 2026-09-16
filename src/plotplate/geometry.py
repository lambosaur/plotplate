"""Units and rectangles.

All layout geometry is expressed in millimetres, in *page coordinates*: origin at the
top-left corner of the figure area, x to the right, y downwards (the same orientation
as Inkscape and as reading a printed page).
"""

from __future__ import annotations

from dataclasses import dataclass

MM_PER_INCH = 25.4
PT_PER_INCH = 72.0


def mm_to_in(value: float) -> float:
    """Convert millimetres to inches."""
    return value / MM_PER_INCH


def in_to_mm(value: float) -> float:
    """Convert inches to millimetres."""
    return value * MM_PER_INCH


def mm_to_pt(value: float) -> float:
    """Convert millimetres to PostScript points (1/72 inch)."""
    return value * PT_PER_INCH / MM_PER_INCH


def pt_to_mm(value: float) -> float:
    """Convert PostScript points (1/72 inch) to millimetres."""
    return value * MM_PER_INCH / PT_PER_INCH


@dataclass(frozen=True)
class Rect:
    """Axis-aligned rectangle in millimetres, top-left origin, y downwards."""

    x: float
    y: float
    w: float
    h: float

    def __post_init__(self) -> None:
        """Reject degenerate rectangles early, with a readable message."""
        if self.w <= 0 or self.h <= 0:
            raise ValueError(f"Rectangle must have positive width and height, got {self}")

    @classmethod
    def from_edges(cls, left: float, top: float, right: float, bottom: float) -> Rect:
        """Build a rectangle from its four edges."""
        return cls(left, top, right - left, bottom - top)

    @classmethod
    def from_list(cls, values: list[float] | tuple[float, ...]) -> Rect:
        """Build a rectangle from ``[x, y, w, h]``."""
        if len(values) != 4:
            raise ValueError(f"A box is [x, y, w, h] in mm, got {values!r}")
        return cls(*(float(v) for v in values))

    @property
    def left(self) -> float:
        """Left edge."""
        return self.x

    @property
    def top(self) -> float:
        """Top edge."""
        return self.y

    @property
    def right(self) -> float:
        """Right edge."""
        return self.x + self.w

    @property
    def bottom(self) -> float:
        """Bottom edge."""
        return self.y + self.h

    @property
    def size_in(self) -> tuple[float, float]:
        """Size in inches, as expected by matplotlib's ``figsize``."""
        return (mm_to_in(self.w), mm_to_in(self.h))

    def to_list(self, ndigits: int = 2) -> list[float]:
        """Return ``[x, y, w, h]`` rounded for serialization."""
        return [float(round(v, ndigits)) for v in (self.x, self.y, self.w, self.h)]

    def translated(self, dx: float, dy: float) -> Rect:
        """Return a copy moved by ``(dx, dy)``."""
        return Rect(self.x + dx, self.y + dy, self.w, self.h)

    def relative_to(self, container: Rect) -> Rect:
        """Express this rectangle in the coordinates of ``container``'s top-left corner."""
        return Rect(self.x - container.x, self.y - container.y, self.w, self.h)

    def to_figure_fraction(self, container: Rect) -> tuple[float, float, float, float]:
        """Return matplotlib ``[left, bottom, width, height]`` fractions inside ``container``.

        Matplotlib figure coordinates have their origin at the bottom-left, so the y
        axis is flipped here.
        """
        rel = self.relative_to(container)
        return (
            rel.x / container.w,
            1.0 - (rel.y + rel.h) / container.h,
            rel.w / container.w,
            rel.h / container.h,
        )

    def contains(self, other: Rect, tol: float = 1e-6) -> bool:
        """Whether ``other`` lies fully inside this rectangle (within ``tol`` mm)."""
        return (
            other.left >= self.left - tol
            and other.top >= self.top - tol
            and other.right <= self.right + tol
            and other.bottom <= self.bottom + tol
        )

    def intersection_area(self, other: Rect) -> float:
        """Area (mm²) shared by the two rectangles."""
        dx = min(self.right, other.right) - max(self.left, other.left)
        dy = min(self.bottom, other.bottom) - max(self.top, other.top)
        return dx * dy if dx > 0 and dy > 0 else 0.0
