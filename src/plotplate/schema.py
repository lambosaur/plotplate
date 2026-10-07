"""What a layout file may contain, as one table.

Every key plotplate reads is listed here with the types it accepts. ``plotplate check`` walks
a layout against the table, so a key that is misspelled, indented one level too far or left
over from an older release is an error with a name attached -- not silence. Keys that moved
are listed too, which is how the file says where they went.

The table is the only place to add a key. Nothing reads a layout key that is not in it.
"""

from __future__ import annotations

import difflib
from typing import Any

from .config import default_style

NUMBER: tuple[type, ...] = (int, float)
TEXT: tuple[type, ...] = (str,)
BOOL: tuple[type, ...] = (bool,)
MAP: tuple[type, ...] = (dict,)
LIST: tuple[type, ...] = (list,)
ANY: tuple[type, ...] = (int, float, str, bool, list, dict)
EDGE = NUMBER + TEXT  # a number in mm, or a guide name with an optional offset

#: Top-level keys.
LAYOUT: dict[str, tuple[type, ...]] = {
    "schema": NUMBER,
    "name": TEXT,
    "journal": TEXT,
    "style": MAP,
    "style_files": LIST,
    "page": MAP,
    "area": MAP,
    "gutter": NUMBER + LIST,
    "code_dir": TEXT,
    "output_dir": TEXT,
    "labels": TEXT + BOOL,
    "guides": MAP,
    "page_guides": MAP,
    "mosaic": MAP,
    "panels": MAP,
    "constraints": MAP,
    "optimize": MAP,
    "notes": ANY,
}

#: Sections with a fixed set of keys, descended into one level.
SECTIONS: dict[str, dict[str, tuple[type, ...]]] = {
    "page": {
        "paper": TEXT + LIST,
        "margins": NUMBER + MAP,
        "caption": NUMBER,
        "outlines": BOOL,
        # The figure box lived here before `area:` existed, and took the same values.
        "width": NUMBER + TEXT,
        "height": NUMBER + TEXT,
    },
    "area": {"width": NUMBER + TEXT, "height": NUMBER + TEXT},
    "mosaic": {"rows": LIST, "widths": LIST, "heights": LIST, "gap": NUMBER + LIST},
    "optimize": {
        "max_stretch": NUMBER + TEXT,
        "max_shrink": NUMBER,
        "height": NUMBER + TEXT,
        "tolerance": NUMBER,
        "panels": MAP,
        "gap": NUMBER,
    },
    "guides": {"x": MAP, "y": MAP},
    "page_guides": {"x": LIST, "y": LIST},
}

#: Keys of one entry of ``panels:``.
PANEL: dict[str, tuple[type, ...]] = {
    "box": LIST,
    "axes": MAP,
    "label": MAP + BOOL,
    "margins": LIST,
    "source": TEXT,
}

#: Keys of one entry of ``panels.<name>.axes:``.
AXES: dict[str, tuple[type, ...]] = {
    "box": LIST,
    "left": EDGE,
    "top": EDGE,
    "right": EDGE,
    "bottom": EDGE,
    "ref": TEXT,
    "nrows": NUMBER,
    "ncols": NUMBER,
    "width_ratios": LIST,
    "height_ratios": LIST,
    "wgap": NUMBER,
    "hgap": NUMBER,
}

#: Keys of one entry of ``optimize.panels:``.
OPTIMIZE_PANEL: dict[str, tuple[type, ...]] = {
    "freeze": BOOL,
    "keep_aspect": BOOL,
    "stretch": NUMBER,
}

#: Keys of one entry of ``panels.<name>.label:``.
LABEL: dict[str, tuple[type, ...]] = {"text": TEXT, "offset": LIST}

#: Keys that moved, and what replaced them. Both are read, so old layouts keep working.
MOVED: dict[str, str] = {
    "mosaic.gap": "gutter",
    "optimize.gap": "gutter",
    "preview": "page",
    "preview.page": "page.paper",
    "preview.outlines": "page.outlines",
}

#: Values a key accepts beyond its type, where the set is small and closed.
CHOICES: dict[str, tuple[str, ...]] = {
    "labels": ("id", "auto", "none"),
    "area.height": ("solve", "auto"),
    "optimize.height": ("scale", "keep"),
    "optimize.max_stretch": ("auto",),
    "page.paper": ("a4", "letter", "none"),
}

Report = tuple[str, str, str]  # level, code, message


def _name(types: tuple[type, ...]) -> str:
    """The accepted types of a key, as the words a reader would use."""
    words = {int: "a number", float: "a number", str: "text", bool: "true or false"}
    words |= {list: "a list", dict: "a mapping"}
    seen = list(dict.fromkeys(words[t] for t in types if t in words))
    return " or ".join(seen) if seen else "anything"


def _unknown(path: str, key: str, allowed: dict[str, tuple[type, ...]]) -> Report:
    """One unknown key, with the closest legal name when there is one."""
    close = difflib.get_close_matches(key, allowed, n=1, cutoff=0.6)
    where = f"{path}.{key}" if path else key
    if close:
        return ("error", "unknown-key", f'{where}: unknown key; did you mean "{close[0]}"?')
    section = path or "a layout"
    return ("error", "unknown-key", f"{where}: unknown key; {section} takes {', '.join(allowed)}")


def _walk(raw: Any, allowed: dict[str, tuple[type, ...]], path: str, reports: list[Report]) -> None:
    """Check one mapping's keys and the type of each value."""
    if not isinstance(raw, dict):
        return
    for key, value in raw.items():
        key = str(key)
        where = f"{path}.{key}" if path else key
        if where in MOVED or (path and f"{path.split('.')[0]}.{key}") in MOVED:
            moved = MOVED.get(where) or MOVED[f"{path.split('.')[0]}.{key}"]
            reports.append(
                ("warning", "deprecated-key", f"{where}: renamed to {moved}; still read, for now")
            )
            continue
        if key not in allowed:
            reports.append(_unknown(path, key, allowed))
            continue
        types = allowed[key]
        if value is None:
            continue
        # bool is an int in Python; a key that wants a number must not take `true`.
        wrong = not isinstance(value, types) or (isinstance(value, bool) and bool not in types)
        if wrong:
            reports.append(
                ("error", "wrong-type", f"{where}: expected {_name(types)}, got {value!r}")
            )
            continue
        choices = CHOICES.get(where)
        if choices and isinstance(value, str) and value.lower() not in choices:
            reports.append(
                ("error", "bad-value", f"{where}: {value!r} is not one of {', '.join(choices)}")
            )


def issues(raw: dict[str, Any]) -> list[Report]:
    """Every key of ``raw`` that plotplate does not read, and every value of the wrong type."""
    reports: list[Report] = []
    _walk(raw, LAYOUT, "", reports)
    for section, allowed in SECTIONS.items():
        _walk(raw.get(section), allowed, section, reports)
    _walk(raw.get("style"), {k: ANY for k in default_style()}, "style", reports)
    for name, entry in (raw.get("panels") or {}).items():
        if not isinstance(entry, dict):
            continue
        _walk(entry, PANEL, f"panels.{name}", reports)
        _walk(entry.get("label"), LABEL, f"panels.{name}.label", reports)
        for ax_name, ax_raw in (entry.get("axes") or {}).items():
            if isinstance(ax_raw, dict):
                _walk(ax_raw, AXES, f"panels.{name}.axes.{ax_name}", reports)
    for name, entry in ((raw.get("optimize") or {}).get("panels") or {}).items():
        _walk(entry, OPTIMIZE_PANEL, f"optimize.panels.{name}", reports)
    return reports
