"""``plotplate`` command line: layout conversion, previews, LaTeX, and checks."""

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
from .layout import Issue, Layout


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


def cmd_new(args: argparse.Namespace) -> int:
    out = Path(args.output)
    if out.exists() and not args.force:
        print(f"{out} exists (use --force)", file=sys.stderr)
        return 1
    rows = [r.strip() for r in args.mosaic.split("/")]
    data = {
        "schema": 1,
        "name": args.name or out.parent.name,
        "journal": args.journal,
        "page": {"width": _number_or_name(args.width), "height": args.height},
        "guides": {"x": {}, "y": {}},
        "mosaic": {"rows": rows, "gap": [args.gap, args.gap]},
        "panels": {},
    }
    dump_yaml(data, out)
    layout = Layout.load(out)
    print(f"wrote {_rel(out)}: {len(layout.panels)} panels on {layout.width} x {layout.height} mm")
    return _print_issues(layout.validate())


def _number_or_name(value: str) -> float | str:
    try:
        return float(value)
    except ValueError:
        return value


def cmd_validate(args: argparse.Namespace) -> int:
    layout = Layout.load(args.layout)
    print(f"{layout.name}: {layout.width} x {layout.height} mm, panels {list(layout.panels)}")
    return _print_issues(layout.validate())


def cmd_resolve(args: argparse.Namespace) -> int:
    """Print or write the layout with all boxes made explicit (mosaic/guides resolved)."""
    layout = Layout.load(args.layout)
    data = dict(layout.raw)
    data.pop("mosaic", None)
    data.pop("constraints", None)  # the solved boxes replace the rules
    key = "area" if "area" in data else "page"
    data[key] = {**(data.get(key) or {}), "height": layout.height}
    panels = {}
    for name, spec in layout.panels.items():
        entry = dict((layout.raw.get("panels") or {}).get(name) or {})
        entry["box"] = spec.box.to_list()
        entry.pop("margins", None)
        axes = {}
        for ax_name, ax in spec.axes.items():
            ax_raw = dict((entry.get("axes") or {}).get(ax_name) or {})
            for key in ("left", "top", "right", "bottom", "ref"):
                ax_raw.pop(key, None)
            ax_raw["box"] = ax.region.to_list()
            axes[ax_name] = ax_raw
        if axes:
            entry["axes"] = axes
        panels[name] = entry
    data["panels"] = panels
    dump_yaml(data, args.output or args.layout)
    print(f"wrote {_rel(args.output or args.layout)}")
    return 0


def cmd_svg_export(args: argparse.Namespace) -> int:
    from .svg import export_svg

    layout = Layout.load(args.layout)
    out = export_svg(
        layout, args.output or Path(args.layout).with_suffix(".svg"), background=args.background
    )
    print(
        f"wrote {_rel(out)} (edit rectangles in layers 'panels'/'axes', then `plotplate svg-import`)"
    )
    return 0


def cmd_svg_import(args: argparse.Namespace) -> int:
    from .svg import import_svg

    target = Path(args.output) if args.output else Path(args.svg).with_suffix(".yaml")
    base = load_yaml(target) if target.exists() else None
    data, issues = import_svg(args.svg, base)
    dump_yaml(data, target)
    print(f"wrote {_rel(target)}")
    status = _print_issues(issues)
    return max(status, _print_issues(Layout.load(target).validate()))


def cmd_detect(args: argparse.Namespace) -> int:
    from .detect import draft_layout

    data = draft_layout(
        args.image,
        args.width,
        name=args.name or Path(args.image).stem,
        min_gap_mm=args.min_gap,
        min_size_mm=args.min_size,
        attach_mm=args.attach,
        threshold=args.threshold,
    )
    out = Path(args.output)
    dump_yaml(data, out)
    print(f"wrote {_rel(out)}: {len(data['panels'])} segments")
    print("rename and merge them into panels, then run `plotplate tidy`")
    if args.wireframe:
        from .render import wireframe

        wireframe(Layout.load(out), args.wireframe, background=args.image)
        print(f"wrote {_rel(args.wireframe)}")
    return 0


def cmd_merge(args: argparse.Namespace) -> int:
    from .tidy import merge_panels

    data = merge_panels(load_yaml(args.layout), args.panels, args.name)
    out = args.output or args.layout
    dump_yaml(data, out)
    print(f"wrote {_rel(out)}: {'+'.join(args.panels)} -> {args.name}")
    return 0


def cmd_from_pdf(args: argparse.Namespace) -> int:
    from .pdfimport import layout_from_pdf, render_area
    from .tidy import fill_gaps, scale_layout, tidy

    result = layout_from_pdf(
        args.pdf,
        args.page,
        name=args.name,
        min_size_mm=args.min_size,
        use_letters=not args.no_letters,
        detect=args.detect,
        axes=args.axes,
        guides=args.guides,
    )
    data = result.data
    if args.journal:
        data["journal"] = args.journal
    if args.width is not None:
        width = _number_or_name(args.width)
        if isinstance(width, str):
            widths = (
                (load_journal(args.journal).get("page") or {}).get("widths") or {}
                if args.journal
                else {}
            )
            if width not in widths:
                print(f"--width {width!r}: not a number nor a width of --journal {args.journal}")
                return 1
            width = float(widths[width])
        data = scale_layout(data, width)
    if args.fill_gap is not None:
        data = tidy(fill_gaps(data, args.fill_gap), tolerance=args.tolerance, step=0.5)
    out = Path(args.output)
    dump_yaml(data, out)
    how = "placed graphics" if result.method == "placed" else "gutter detection"
    print(f"wrote {_rel(out)}: {len(data['panels'])} panels from {how}, {list(data['panels'])}")
    for item in result.placed:
        detail = f"scale {item.scale:.0%}" if item.scale is not None else f"{item.dpi:.0f} dpi"
        print(f"  {item.name:6s} {item.kind:5s} {item.box.to_list(1)} mm  {detail}")
    for note in result.notes:
        print(f"  note: {note}")
    if args.wireframe and result.area is not None:
        from .render import wireframe

        background = render_area(args.pdf, out.with_suffix(".source.png"), result.area, args.page)
        wireframe(Layout.load(out), args.wireframe, background=background)
        print(f"wrote {_rel(args.wireframe)} (boxes over {background.name})")
    return 0


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


def cmd_relabel(args: argparse.Namespace) -> int:
    layout = Layout.load(args.layout)
    data = dict(layout.raw)
    data["labels"] = "auto"
    panels = data.get("panels") or {}
    for name, spec in Layout(data, layout.path).panels.items():
        entry = panels.get(name) or {}
        if entry.get("label") is not False:
            entry["label"] = {"text": spec.label, "offset": list(spec.label_offset)}
        panels[name] = entry
    data["labels"] = "id"  # labels are explicit now
    dump_yaml(data, args.output or args.layout)
    letters = {name: (panels[name].get("label") or {}).get("text") for name in panels}
    print(f"wrote {_rel(args.output or args.layout)}: {letters}")
    return 0


def cmd_tidy(args: argparse.Namespace) -> int:
    from .tidy import fill_gaps, tidy

    data = load_yaml(args.layout)
    if args.fill_gap is not None:
        data = fill_gaps(data, args.fill_gap)
    data = tidy(data, tolerance=args.tolerance, step=args.step)
    out = args.output or args.layout
    dump_yaml(data, out)
    print(f"wrote {_rel(out)}")
    return _print_issues(Layout.load(out).validate())


def cmd_wireframe(args: argparse.Namespace) -> int:
    from .render import wireframe

    layout = Layout.load(args.layout)
    out = wireframe(
        layout, args.output or layout.base_dir / "wireframe.png", background=args.background
    )
    print(f"wrote {_rel(out)}")
    return 0


def cmd_preview(args: argparse.Namespace) -> int:
    from .render import page_view, preview

    layout = Layout.load(args.layout)
    rules = None
    if args.rules:
        from .align import read_features, rule_lines

        features, _ = read_features(layout)
        entries, _ = _alignment_rules(layout, args.constraints)
        rules = rule_lines(features, entries)
    paths = preview(
        layout, args.output_dir, labels=not args.no_labels, outlines=args.outlines, rules=rules
    )
    if args.page:
        page = page_view(layout, args.output_dir, args.page)
        paths.update({f"page-{key}": value for key, value in page.items()})
    print("wrote " + ", ".join(_rel(p) for p in paths.values()))
    return 0


def _demo_cases() -> dict[str, Any]:
    """Bundled demo cases: folder name -> package resource."""
    root = resources.files("plotplate") / "demo"
    return {
        entry.name: entry for entry in sorted(root.iterdir(), key=lambda e: e.name) if entry.is_dir()
    }


def _build_figure_demo(dest: Path, python: str) -> int:
    """Run the figure walkthrough: legacy PDF, tables, panels, export, page view."""
    import os
    import subprocess

    from .render import export_figure, page_view

    print("\n[1/4] draft a layout from the legacy PDF")
    status = main(
        [
            "from-pdf", str(dest / "legacy" / "manuscript.pdf"),
            "-o", str(dest / "legacy" / "draft" / "layout.yaml"),
            "--journal", "nature", "--width", "double", "--fill-gap", "4",
            "--wireframe", str(dest / "legacy" / "draft" / "wireframe.png"),
        ]
    )  # fmt: skip
    print("\n[2/4] write the demo tables")
    env = {**os.environ, "MPLBACKEND": "Agg"}
    subprocess.run([python, "make_data.py"], cwd=dest / "fig1", env=env, check=True)
    print("\n[3/4] draw the panels of the refined layout, then preview, LaTeX and checks")
    if main(["build", str(dest / "fig1" / "layout.yaml"), "--python", python]) != 0:
        print("\nthe build failed: see the messages above (a panel script error, or failed checks)")
        return 1
    main(["wireframe", str(dest / "fig1" / "layout.yaml")])
    print("\n[4/4] production file and page view")
    layout = Layout.load(dest / "fig1" / "layout.yaml")
    out, issues = export_figure(layout, dest / "fig1" / "export" / "Figure1.pdf")
    status = max(status, _print_issues(issues))
    page = page_view(layout, paper="a4")
    print(f"wrote {_rel(out)}, {_rel(page['png'])}")
    print("\nlook at, in order:")
    for path in (
        dest / "legacy" / "draft" / "wireframe.png",
        dest / "fig1" / "wireframe.png",
        dest / "fig1" / "preview.png",
        page["png"],
    ):
        print(f"  {_rel(path)}")
    return status


def _build_hard_layout_demo(dest: Path, python: str) -> int:
    """Generate the awkward-arrangement PDF and read it back."""
    import os
    import subprocess

    print("\n[1/3] build the PDF with awkward arrangements")
    env = {**os.environ, "MPLBACKEND": "Agg"}
    subprocess.run([python, "make.py"], cwd=dest, env=env, check=True)
    print("\n[2/3] read it back")
    status = main(
        [
            "from-pdf", str(dest / "hard.pdf"), "-o", str(dest / "layout.yaml"),
            "--axes", "--guides", "--wireframe", str(dest / "wireframe.png"),
        ]
    )  # fmt: skip
    print("\n[3/3] validate and preview (the overlaps are real: see the README)")
    main(["validate", str(dest / "layout.yaml")])
    main(["preview", str(dest / "layout.yaml")])
    return status


def cmd_demo(args: argparse.Namespace) -> int:
    cases = _demo_cases()
    if args.list or args.case is None:
        print("demo cases (plotplate demo <case> --dir <folder> --build):")
        for name, entry in cases.items():
            first = (entry / "README.md").read_text(encoding="utf-8").splitlines()
            summary = next((line for line in first[1:] if line.strip()), "")
            print(f"  {name:12s} {summary}")
        return 0
    if args.case not in cases:
        print(f"unknown case {args.case!r}; have {', '.join(cases)}", file=sys.stderr)
        return 1

    dest = Path(args.dir) if args.dir else Path(f"plotplate-demo-{args.case}")
    if dest.exists() and any(dest.iterdir()) and not args.force:
        print(f"{_rel(dest)} is not empty (use --force to overwrite demo files)", file=sys.stderr)
        return 1
    _copy_tree(cases[args.case], dest)
    print(f"copied the {args.case} demo to {_rel(dest)}; read {_rel(dest / 'README.md')}")
    if not args.build:
        print(f"next: plotplate demo {args.case} --dir {_rel(dest)} --build --force")
        return 0

    python = args.python or sys.executable
    needed = ("pandas", "pyarrow", "scipy", "seaborn") if args.case == "figure" else ("matplotlib",)
    missing = _missing_modules(python, needed)
    if missing:
        print(
            f"cannot build: {python} is missing {', '.join(missing)}.\n"
            "  run it from a project environment that has them (e.g. `pixi run plotplate ...`),\n"
            "  or add them to this installation (`pixi global add --environment plotplate ...`,\n"
            "  `pipx inject plotplate ...`), or pass --python /path/to/python",
            file=sys.stderr,
        )
        return 1
    if args.case == "figure":
        return _build_figure_demo(dest, python)
    return _build_hard_layout_demo(dest, python)


def _copy_tree(source: Any, target: Path) -> None:
    """Copy package data (a Traversable) without generated folders."""
    target.mkdir(parents=True, exist_ok=True)
    for entry in source.iterdir():
        if entry.name in {"__pycache__", "data", "panels", "export", "draft"}:
            continue
        if entry.is_dir():
            _copy_tree(entry, target / entry.name)
        else:
            (target / entry.name).write_bytes(entry.read_bytes())


def cmd_latex(args: argparse.Namespace) -> int:
    from .latex import write_figure_tex

    layout = Layout.load(args.layout)
    out = write_figure_tex(
        layout, args.output, graphics_prefix=args.prefix, labels=not args.no_labels
    )
    print(f"wrote {_rel(out)}")
    return 0


def cmd_bundle(args: argparse.Namespace) -> int:
    from .latex import bundle

    layout = Layout.load(args.layout)
    status = cmd_check(args)
    out = bundle(layout, args.output_dir, graphics_prefix=args.prefix)
    print(f"wrote {_rel(out.parent)} (upload its content to Overleaf)")
    return status


def cmd_export(args: argparse.Namespace) -> int:
    from .render import export_figure

    layout = Layout.load(args.layout)
    status = cmd_check(args)
    out, issues = export_figure(layout, args.output, dpi=args.dpi)
    print(f"wrote {_rel(out)}")
    return max(status, _print_issues(issues))


def cmd_palettes(args: argparse.Namespace) -> int:
    import yaml

    from .config import PRESETS

    palettes = yaml.safe_load((PRESETS / "palettes.yaml").read_text(encoding="utf-8"))
    for name, entry in palettes.items():
        print(f"{name:18s} {' '.join(entry['colors'])}\n{'':18s} {entry['description']}")
    return 0


def _alignment_rules(layout: Layout, path: str | None) -> tuple[list[dict[str, Any]], float]:
    candidate = Path(path) if path else layout.base_dir / "alignment.yaml"
    if not candidate.exists():
        return [], 0.3
    data = load_yaml(candidate)
    return list(data.get("rules") or []), float(data.get("tolerance", 0.3))


def cmd_align(args: argparse.Namespace) -> int:
    from .align import check_rules, near_misses, read_features

    layout = Layout.load(args.layout)
    features, issues = read_features(layout)
    rules, tolerance = _alignment_rules(layout, args.constraints)
    tolerance = args.tolerance if args.tolerance is not None else tolerance
    if rules:
        print(f"{len(rules)} rules, tolerance {tolerance} mm, {len(features)} features")
        issues += check_rules(features, rules, tolerance)
    else:
        print(f"no alignment.yaml: reporting features within {args.near} mm of each other")
        issues += near_misses(features, args.near)
    status = _print_issues(issues)
    print("OK" if status == 0 else "MISALIGNED")
    return status


_ANONYMOUS = re.compile(r"^ax\d+$")


def cmd_features(args: argparse.Namespace) -> int:
    """List every measurable feature of the saved panels, ready to paste into alignment.yaml."""
    from .align import read_features

    layout = Layout.load(args.layout)
    features, issues = read_features(layout)
    if not features:
        print("no geometry yet: draw the panels first (`plotplate build`)")
        return _print_issues(issues)
    width = max(len(ref) for ref in features)
    print(f"{'feature':{width}}  kind    coordinates (mm)")
    for ref, feature in sorted(features.items()):
        if feature.kind == "mark":
            detail = f"x {feature.values['x']:.2f}  y {feature.values['y']:.2f}"
        else:
            edges = "  ".join(
                f"{e} {feature.values[e]:.2f}" for e in ("left", "right", "top", "bottom")
            )
            spines = ",".join(feature.spines) or "no spines"
            detail = edges if feature.kind == "anchor" else f"{edges}   [{spines}]"
        print(f"{ref:{width}}  {feature.kind:6}  {detail}")

    anonymous = sorted(ref for ref, feature in features.items() if _ANONYMOUS.match(feature.name))
    if anonymous:
        issues.append(
            Issue(
                "error" if args.check else "warning",
                "unnamed-axes",
                f"{len(anonymous)} axes have no name ({', '.join(anonymous)}): add an axes entry "
                'in the layout, or ax.set_label("...") in the panel code',
            )
        )
    return _print_issues(issues)


def cmd_check(args: argparse.Namespace) -> int:
    from .render import panel_status

    layout = Layout.load(args.layout)
    issues = layout.validate()
    for info in panel_status(layout).values():
        issues.extend(info["issues"])
    print(f"{layout.name}: {len(layout.panels)} panels")
    status = _print_issues(issues)
    print("OK" if status == 0 else "ERRORS")
    return status


def panel_sources(layout: Layout, sources_dir: str | None = None) -> dict[str, Path]:
    """Script of each panel: ``panels.<name>.source``, or ``panel_<name>_*.py`` in a folder.

    Panel scripts are only needed by ``plotplate build``, which runs them for you. Every other
    command works from the saved panel files, so the code can live anywhere (a notebooks/
    folder, another repository) and be run however you like.
    """
    root = Path(sources_dir) if sources_dir else layout.base_dir
    sources: dict[str, Path] = {}
    for name in layout.panels:
        explicit = ((layout.raw.get("panels") or {}).get(name) or {}).get("source")
        if explicit:
            sources[name] = layout.base_dir / explicit
            continue
        matches = sorted(root.glob(f"panel_{name}_*.py")) + sorted(root.glob(f"panel_{name}.py"))
        if matches:
            sources[name] = matches[0]
    return sources


def cmd_build(args: argparse.Namespace) -> int:
    """Run panel scripts, then write preview, LaTeX snippet and check results."""
    import os
    import subprocess

    from .latex import write_figure_tex
    from .render import preview

    layout = Layout.load(args.layout)
    sources = panel_sources(layout, getattr(args, "sources", None))
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
            print(f"panel {name}: no script (panel_{name}_*.py or panels.{name}.source)")
            continue
        print(f"panel {name}: running {script.name}")
        result = subprocess.run([python, script.name], cwd=script.parent, env=env, check=False)
        if result.returncode != 0:
            failed.append(name)
    paths = preview(layout)
    tex = write_figure_tex(layout)
    print(f"wrote {paths['pdf'].name}, {paths['png'].name}, {paths['svg'].name}, {tex.name}")
    status = cmd_check(args)
    if failed:
        print(f"FAILED scripts: {failed}")
        return 1
    return status


def cmd_doctor(args: argparse.Namespace) -> int:
    """Report which plotplate runs the commands, which one the notebooks import, and the fonts."""
    import plotplate

    from .style import first_available_font

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
        print("       install one, then run `plotplate fonts --rebuild`")
    return 1 if problem is not None and problem.level == "error" else 0


def cmd_fonts(args: argparse.Namespace) -> int:
    from .style import first_available_font, rebuild_font_cache

    if args.rebuild:
        rebuild_font_cache()
        print("matplotlib font cache rebuilt")
    families = args.family or ["Arial", "Liberation Sans", "Helvetica"]
    for family in families:
        print(f"{family:20s} {'found' if first_available_font([family]) else 'MISSING'}")
    return 0


def cmd_skills(args: argparse.Namespace) -> int:
    source = resources.files("plotplate") / "skills"
    skills = sorted((entry for entry in source.iterdir() if entry.is_dir()), key=lambda e: e.name)
    if args.list:
        for entry in skills:
            text = (entry / "SKILL.md").read_text(encoding="utf-8")
            description = next(
                (line[len("description:") :].strip() for line in text.splitlines()
                 if line.startswith("description:")), ""
            )  # fmt: skip
            print(f"{entry.name}\n  {description}")
        return 0
    if args.print:
        for entry in skills:
            print(f"<!-- {entry.name} -->")
            print((entry / "SKILL.md").read_text(encoding="utf-8"))
        return 0
    dest = Path(args.dest)
    for entry in skills:
        target = dest / entry.name
        if target.exists() and not args.force:
            print(f"skip {_rel(target)} (exists; --force to overwrite)")
            continue
        target.mkdir(parents=True, exist_ok=True)
        for file in entry.iterdir():
            with resources.as_file(file) as real:
                shutil.copy2(real, target / file.name)
        print(f"installed {_rel(target)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="plotplate", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, func: object, help_text: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_text, description=help_text)
        p.set_defaults(func=func)
        return p

    add("journals", cmd_journals, "List bundled journal presets.")

    p = add("new", cmd_new, "Create a layout from a mosaic string, e.g. 'AAB/CDD'.")
    p.add_argument("output")
    p.add_argument(
        "--mosaic", required=True, help="rows separated by '/', one char per cell, '.' empty"
    )
    p.add_argument("--journal", default="generic-a4")
    p.add_argument("--width", default="full", help="mm or journal width name (single, double…)")
    p.add_argument("--height", type=float, required=True, help="mm")
    p.add_argument("--gap", type=float, default=4.0, help="mm between cells")
    p.add_argument("--name")
    p.add_argument("--force", action="store_true")

    p = add("validate", cmd_validate, "Check layout geometry.")
    p.add_argument("layout")

    p = add("resolve", cmd_resolve, "Make every box explicit (resolve constraints, mosaic, guides).")
    p.add_argument("layout")
    p.add_argument("-o", "--output")

    p = add("svg-export", cmd_svg_export, "Write an Inkscape SVG of the layout.")
    p.add_argument("layout")
    p.add_argument("-o", "--output")
    p.add_argument("--background", help="screenshot to trace over (locked layer)")

    p = add("svg-import", cmd_svg_import, "Update a layout YAML from rectangles drawn in Inkscape.")
    p.add_argument("svg")
    p.add_argument("-o", "--output", help="layout YAML to update/create (default: <svg>.yaml)")

    p = add("detect", cmd_detect, "Draft panel boxes from a figure screenshot (XY-cut).")
    p.add_argument("image")
    p.add_argument("--width", type=float, required=True, help="figure width in mm = image width")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--name")
    p.add_argument("--min-gap", type=float, default=1.5, help="mm")
    p.add_argument("--min-size", type=float, default=3.0, help="mm")
    p.add_argument("--attach", type=float, default=2.5, help="mm; small blocks closer merge in")
    p.add_argument("--threshold", type=float, default=0.9)
    p.add_argument("--wireframe", help="also write a wireframe PNG over the screenshot")

    p = add("from-pdf", cmd_from_pdf, "Draft a layout from a PDF page (placed graphics + labels).")
    p.add_argument("pdf")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--page", type=int, default=1, help="1-based page number")
    p.add_argument("--name")
    p.add_argument("--journal", help="journal preset to record in the layout")
    p.add_argument("--width", help="rescale the draft to this width: mm, or a --journal width name")
    p.add_argument("--min-size", type=float, default=5.0, help="mm; ignore smaller graphics")
    p.add_argument("--no-letters", action="store_true", help="do not name/group by panel letters")
    p.add_argument("--detect", action="store_true", help="force gutter detection (flattened PDFs)")
    p.add_argument(
        "--axes", action="store_true", help="also read plotting areas inside vector panels"
    )
    p.add_argument(
        "--guides",
        type=float,
        nargs="?",
        const=0.5,
        help="with --axes: name shared edges (mm tolerance, default 0.5)",
    )
    p.add_argument("--fill-gap", type=float, help="grow panel boxes to meet this many mm apart")
    p.add_argument("--tolerance", type=float, default=1.0, help="mm, edge alignment with --fill-gap")
    p.add_argument("--wireframe", help="write the boxes over the rendered figure area (PNG)")

    p = add("tidy", cmd_tidy, "Align nearly-equal edges and snap boxes to a step.")
    p.add_argument("layout")
    p.add_argument("-o", "--output")
    p.add_argument("--tolerance", type=float, default=1.0, help="mm")
    p.add_argument("--step", type=float, default=0.5, help="mm, 0 to disable")
    p.add_argument(
        "--fill-gap", type=float, help="first grow boxes to meet neighbours this many mm apart"
    )

    p = add("diff", cmd_diff, "Compare two layouts: what moved, merged, split, was added or removed.")
    p.add_argument("old")
    p.add_argument("new")
    p.add_argument("-o", "--output", help="write the revision plan (YAML)")
    p.add_argument("--wireframe", help="write a before/after wireframe (PNG)")
    p.add_argument(
        "--mapping", help="YAML with `mapping: {old: [new, ...]}` instead of matching by overlap"
    )

    p = add("relabel", cmd_relabel, "Write explicit panel letters, assigned in reading order.")
    p.add_argument("layout")
    p.add_argument("-o", "--output")

    p = add("merge", cmd_merge, "Merge panels (e.g. detected segments) into one, by box union.")
    p.add_argument("layout")
    p.add_argument("panels", nargs="+")
    p.add_argument("--as", dest="name", required=True, help="name of the merged panel")
    p.add_argument("-o", "--output")

    p = add("wireframe", cmd_wireframe, "Draw the layout boxes, optionally over a screenshot.")
    p.add_argument("layout")
    p.add_argument("-o", "--output")
    p.add_argument("--background")

    p = add("preview", cmd_preview, "Compose preview.pdf/png/svg from the saved panels.")
    p.add_argument("layout")
    p.add_argument("--output-dir")
    p.add_argument("--no-labels", action="store_true")
    p.add_argument("--outlines", action="store_true", help="outline every panel box")
    p.add_argument("--page", choices=["a4", "letter"], help="also write preview-page.* on this paper")
    p.add_argument("--rules", action="store_true", help="draw the alignment rules across the page")
    p.add_argument(
        "--constraints", help="alignment file (default: alignment.yaml next to the layout)"
    )

    p = add("latex", cmd_latex, "Write the LaTeX snippet placing the panels.")
    p.add_argument("layout")
    p.add_argument("-o", "--output")
    p.add_argument("--prefix", default="panels/", help="graphics path prefix in LaTeX")
    p.add_argument("--no-labels", action="store_true")

    p = add("features", cmd_features, "List the measurable features of the saved panels.")
    p.add_argument("layout")
    p.add_argument("--check", action="store_true", help="fail when axes have no name")

    p = add("align", cmd_align, "Check that panel features line up, using measured page coordinates.")
    p.add_argument("layout")
    p.add_argument(
        "--constraints", help="alignment file (default: alignment.yaml next to the layout)"
    )
    p.add_argument("--tolerance", type=float, help="mm; overrides the file's tolerance")
    p.add_argument(
        "--near", type=float, default=1.0, help="mm; without rules, report features this close"
    )

    p = add("check", cmd_check, "Check layout and saved panel files (sizes, reports).")
    p.add_argument("layout")

    p = add("bundle", cmd_bundle, "Collect .tex + panel PDFs into a folder for Overleaf upload.")
    p.add_argument("layout")
    p.add_argument("output_dir")
    p.add_argument("--prefix", help="panel path inside Overleaf (default figures/<name>/)")

    p = add("build", cmd_build, "Run panel scripts, then preview + LaTeX + check.")
    p.add_argument("layout")
    p.add_argument("panels", nargs="*", help="only these panels (default: all)")
    p.add_argument("--python", help="interpreter that runs the notebooks (default: this one)")
    p.add_argument("--sources", help="folder holding the panel scripts (default: next to the layout)")

    p = add("export", cmd_export, "Write the final single-file figure (.pdf, .tif, .png).")
    p.add_argument("layout")
    p.add_argument("-o", "--output", required=True, help="e.g. Figure1.pdf or Fig1.tif")
    p.add_argument("--dpi", type=int, help="raster formats; default: journal raster_dpi or style")

    p = add("palettes", cmd_palettes, "List bundled colour-blind-safe palettes.")

    p = add("demo", cmd_demo, "Copy a demo case into a folder (and optionally run it).")
    p.add_argument("case", nargs="?", help="demo case; omit to list them")
    p.add_argument("--dir", help="where to copy it (default: ./plotplate-demo-<case>)")
    p.add_argument("--build", action="store_true", help="also run every step of the case")
    p.add_argument("--python", help="interpreter that runs the notebooks (default: this one)")
    p.add_argument("--list", action="store_true", help="list the cases")
    p.add_argument("--force", action="store_true", help="write into a non-empty folder")

    p = add("doctor", cmd_doctor, "Report versions, environments and fonts; check they agree.")
    p.add_argument("--python", help="interpreter that runs the notebooks")

    p = add("fonts", cmd_fonts, "Report whether fonts are visible to matplotlib.")
    p.add_argument("family", nargs="*")
    p.add_argument("--rebuild", action="store_true", help="rescan system fonts first")

    p = add("skills", cmd_skills, "Install the bundled agent skills, or print them.")
    p.add_argument("--dest", default=".claude/skills", help="folder to copy the skills into")
    p.add_argument("--list", action="store_true", help="list the skills and what they do")
    p.add_argument("--print", action="store_true", help="print every skill (to paste into any agent)")
    p.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
