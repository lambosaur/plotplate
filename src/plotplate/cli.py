"""``plotplate`` command line: four commands for a figure, and a few for everything else."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from importlib import resources
from pathlib import Path
from typing import Any

from . import __version__
from .config import dump_yaml, list_journals, load_journal, load_yaml
from .layout import Issue, Layout, area_section, sheet_for
from .variants import find_layouts, resolve_layout_path, variant_path


def _rel(path: str | Path) -> str:
    """Path relative to the working directory when it is inside it, else as given."""
    try:
        return str(Path(path).resolve().relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def _probe(python: str) -> dict[str, Any]:
    """What a Python interpreter provides: its version, and the plotplate it imports."""
    import subprocess

    code = (
        "import json,sys;"
        "d={'python': sys.version.split()[0], 'executable': sys.executable};"
        "\ntry:\n import plotplate;"
        " d['plotplate']=plotplate.__version__; d['path']=plotplate.__file__\n"
        "except Exception as exc:\n d['plotplate']=None; d['error']=str(exc)\n"
        "print(json.dumps(d))"
    )
    try:
        out = subprocess.run(
            [python, "-c", code], capture_output=True, text=True, timeout=60, check=True
        )
        return dict(json.loads(out.stdout))
    except Exception as exc:  # noqa: BLE001 - report, never crash a build on probing
        return {"python": None, "executable": python, "plotplate": None, "error": str(exc)}


def _missing_modules(python: str, names: tuple[str, ...]) -> list[str]:
    """Which of ``names`` the given interpreter cannot import."""
    import importlib.util
    import subprocess

    if Path(python).resolve() == Path(sys.executable).resolve():
        return [name for name in names if importlib.util.find_spec(name) is None]
    code = (
        "import importlib.util,sys;"
        "print(' '.join(n for n in sys.argv[1:] if importlib.util.find_spec(n) is None))"
    )
    out = subprocess.run(
        [python, "-c", code, *names], capture_output=True, text=True, timeout=60, check=False
    )
    return out.stdout.split()


def _environment_issue(python: str) -> Issue | None:
    """Whether the interpreter that runs the notebooks agrees with this command.

    Missing library: an error, because the notebooks cannot run at all.
    Different version: a warning, because panels would be drawn by one version and checked
    by another.
    """
    if Path(python).resolve() == Path(sys.executable).resolve():
        return None
    info = _probe(python)
    if info.get("plotplate") is None:
        return Issue(
            "error",
            "environment",
            f"{python} cannot import plotplate ({info.get('error', 'unknown error')}); "
            "install the library in the environment that runs the notebooks",
        )
    if info["plotplate"] != __version__:
        return Issue(
            "warning",
            "environment",
            f"this command is plotplate {__version__}, but {python} imports "
            f"{info['plotplate']} ({info.get('path')}): panels would be drawn by one "
            "version and checked by another",
        )
    return None


def _print_issues(issues: list[Issue]) -> int:
    for issue in issues:
        print(f"  {issue}")
    return 1 if any(i.level == "error" for i in issues) else 0


def _journal_width(layout: Layout, name: str) -> float | None:
    """A named width from the layout's journal preset, or None after reporting the problem."""
    widths = ((layout.journal or {}).get("page") or {}).get("widths") or {}
    if name not in widths or widths[name] is None:
        print(
            f"--width {name!r}: not a number, and not a width of the layout's journal {widths}",
            file=sys.stderr,
        )
        return None
    return float(widths[name])


def cmd_journals(args: argparse.Namespace) -> int:
    for name in list_journals():
        preset = load_journal(name)
        page = preset.get("page") or {}
        font = (preset.get("style") or {}).get("font") or {}
        print(
            f"{name:18s} widths={page.get('widths')} max_height={page.get('max_height')} "
            f"font min={font.get('min')} max={font.get('max')}\n"
            f"{'':18s} verified: {preset.get('verified')}"
        )
    return 0


def _drafted_layout_path(args: argparse.Namespace, folder: Path, update: bool = False) -> Path | None:
    """Where a command that reads an existing figure writes its draft, or None when it refuses.

    Always ``layout.detected.yaml``, whatever was read -- a PDF, a screenshot, a drawing -- so
    there is one name to remember and ``plotplate view`` shows the draft beside the layout in
    use. ``-o`` overrides it, with a file or a folder. An existing draft is not replaced without
    ``--force``, except by ``svg-import``, which is *meant* to write back over the layout it
    read on the way out of a drawing program (``update``).
    """
    given = getattr(args, "output", None)
    target = Path(given) if given else folder / "layout.detected.yaml"
    if given and target.is_dir():
        target = target / "layout.detected.yaml"
    if target.exists() and not update and not getattr(args, "force", False):
        print(f"{_rel(target)} exists; use --force, or -o to name another file", file=sys.stderr)
        return None
    return target


def cmd_new(args: argparse.Namespace) -> int:
    out = Path(args.output)
    if out.is_dir():
        out = out / "layout.yaml"
    if out.exists() and not args.force:
        print(f"{_rel(out)} exists (use --force)", file=sys.stderr)
        return 1
    rows = [r.strip() for r in args.mosaic.split("/")]
    data: dict[str, Any] = {
        "schema": 1,
        "name": out.parent.name,
        "journal": args.journal,
    }
    data["page"] = sheet_for("a4")  # the sheet; `area` below is the figure itself
    data["area"] = {"width": _number_or_name(args.width), "height": args.height}
    data["gutter"] = 4
    data["guides"] = {"x": {}, "y": {}}
    data["mosaic"] = {"rows": rows}
    data["panels"] = {}
    dump_yaml(data, out)
    layout = Layout.load(out)
    # The journal width is a number now, so the margins can be made to fit it.
    data["page"] = sheet_for("a4", layout.width)
    dump_yaml(data, out)
    layout = Layout.load(out)
    print(f"wrote {_rel(out)}: {len(layout.panels)} panels on {layout.width} x {layout.height} mm")
    return _print_issues(layout.validate())


def _number_or_name(value: str) -> float | str:
    try:
        return float(value)
    except ValueError:
        return value


def _writable(args: argparse.Namespace, source: Path) -> Path | None:
    """Where a command that rewrites a layout writes: ``-o`` if given, else the file itself.

    The one file that is never written without being named is ``layout.yaml``: that is the
    layout a figure folder uses, and replacing it silently is how a morning's work disappears.
    Drafts (``layout.detected.yaml`` and friends) are rewritten in place, because that is what
    a draft is for.
    """
    if getattr(args, "output", None):
        return Path(args.output)
    if source.name in {"layout.yaml", "layout.yml"}:
        print(
            f"{_rel(source)} is the layout in use, and plotplate does not overwrite it. Name an "
            f"output:\n  -o {_rel(source.parent)}/layout.<name>.yaml\n  -o {_rel(source)}"
            "   # ... or say so explicitly",
            file=sys.stderr,
        )
        return None
    return source


def cmd_resolve(args: argparse.Namespace) -> int:
    """Print or write the layout with all boxes made explicit (mosaic/guides resolved)."""
    layout = Layout.load(args.layout)
    out = _writable(args, resolve_layout_path(args.layout))
    if out is None:
        return 1
    dump_yaml(layout.resolved(), out)
    print(f"wrote {_rel(out)}")
    return 0


PDF_SUFFIXES = {".pdf"}


def _detect_from_pdf(args: argparse.Namespace) -> tuple[dict[str, Any], Any] | None:
    """Read a figure out of a PDF page: placed graphics if there are any, gutters otherwise."""
    from .pdfimport import layout_from_pdf

    result = layout_from_pdf(
        args.input,
        args.page,
        name=Path(args.input).stem,
        use_letters=True,
        detect=False,
        axes=True,  # the axes rectangles are what the optimizer and `check` align against
        guides=0.5,  # ... and shared edges become named guides
        paper="a4",
    )
    data = result.data
    if args.journal:
        data["journal"] = args.journal
    if args.width is not None:
        scaled = _retarget_width(args, data, result.paper)
        if scaled is None:
            return None
        data = scaled
    return data, result


def _detect_from_image(args: argparse.Namespace) -> tuple[dict[str, Any], Any]:
    """Read a figure out of a raster image: blank gutters cut it into segments."""
    from .detect import draft_layout

    data = draft_layout(args.input, float(args.width), name=Path(args.input).stem)
    if args.journal:
        data["journal"] = args.journal
    return data, None


def cmd_detect(args: argparse.Namespace) -> int:
    """Draft a layout from an existing figure: a PDF page, or a raster image of one."""
    from .tidy import snap

    source = Path(args.input)
    if source.suffix.lower() in PDF_SUFFIXES:
        found = _detect_from_pdf(args)
        if found is None:
            return 1
        data, result = found
    else:
        if args.width is None:
            print("--width is required for an image: it is what sets the scale", file=sys.stderr)
            return 1
        if isinstance(_number_or_name(args.width), str):
            print(f"--width {args.width!r}: an image needs a number of millimetres", file=sys.stderr)
            return 1
        data, result = _detect_from_image(args)

    # A detector reports what it measured; the numbers a person then edits should be the few
    # the figure is really made of, so nearly-equal edges become one value here, always.
    data = snap(data, tolerance=1.0)
    out = _drafted_layout_path(args, source.parent)
    if out is None:
        return 1
    dump_yaml(data, out)
    how = "gutter detection" if result is None else (
        "placed graphics" if result.method == "placed" else "gutter detection"
    )  # fmt: skip
    print(f"wrote {_rel(out)}: {len(data['panels'])} panels from {how}, {list(data['panels'])}")
    if result is not None:
        for item in result.placed:
            detail = f"scale {item.scale:.0%}" if item.scale is not None else f"{item.dpi:.0f} dpi"
            print(f"  {item.name:6s} {item.kind:5s} {item.box.to_list(1)} mm  {detail}")
        for note in result.notes:
            print(f"  note: {note}")
    _detect_wireframe(args, out, source, result)
    # A draft is allowed to be a mess -- overlapping boxes are how a detector says "look here" --
    # so the problems are printed and the draft is still written. `plotplate check` is the gate.
    _print_issues(Layout.load(out).validate())
    print(f"next: look at the wireframe, then plotplate view {_rel(out.parent)}")
    return 0


def _detect_wireframe(args: argparse.Namespace, out: Path, source: Path, result: Any) -> None:
    """Draw the drafted boxes over the figure they were read from -- the one check that matters."""
    from .render import wireframe

    background: Path | str = source
    if result is not None and result.area is not None:
        from .pdfimport import render_area

        background = render_area(args.input, out.with_suffix(".source.png"), result.area, args.page)
    target = out.with_name(f"{out.stem}.wireframe.png")
    wireframe(Layout.load(out), target, background=background)
    print(f"wrote {_rel(target)}: the boxes over {Path(background).name}")


def cmd_merge(args: argparse.Namespace) -> int:
    from .tidy import merge_panels

    path = resolve_layout_path(args.layout)
    data = merge_panels(load_yaml(path), args.panels, args.name)
    out = _writable(args, path)
    if out is None:
        return 1
    dump_yaml(data, out)
    print(f"wrote {_rel(out)}: {'+'.join(args.panels)} -> {args.name}")
    return 0


def _retarget_width(
    args: argparse.Namespace, data: dict[str, Any], paper: str | None
) -> dict[str, Any] | None:
    """Scale a drafted layout to ``--width`` (millimetres or a journal width name)."""
    from .tidy import scale_layout

    width = _number_or_name(args.width)
    if isinstance(width, str):
        widths = (
            (load_journal(args.journal).get("page") or {}).get("widths") or {} if args.journal else {}
        )
        if width not in widths:
            print(f"--width {width!r}: not a number nor a width of --journal {args.journal}")
            return None
        width = float(widths[width])
    data = scale_layout(data, width)
    if data.get("page") and paper:  # margins follow the rescaled figure
        data["page"] = sheet_for(paper, float(area_section(data)["width"]))
    return data


def _optimize_target(args: argparse.Namespace, layout: Layout) -> Any:
    """The optimizer settings: everything from the layout, plus the width to aim for.

    How much a figure may be distorted, which panels must not move, how wide its gutters are:
    those belong to the figure, so they are read from its ``gutter:`` and ``optimize:`` keys,
    where they are versioned and where an agent can edit them. ``--width`` is the exception,
    because aiming a draft at a column width is a decision about this run.
    """
    from dataclasses import replace

    from .pack import Target

    target = Target.from_layout(layout)
    if args.width is None:
        return target
    value = _number_or_name(args.width)
    width = float(value) if not isinstance(value, str) else _journal_width(layout, value)
    if width is None:
        raise SystemExit(1)
    return replace(target, width=width)


def _optimize_report(report: Any, target: Any, source: str) -> None:
    """Print what the optimization did, for a person reading a terminal."""
    overlaps = f", {report.overlaps} overlapping pairs" if report.overlaps else ""
    before, after = report.gutters
    gutters = (
        f"{after[0]:.1f} mm everywhere"
        if abs(after[1] - after[0]) < 0.05
        else f"{after[0]:.1f}-{after[1]:.1f} mm"
    )
    chosen = " (chosen for you; --max-stretch sets it)" if report.automatic else ""
    print(f"{source}: {len(report.before)} panels{overlaps}")
    print(f"  gutters   {before[0]:.1f}-{before[1]:.1f} mm  ->  {gutters}")
    print(
        f"  panels    {report.occupancy[0]:.0%} of the figure  ->  {report.occupancy[1]:.0%}"
        f"  ({report.width:g} x {report.height:g} mm)"
    )
    print(f"  stretched up to {report.stretch:.2f}x{chosen}")
    print(f"  {'panel':6s} {'before (x, y, w, h)':28s} {'after':28s} factor")
    for name in report.after:
        fx, fy = report.factors(name)
        note = "  frozen" if name in target.freeze else ""
        print(
            f"  {name:6s} {report.before[name].to_list(1)!s:28s} "
            f"{report.after[name].to_list(1)!s:28s} {fx:.2f} x {fy:.2f}{note}"
        )
    for note in report.notes:
        print(f"  note: {note.message}")


def cmd_optimize(args: argparse.Namespace) -> int:
    """Re-spend the white space between panels, within a distortion limit."""
    from .pack import PackError, optimize

    layout = Layout.load(args.layout)
    if args.journal:  # aiming a draft at a journal is how most runs start
        layout.raw["journal"] = args.journal
        layout = Layout(layout.raw, layout.path)
    target = _optimize_target(args, layout)
    try:
        data, report = optimize(layout, target, tolerance=target.tolerance)
    except PackError as exc:
        print(f"cannot optimize {_rel(layout.file)}: {exc}", file=sys.stderr)
        return 1
    name = getattr(args, "variant", None) or "optimized"
    if "/" in name or "\\" in name:
        print(f"--as takes a variant name, not a path: {name}", file=sys.stderr)
        return 1
    out = Path(args.output) if args.output else variant_path(layout.file, name)

    if args.json:
        print(
            json.dumps(
                {
                    "source": _rel(layout.file),
                    "output": None if args.dry_run else _rel(out),
                    "width": report.width,
                    "height": report.height,
                    "stretch": report.stretch,
                    "stretch_chosen_automatically": report.automatic,
                    "gap": target.gap,
                    "occupancy": {"before": report.occupancy[0], "after": report.occupancy[1]},
                    "gutters": {"before": report.gutters[0], "after": report.gutters[1]},
                    "guides": {"before": report.guides[0], "after": report.guides[1]},
                    "overlaps_before": report.overlaps,
                    "panels": {
                        name: {
                            "before": report.before[name].to_list(),
                            "after": report.after[name].to_list(),
                            "factor": list(report.factors(name)),
                            "frozen": name in target.freeze,
                        }
                        for name in report.after
                    },
                    "notes": [note.as_dict() for note in report.notes],
                },
                indent=2,
            )
        )
    else:
        _optimize_report(report, target, _rel(layout.file))
    if args.dry_run:
        if not args.json:
            print("--dry-run: nothing written")
        return 0
    dump_yaml(data, out)
    if not args.json:
        print(f"wrote {_rel(out)}\nnext: plotplate view {_rel(out.parent)}")
    return _print_issues(Layout.load(out).validate())


def cmd_diff(args: argparse.Namespace) -> int:
    from .revise import diff_layouts, diff_wireframe, write_plan

    old, new = Layout.load(args.old), Layout.load(args.new)
    mapping = None
    if args.mapping:
        raw = load_yaml(args.mapping).get("mapping") or {}
        mapping = {k: ([v] if isinstance(v, str) else list(v)) for k, v in raw.items()}
    changes = diff_layouts(old, new, mapping)
    for change in changes:
        if change.change == "unchanged":
            continue
        arrow = f"{'+'.join(change.old) or '-'} -> {'+'.join(change.new) or '-'}"
        print(f"  {change.change:11s} {arrow}: {change.detail}")
        if change.sources:
            print(f"{'':14s}notebooks: {', '.join(change.sources)}")
    unchanged = [c.old[0] for c in changes if c.change == "unchanged"]
    print(f"  unchanged   {', '.join(unchanged) if unchanged else '(none)'}")
    if args.output:
        print(f"wrote {_rel(write_plan(changes, old, new, args.output))}")
    if args.wireframe:
        print(f"wrote {_rel(diff_wireframe(old, new, args.wireframe))}")
    return 0


def cmd_wireframe(args: argparse.Namespace) -> int:
    from .render import wireframe

    layout = Layout.load(args.layout)
    out = wireframe(layout, args.output or layout.output_dir / "wireframe.png")
    print(f"wrote {_rel(out)}")
    return 0


def _demo_cases() -> dict[str, Any]:
    """Bundled demo cases: folder name -> package resource."""
    root = resources.files("plotplate") / "demo"
    return {
        entry.name: entry for entry in sorted(root.iterdir(), key=lambda e: e.name) if entry.is_dir()
    }


def _build_figure_demo(dest: Path, python: str) -> int:
    """Run the walkthrough: read an old figure back, optimize it, draw the panels, export."""
    import os
    import subprocess

    from .render import export_figure

    figure = dest / "figures" / "figure_1"
    draft = figure / "layout.detected.yaml"
    print("\n[1/5] read the old figure back: legacy/manuscript.pdf -> layout.detected.yaml")
    status = main(
        [
            "detect", str(dest / "legacy" / "manuscript.pdf"),
            "-o", str(draft), "--journal", "nature", "--width", "double",
        ]
    )  # fmt: skip

    print("\n[2/5] say what the figure wants, in the file you would edit yourself")
    # These two numbers belong to the figure, not to a command line: the gutter it is drawn
    # with, and the height to aim for -- which also brings it under Nature's 170 mm limit.
    data = load_yaml(draft)
    data["gutter"] = 4
    data["optimize"] = {"height": 168}
    dump_yaml(data, draft)
    print(f"  {_rel(draft)}: gutter: 4, optimize: {{height: 168}}")
    print("      then spend its white space -> layout.optimized.yaml")
    status = max(status, main(["optimize", str(draft)]))

    print("\n[3/5] write the demo tables")
    env = {**os.environ, "MPLBACKEND": "Agg"}
    subprocess.run([python, "make_data.py"], cwd=figure, env=env, check=True)

    print("\n[4/5] draw the panels of the maintained layout, then the page, LaTeX and the checks")
    if main(["build", str(figure / "layout.yaml"), "--python", python]) != 0:
        print("\nthe build failed: see the messages above (a panel script error, or failed checks)")
        return 1
    main(["wireframe", str(figure / "layout.yaml")])

    print("\n[5/5] the production file")
    layout = Layout.load(figure / "layout.yaml")
    out, issues = export_figure(layout, layout.output_dir / "Figure1.pdf")
    status = max(status, _print_issues(issues))
    print(f"wrote {_rel(out)}")
    print("\nlook at, in order:")
    for path in (
        draft.with_name(f"{draft.stem}.wireframe.png"),
        layout.output_dir / "wireframe.png",
        layout.output_dir / "page.png",
    ):
        print(f"  {_rel(path)}")
    print("\nthen open all three layouts at once, and move the boxes yourself:")
    print(f"  plotplate view {_rel(figure)}")
    return status


_DEMO_BUILDERS = {"figure": _build_figure_demo}


def cmd_demo(args: argparse.Namespace) -> int:
    cases = _demo_cases()
    case = "figure"
    dest = Path(args.dir) if args.dir else Path(f"plotplate-demo-{case}")
    if dest.exists() and any(dest.iterdir()) and not args.force:
        print(f"{_rel(dest)} is not empty (use --force to overwrite demo files)", file=sys.stderr)
        return 1
    _copy_tree(cases[case], dest)
    print(f"copied the demo to {_rel(dest)}; read {_rel(dest / 'README.md')}")
    if not args.build:
        print(f"next: plotplate demo --dir {_rel(dest)} --build --force")
        return 0

    python = args.python or sys.executable
    builder = _DEMO_BUILDERS.get(case)
    if builder is None:
        print(f"the {case} case has no build steps; read {_rel(dest / 'README.md')}")
        return 0
    missing = _missing_modules(python, ("pandas", "pyarrow", "scipy", "seaborn"))
    if missing:
        print(
            f"cannot build: {python} is missing {', '.join(missing)}.\n"
            "  run it from a project environment that has them (e.g. `pixi run plotplate ...`),\n"
            "  or add them to this installation (`pixi global add --environment plotplate ...`,\n"
            "  `pipx inject plotplate ...`), or pass --python /path/to/python",
            file=sys.stderr,
        )
        return 1
    return builder(dest, python)


def _copy_tree(source: Any, target: Path) -> None:
    """Copy package data (a Traversable) without generated folders."""
    target.mkdir(parents=True, exist_ok=True)
    for entry in source.iterdir():
        if entry.name in {"__pycache__", "data", "output", "panels", "export", "draft"}:
            continue
        if entry.is_dir():
            _copy_tree(entry, target / entry.name)
        else:
            (target / entry.name).write_bytes(entry.read_bytes())


def cmd_latex(args: argparse.Namespace) -> int:
    from .latex import bundle

    """Fill a folder with what the manuscript needs: the panels and the .tex that places them."""
    layout = Layout.load(args.layout)
    status = cmd_check(args)
    # Everything a build produces lives under output_dir; the upload folder is one of those.
    destination = Path(args.output_dir) if args.output_dir else layout.output_dir / "overleaf"
    out = bundle(layout, destination, graphics_prefix=args.prefix)
    prefix = args.prefix if args.prefix is not None else f"figures/{layout.name}/"
    print(f"wrote {_rel(out.parent)}: upload its content to {prefix} in the Overleaf project")
    print("then, one line in the manuscript:\n")
    print(f"  \\input{{{prefix}{layout.name}-figure.tex}}\n")
    print(
        f"{layout.name}-figure.tex holds the figure environment, the caption and the label: it is a\n"
        f"copy of the one beside your layout, so the caption you wrote travels with it.\n"
        f"{layout.name}.tex holds the panels, and plotplate rewrites it on every build."
    )
    return status


def cmd_export(args: argparse.Namespace) -> int:
    from .render import export_figure

    layout = Layout.load(args.layout)
    status = cmd_check(args)
    try:
        out, issues = export_figure(layout, args.output, allow_missing=args.allow_missing)
    except ValueError as exc:  # missing or wrongly sized panels: the file would be wrong
        print(str(exc), file=sys.stderr)
        return 1
    print(f"wrote {_rel(out)}")
    return max(status, _print_issues(issues))


def _alignment_rules(layout: Layout, path: str | None) -> tuple[list[dict[str, Any]], float]:
    candidate = Path(path) if path else layout.base_dir / "alignment.yaml"
    if not candidate.exists():
        return [], 0.3
    data = load_yaml(candidate)
    return list(data.get("rules") or []), float(data.get("tolerance", 0.3))


_ANONYMOUS = re.compile(r"^ax\d+$")


def cmd_view(args: argparse.Namespace) -> int:
    from .view import serve

    found = find_layouts(args.layout)
    if not found:
        print(f"{_rel(args.layout)}: no layout.yaml (nor layout.<variant>.yaml)", file=sys.stderr)
        return 1
    serve(
        args.layout,
        port=args.port,
        open_browser=not args.no_browser,
        paper="a4",
        editable=True,  # the viewer is where a layout is edited; nothing is written until you save
    )
    return 0


def _alignment_issues(layout: Layout) -> list[Issue]:
    """Did the panels come out aligned? Compares what was measured with what was declared.

    Two sources, in this order. Every axes edge the layout declares at the same coordinate is a
    contract -- that is what a guide is for -- so the measured spines there must agree, with no
    file to write. An ``alignment.yaml`` beside the layout adds the cases no rectangle can
    express: a mark in data coordinates, a legend, a library's own axes.
    """
    from .align import check_rules, drift, read_features

    features, issues = read_features(layout)
    if not features:
        return issues
    rules, tolerance = _alignment_rules(layout, None)
    issues += drift(layout, features, tolerance)
    if rules:
        issues += check_rules(features, rules, tolerance)
    anonymous = sorted(ref for ref, feature in features.items() if _ANONYMOUS.match(feature.name))
    if anonymous:
        issues.append(
            Issue(
                "warning",
                "unnamed-axes",
                f"{len(anonymous)} axes have no name ({', '.join(anonymous)}): add an axes entry "
                'in the layout, or ax.set_label("...") in the panel code',
            )
        )
    return issues


def cmd_check(args: argparse.Namespace) -> int:
    """Everything that can be wrong with a figure, in one report."""
    from .render import panel_status

    layout = Layout.load(args.layout)
    issues = layout.validate()
    for info in panel_status(layout).values():
        issues.extend(info["issues"])
    issues += _alignment_issues(layout)
    print(f"{layout.name}: {len(layout.panels)} panels, {layout.width} x {layout.height} mm")
    status = _print_issues(issues)
    print("OK" if status == 0 else "ERRORS")
    return status


def panel_sources(layout: Layout, sources_dir: str | None = None) -> dict[str, Path]:
    """Script of each panel: ``panels.<name>.source``, or ``panel_<name>*.py`` in ``code_dir``.

    Panel scripts are only needed by ``plotplate build``, which runs them for you. Every other
    command works from the saved panel files, so the code can live where it suits (``code_dir:
    code``, a notebooks folder, another repository) and be run however you like. Jupytext
    percent-format ``.py`` files are ordinary scripts and run as they are.
    """
    root = Path(sources_dir) if sources_dir else layout.code_dir
    sources: dict[str, Path] = {}
    for name in layout.panels:
        explicit = ((layout.raw.get("panels") or {}).get(name) or {}).get("source")
        if explicit:
            sources[name] = layout.code_dir / explicit
            continue
        matches = sorted(root.glob(f"panel_{name}_*.py")) + sorted(root.glob(f"panel_{name}.py"))
        if matches:
            sources[name] = matches[0]
    return sources


def cmd_build(args: argparse.Namespace) -> int:
    """Draw the panels, put the figure on its page, write the LaTeX, check the result."""
    import os
    import subprocess

    from .latex import write_figure_scaffold, write_figure_tex
    from .render import page_view

    layout = Layout.load(args.layout)
    sources = panel_sources(layout)
    wanted = args.panels or list(layout.panels)
    python = getattr(args, "python", None) or sys.executable
    problem = _environment_issue(python)
    if problem is not None:
        print(f"  {problem}", flush=True)
        if problem.level == "error":
            return 1
    env = {**os.environ, "MPLBACKEND": "Agg"}
    failed = []
    for name in wanted:
        script = sources.get(name)
        if script is None:
            where = _rel(layout.code_dir)
            print(f"panel {name}: no script (panel_{name}*.py in {where}, or panels.{name}.source)")
            continue
        print(f"panel {name}: running {script.name}")
        result = subprocess.run([python, script.name], cwd=script.parent, env=env, check=False)
        if result.returncode != 0:
            failed.append(name)
    # One rendering to look at: the figure on its sheet. `plotplate export` writes the figure
    # itself, cropped, when the one file is what is wanted.
    paths: dict[str, Path] = {}
    if layout.sheet_geometry("a4") is None:
        print("page: none in the layout, so there is no page view; plotplate export writes a file")
    else:
        paths = page_view(layout, outlines=layout.page_outlines)
    tex = write_figure_tex(layout)
    scaffold = write_figure_scaffold(layout)  # once; a caption written there survives rebuilds
    print("wrote " + ", ".join(_rel(path) for path in [*paths.values(), tex]))
    print(f"  {_rel(scaffold)}: the figure environment and its caption, yours to edit")
    status = cmd_check(args)
    if failed:
        print(f"FAILED scripts: {failed}")
        return 1
    return status


def cmd_doctor(args: argparse.Namespace) -> int:
    """Report which plotplate runs the commands, which one the notebooks import, and the fonts."""
    import plotplate

    from .style import first_available_font, rebuild_font_cache

    if args.rebuild_fonts:
        rebuild_font_cache()
        print("matplotlib font cache rebuilt\n")

    print("command (this process)")
    print(f"  plotplate {__version__}")
    print(f"  library   {Path(plotplate.__file__).parent}")
    print(f"  python    {sys.version.split()[0]}  {sys.executable}")

    python = args.python or sys.executable
    if Path(python).resolve() != Path(sys.executable).resolve():
        info = _probe(python)
        print(f"\nnotebooks (--python {python})")
        print(f"  plotplate {info.get('plotplate') or 'NOT INSTALLED'}")
        print(f"  library   {info.get('path') or info.get('error', '')}")
        print(f"  python    {info.get('python')}  {info.get('executable')}")

    problem = _environment_issue(python)
    print(f"\n{problem if problem else 'versions agree'}")

    optional = ("pandas", "pyarrow", "scipy", "seaborn", "marsilea")
    missing = _missing_modules(python, optional)
    present = [name for name in optional if name not in missing]
    print(f"\noptional packages there: have {present or 'none'}")
    print(f"                         missing {missing or 'none'}")

    families = ["Arial", "Helvetica", "Liberation Sans"]
    found = [f for f in families if first_available_font([f])]
    print(f"fonts: {found or 'none of ' + str(families)}")
    if not found:
        print("       install one, then run `plotplate doctor --rebuild-fonts`")
    return 1 if problem is not None and problem.level == "error" else 0


def _skill_file(entry: Any, name: str) -> Path:
    """A path to this skill's SKILL.md that something else can actually open.

    The skills travel inside the package, so they are there after `pip install plotplate` and
    after `pip install git+...` alike. An installation that keeps the package zipped has no
    real path to give, and then the file is unpacked once into the user's cache, because a
    path printed for an agent to read has to outlive this command.
    """
    import os

    file = entry / "SKILL.md"
    path = Path(str(file))
    if path.is_file():
        return path
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    target = cache / "plotplate" / "skills" / name
    target.mkdir(parents=True, exist_ok=True)
    with resources.as_file(file) as real:
        shutil.copy2(real, target / "SKILL.md")
    return target / "SKILL.md"


def _skills() -> list[dict[str, Any]]:
    """The bundled skills: name, one-line description, and where the file is."""
    source = resources.files("plotplate") / "skills"
    found = []
    for entry in sorted((e for e in source.iterdir() if e.is_dir()), key=lambda e: e.name):
        text = (entry / "SKILL.md").read_text(encoding="utf-8")
        description = next(
            (line[len("description:") :].strip() for line in text.splitlines()
             if line.startswith("description:")), ""
        )  # fmt: skip
        found.append(
            {
                "name": entry.name,
                "description": description,
                "path": str(_skill_file(entry, entry.name)),
            }
        )
    return found


def _list_skills(skills: list[dict[str, Any]]) -> None:
    """What each skill is for, and the file to read it in."""
    for skill in skills:
        print(f"{skill['name']}\n  {skill['description']}\n  {skill['path']}")
    if skills:
        print(f"\nall of them are under {Path(skills[0]['path']).parent.parent}")
    print("point an agent at those files, or run `plotplate skills` to copy them into a project")


def cmd_skills(args: argparse.Namespace) -> int:
    skills = _skills()
    if args.list:
        _list_skills(skills)
        return 0
    source = resources.files("plotplate") / "skills"
    dest = Path(args.dest)
    for skill in skills:
        target = dest / skill["name"]
        if target.exists() and not args.force:
            print(f"skip {_rel(target)} (exists; --force to overwrite)")
            continue
        target.mkdir(parents=True, exist_ok=True)
        for file in (source / skill["name"]).iterdir():
            with resources.as_file(file) as real:
                shutil.copy2(real, target / file.name)
        print(f"installed {_rel(target)}")
    return 0


GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "the four you need",
        (
            ("detect", "draft a layout from a figure that exists: a PDF page, or an image"),
            ("optimize", "spend the white space between the panels"),
            ("view", "open the layout in a browser and move the boxes"),
            ("build", "draw the panels, put the figure on its page, check it"),
        ),
    ),
    (
        "at hand-off",
        (
            ("check", "everything that can be wrong with the figure, in one report"),
            ("export", "the figure as one file: .pdf, .png, .tif or .svg"),
            ("latex", "fill a folder to upload to Overleaf: the panels and their .tex"),
        ),
    ),
    (
        "when a layout needs surgery",
        (
            ("new", "start one from a mosaic string, e.g. 'AAB/CDD'"),
            ("merge", "make several detected segments into one panel"),
            ("resolve", "freeze solved boxes as plain numbers"),
            ("diff", "compare two layouts: what moved, merged, split, appeared"),
            ("wireframe", "draw the boxes as a PNG, before any panel exists"),
        ),
    ),
    (
        "your setup",
        (
            ("demo", "copy a worked example into a folder, and build it"),
            ("doctor", "which plotplate runs what, which fonts are there"),
            ("skills", "install the agent skills"),
            ("journals", "column widths and limits of the bundled presets"),
        ),
    ),
)


def _epilog() -> str:
    """The command list, grouped by when it is needed rather than alphabetically."""
    lines = []
    for title, commands in GROUPS:
        lines.append(f"\n{title}:")
        lines += [f"  {name:10s} {summary}" for name, summary in commands]
    lines.append("\n`plotplate <command> --help` for one command.")
    lines.append("A figure's own settings -- its width, its gutters, how far the optimizer")
    lines.append("may stretch a panel -- live in layout.yaml, not in these flags.")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    from . import __version__

    parser = argparse.ArgumentParser(
        prog="plotplate",
        description=__doc__,
        epilog=_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"plotplate {__version__}")
    # The subcommands are listed by `_epilog` in groups, so argparse does not list them again.
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")
    summaries = {name: summary for _, commands in GROUPS for name, summary in commands}

    def add(name: str, func: object) -> argparse.ArgumentParser:
        p = sub.add_parser(name, description=summaries[name].capitalize() + ".")
        p.set_defaults(func=func)
        return p

    # ----------------------------------------------------------- the four you need
    p = add("detect", cmd_detect)
    p.add_argument("input", help="a PDF page, or a PNG/JPG of a figure")
    p.add_argument("-o", "--output", help="layout file or folder (default: beside the input)")
    p.add_argument("--force", action="store_true", help="overwrite an existing draft")
    p.add_argument(
        "--width",
        help="the width to draft at: mm, or a journal width name; required for an image",
    )
    p.add_argument("--journal", help="journal preset to record (see `plotplate journals`)")
    p.add_argument("--page", type=int, default=1, help="which page of a PDF, 1-based")

    p = add("optimize", cmd_optimize)
    p.add_argument("layout", help="layout file, or the figure folder holding layout.yaml")
    p.add_argument("-o", "--output", help="default: layout.optimized.yaml next to the input")
    p.add_argument(
        "--as", dest="variant", help="write layout.<name>.yaml instead of layout.optimized.yaml"
    )
    p.add_argument("--width", help="target width: mm, or a journal width name (single, double…)")
    p.add_argument("--journal", help="aim at this journal's style and limits, and record it")
    p.add_argument("--dry-run", action="store_true", help="report, write nothing")
    p.add_argument("--json", action="store_true", help="report as JSON (for agents and scripts)")

    p = add("view", cmd_view)
    p.add_argument("layout", help="layout file, or the figure folder (every variant is offered)")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true", help="do not open a browser")

    p = add("build", cmd_build)
    p.add_argument("layout")
    p.add_argument("panels", nargs="*", help="only these panels (default: all)")
    p.add_argument("--python", help="interpreter that runs the panel scripts (default: this one)")

    # ----------------------------------------------------------- at hand-off
    p = add("check", cmd_check)
    p.add_argument("layout")

    p = add("export", cmd_export)
    p.add_argument("layout")
    p.add_argument("-o", "--output", required=True, help="e.g. Figure1.pdf, Fig1.tif, touch-up.svg")
    p.add_argument(
        "--allow-missing",
        action="store_true",
        help="draw missing panels as empty boxes instead of refusing: for a draft",
    )

    p = add("latex", cmd_latex)
    p.add_argument("layout")
    p.add_argument(
        "output_dir", nargs="?", help="folder to fill (default: <output_dir>/overleaf in the figure)"
    )
    p.add_argument("--prefix", help="panel path inside Overleaf (default figures/<name>/)")

    # ----------------------------------------------------------- layout surgery
    p = add("new", cmd_new)
    p.add_argument("output", help="layout file to write, or a folder (then layout.yaml in it)")
    p.add_argument(
        "--mosaic", required=True, help="rows separated by '/', one char per cell, '.' empty"
    )
    p.add_argument("--journal", default="generic-a4")
    p.add_argument("--width", default="full", help="mm or journal width name (single, double…)")
    p.add_argument("--height", type=float, required=True, help="mm")
    p.add_argument("--force", action="store_true")

    p = add("merge", cmd_merge)
    p.add_argument("layout")
    p.add_argument("panels", nargs="+")
    p.add_argument("--as", dest="name", required=True, help="name of the merged panel")
    p.add_argument("-o", "--output")

    p = add("resolve", cmd_resolve)
    p.add_argument("layout")
    p.add_argument("-o", "--output")

    p = add("diff", cmd_diff)
    p.add_argument("old")
    p.add_argument("new")
    p.add_argument("-o", "--output", help="write the revision plan (YAML)")
    p.add_argument("--wireframe", help="write a before/after wireframe (PNG)")
    p.add_argument(
        "--mapping", help="YAML file with `mapping: {old: new}`, when the boxes cannot say"
    )

    p = add("wireframe", cmd_wireframe)
    p.add_argument("layout")
    p.add_argument("-o", "--output")

    # ----------------------------------------------------------- your setup
    p = add("demo", cmd_demo)
    p.add_argument("--dir", help="where to copy it (default: ./plotplate-demo-figure)")
    p.add_argument("--build", action="store_true", help="also run every step")
    p.add_argument("--python", help="interpreter that runs the panel scripts (default: this one)")
    p.add_argument("--force", action="store_true", help="write into a non-empty folder")

    p = add("doctor", cmd_doctor)
    p.add_argument("--python", help="interpreter that runs the panel scripts")
    p.add_argument("--rebuild-fonts", action="store_true", help="rescan the system fonts first")

    p = add("skills", cmd_skills)
    p.add_argument("--dest", default=".claude/skills", help="folder to copy the skills into")
    p.add_argument("--list", action="store_true", help="list the skills, what they do, and where")
    p.add_argument("--force", action="store_true")

    add("journals", cmd_journals)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. A file plotplate cannot read is a message, not a traceback."""
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
