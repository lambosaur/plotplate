"""``plotplate`` command line: layout conversion, previews, LaTeX, and checks."""

from __future__ import annotations

import argparse
import shutil
import sys
from importlib import resources
from pathlib import Path
from typing import Any

from .config import dump_yaml, list_journals, load_journal, load_yaml
from .layout import Issue, Layout


def _rel(path: str | Path) -> str:
    """Path relative to the working directory when it is inside it, else as given."""
    try:
        return str(Path(path).resolve().relative_to(Path.cwd()))
    except ValueError:
        return str(path)


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


def cmd_demo(args: argparse.Namespace) -> int:
    import importlib.util
    import os
    import subprocess

    from .render import export_figure, page_view

    dest = Path(args.dest)
    if dest.exists() and any(dest.iterdir()) and not args.force:
        print(f"{dest} is not empty (use --force to overwrite demo files)", file=sys.stderr)
        return 1
    _copy_tree(resources.files("plotplate") / "demo", dest)
    print(f"copied the demo to {_rel(dest)}; read {_rel(dest / 'README.md')}")
    if not args.build:
        print(f"next: plotplate demo {dest} --build --force, or follow the README step by step")
        return 0

    needed = ("pandas", "pyarrow", "scipy", "seaborn")
    missing = [m for m in needed if importlib.util.find_spec(m) is None]
    if missing:
        print(
            f"cannot build: missing {', '.join(missing)} in the environment of plotplate.\n"
            "  pipx: pipx inject plotplate pandas pyarrow scipy seaborn\n"
            '  uv:   uv tool install "plotplate[demo] @ git+..." (reinstall)',
            file=sys.stderr,
        )
        return 1

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
    subprocess.run([sys.executable, "make_data.py"], cwd=dest / "fig1", env=env, check=True)
    print("\n[3/4] draw the panels of the refined layout, then preview, LaTeX and checks")
    if main(["build", str(dest / "fig1" / "layout.yaml")]) != 0:
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


def panel_sources(layout: Layout) -> dict[str, Path]:
    """Script of each panel: ``panels.<name>.source`` or the ``panel_<name>_*.py`` convention."""
    sources: dict[str, Path] = {}
    for name in layout.panels:
        explicit = ((layout.raw.get("panels") or {}).get(name) or {}).get("source")
        if explicit:
            sources[name] = layout.base_dir / explicit
            continue
        matches = sorted(layout.base_dir.glob(f"panel_{name}_*.py")) + sorted(
            layout.base_dir.glob(f"panel_{name}.py")
        )
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
    sources = panel_sources(layout)
    wanted = args.panels or list(layout.panels)
    env = {**os.environ, "MPLBACKEND": "Agg"}
    failed = []
    for name in wanted:
        script = sources.get(name)
        if script is None:
            print(f"panel {name}: no script (panel_{name}_*.py or panels.{name}.source)")
            continue
        print(f"panel {name}: running {script.name}")
        result = subprocess.run(
            [sys.executable, script.name], cwd=script.parent, env=env, check=False
        )
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

    p = add("resolve", cmd_resolve, "Make every box explicit (resolve mosaic, guides, margins).")
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

    p = add("export", cmd_export, "Write the final single-file figure (.pdf, .tif, .png).")
    p.add_argument("layout")
    p.add_argument("-o", "--output", required=True, help="e.g. Figure1.pdf or Fig1.tif")
    p.add_argument("--dpi", type=int, help="raster formats; default: journal raster_dpi or style")

    p = add("palettes", cmd_palettes, "List bundled colour-blind-safe palettes.")

    p = add("demo", cmd_demo, "Copy the demo (legacy PDF, layout, panels, export) into a folder.")
    p.add_argument("dest")
    p.add_argument("--build", action="store_true", help="also run every step (needs the demo extra)")
    p.add_argument("--force", action="store_true", help="write into a non-empty folder")

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
