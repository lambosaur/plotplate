"""Several layouts for one figure, told apart by their file name.

A figure folder holds one layout per idea of how the figure should be arranged::

    figures/figure_1/
        layout.yaml             # the one you maintain
        layout.detected.yaml    # what `plotplate from-pdf` read from the old figure
        layout.optimized.yaml   # what `plotplate optimize` made of it
        panels/                 # the drawn panels, shared by all of them

The part between the dots is the *variant* name; ``layout.yaml`` itself is ``base``. Any
command that takes a layout also takes the folder, and then uses ``layout.yaml``;
``plotplate view`` finds every variant next to it and lets you switch between them.
"""

from __future__ import annotations

from pathlib import Path

BASE = "base"
SUFFIXES = (".yaml", ".yml")


def variant_of(path: str | Path) -> str:
    """The variant name of a layout file: ``layout.optimized.yaml`` -> ``optimized``."""
    stem = Path(path).name
    for suffix in SUFFIXES:
        stem = stem.removesuffix(suffix)
    parts = stem.split(".")
    return ".".join(parts[1:]) if len(parts) > 1 else BASE


def variant_path(path: str | Path, variant: str) -> Path:
    """The sibling file holding another variant of the same figure.

    ``variant_path("figures/f1/layout.detected.yaml", "optimized")`` gives
    ``figures/f1/layout.optimized.yaml``; the base name and suffix are kept.
    """
    path = Path(path)
    stem = path.name
    for suffix in SUFFIXES:
        stem = stem.removesuffix(suffix)
    base = stem.split(".")[0]
    name = base if variant == BASE else f"{base}.{variant}"
    return path.with_name(name + (path.suffix or ".yaml"))


def find_layouts(target: str | Path) -> dict[str, Path]:
    """Every layout variant of one figure, keyed by variant name and sorted base first.

    ``target`` is a layout file or the folder holding it. Only files whose name starts like
    the given one (``layout``, by default) count, so ``alignment.yaml`` or ``style.yaml``
    next to them are not mistaken for layouts.

    A ``layout.yaml`` that is a symlink to one of the variants beside it is not a layout of
    its own: it is the choice of which variant is in use (see :func:`selected`), so it is left
    out and the variant it points at is listed once, under its own name.
    """
    target = Path(target)
    folder = target if target.is_dir() else target.parent
    base = "layout" if target.is_dir() else Path(target.name).name.split(".")[0]
    found: dict[str, Path] = {}
    for entry in sorted(folder.iterdir()):
        if not entry.is_file() or entry.suffix not in SUFFIXES:
            continue
        if entry.name.split(".")[0] != base:
            continue
        if entry.is_symlink() and entry.resolve().parent == folder.resolve():
            continue  # a link to a sibling variant: the variant itself is listed below
        found[variant_of(entry)] = entry
    return dict(sorted(found.items(), key=lambda kv: (kv[0] != BASE, kv[0])))


def selected(target: str | Path) -> str | None:
    """The variant ``layout.yaml`` points at, when it is a symlink to one of its siblings.

    A figure folder can keep several layouts and choose between them with a link; this says
    which one is chosen, so a viewer can mark it instead of showing the link as a layout of its
    own. ``None`` when there is no link (``layout.yaml`` is then its own variant, ``base``).
    """
    target = Path(target)
    folder = target if target.is_dir() else target.parent
    base = "layout" if target.is_dir() else Path(target.name).name.split(".")[0]
    for suffix in SUFFIXES:
        link = folder / f"{base}{suffix}"
        if link.is_symlink():
            return variant_of(link.resolve())
    return BASE if any((folder / f"{base}{s}").exists() for s in SUFFIXES) else None


def resolve_layout_path(target: str | Path) -> Path:
    """The layout file to use when a command is given a path that may be a folder.

    A folder resolves to its ``layout.yaml`` -- a file, or a symlink to the variant the folder
    has selected -- or to the only variant in it when there is none. Anything else is returned
    unchanged, so an explicit file always wins.
    """
    path = Path(target)
    if not path.is_dir():
        return path
    for suffix in SUFFIXES:
        candidate = path / f"layout{suffix}"
        if candidate.exists():  # a layout of its own, or a link to the selected one
            return candidate
    found = find_layouts(path)
    if len(found) == 1:
        return next(iter(found.values()))
    if not found:
        raise FileNotFoundError(f"{path}: no layout.yaml (nor a layout.<variant>.yaml) in it")
    raise FileNotFoundError(
        f"{path}: no layout.yaml, and several variants ({', '.join(found)}); "
        "name the file, or link layout.yaml to the one to use"
    )
