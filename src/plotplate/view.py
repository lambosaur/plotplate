"""A local page that shows a figure with its layout drawn on top.

``plotplate view layout.yaml`` serves one page on localhost: the composed figure, with
toggleable overlays for panel boxes, axes rectangles, guides, alignment rules and the
measured geometry of the drawn panels. It re-reads the files on every request, so a
rebuild in another terminal shows up without restarting anything.

It is read-only on purpose: boxes are edited in ``layout.yaml`` or through the Inkscape
round trip (``plotplate svg-export`` / ``svg-import``). Only the Python standard library is
used, so no server framework is involved.
"""

from __future__ import annotations

import json
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .layout import Layout

PAGE = """<!doctype html>
<meta charset="utf-8">
<title>plotplate: {name}</title>
<style>
 :root {{ color-scheme: light dark; --line: #8884; }}
 body {{ margin: 0; font: 13px/1.45 system-ui, sans-serif; display: flex; height: 100vh; }}
 #side {{ width: 290px; padding: 14px 16px; overflow: auto; border-right: 1px solid var(--line); }}
 #stage {{ flex: 1; overflow: auto; padding: 24px; display: grid; place-items: start center; }}
 #sheet {{ position: relative; box-shadow: 0 1px 12px #0003; background: #fff; }}
 #sheet img {{ display: block; width: 100%; }}
 #sheet svg {{ position: absolute; inset: 0; width: 100%; height: 100%; }}
 h1 {{ font-size: 15px; margin: 0 0 2px; }}
 h2 {{ font-size: 12px; text-transform: uppercase; letter-spacing: .06em; opacity: .6;
       margin: 18px 0 6px; }}
 label {{ display: block; padding: 2px 0; cursor: pointer; }}
 ul {{ list-style: none; margin: 0; padding: 0; }}
 li {{ padding: 2px 4px; border-radius: 4px; cursor: default; font-variant-numeric: tabular-nums; }}
 li:hover, li.on {{ background: #3b82f633; }}
 .mm {{ opacity: .6; }}
 .issue {{ padding: 4px 6px; border-radius: 4px; margin-bottom: 4px; }}
 .error {{ background: #dc262622; }} .warning {{ background: #d9770622; }}
 .info {{ background: #8884; }}
 footer {{ margin-top: 18px; opacity: .6; font-size: 11px; }}
</style>
<div id="side">
  <h1>{name}</h1>
  <div class="mm" id="size"></div>
  <h2>Show</h2>
  <label><input type="checkbox" id="t-panels" checked> panel boxes</label>
  <label><input type="checkbox" id="t-axes" checked> axes rectangles</label>
  <label><input type="checkbox" id="t-guides" checked> guides</label>
  <label><input type="checkbox" id="t-rules"> alignment rules</label>
  <label><input type="checkbox" id="t-measured"> measured geometry</label>
  <label><input type="checkbox" id="t-figure" checked> the figure itself</label>
  <h2>Panels</h2>
  <ul id="panels"></ul>
  <h2>Checks</h2>
  <div id="issues"></div>
  <footer>read-only: edit layout.yaml, or use svg-export / svg-import</footer>
</div>
<div id="stage"><div id="sheet"><img id="figure" alt="figure"><svg id="overlay"></svg></div></div>
<script>
const SV = "http://www.w3.org/2000/svg";
let stamp = null;
const el = id => document.getElementById(id);
const on = id => el(id).checked;

function draw(state) {{
  const svg = el("overlay");
  svg.setAttribute("viewBox", `0 0 ${{state.width}} ${{state.height}}`);
  svg.setAttribute("preserveAspectRatio", "none");
  svg.replaceChildren();
  el("figure").style.visibility = on("t-figure") ? "visible" : "hidden";
  const add = (tag, attrs) => {{
    const node = document.createElementNS(SV, tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    svg.appendChild(node);
    return node;
  }};
  if (on("t-guides")) {{
    for (const [, x] of Object.entries(state.guides.x))
      add("line", {{x1: x, y1: 0, x2: x, y2: state.height, stroke: "#888",
                    "stroke-width": .3, "stroke-dasharray": "2 2"}});
    for (const [, y] of Object.entries(state.guides.y))
      add("line", {{x1: 0, y1: y, x2: state.width, y2: y, stroke: "#888",
                    "stroke-width": .3, "stroke-dasharray": "2 2"}});
  }}
  for (const p of state.panels) {{
    if (on("t-panels")) {{
      add("rect", {{x: p.box[0], y: p.box[1], width: p.box[2], height: p.box[3],
                    fill: "#3b82f6", "fill-opacity": .07, stroke: "#1d4ed8",
                    "stroke-width": .4, "data-panel": p.name}});
      if (p.label) add("text", {{x: p.box[0] + 1.5, y: p.box[1] + 5, "font-size": 4,
                                 fill: "#1d4ed8", "font-weight": "bold"}}).textContent = p.label;
    }}
    if (on("t-axes")) for (const a of p.axes)
      add("rect", {{x: a.box[0], y: a.box[1], width: a.box[2], height: a.box[3], fill: "none",
                    stroke: "#d97706", "stroke-width": .3, "stroke-dasharray": "1.5 1.5"}});
  }}
  if (on("t-measured")) for (const f of state.features) {{
    if (f.kind === "mark") add("circle", {{cx: f.x, cy: f.y, r: .8, fill: "#16a34a"}});
    else add("rect", {{x: f.left, y: f.top, width: f.right - f.left, height: f.bottom - f.top,
                       fill: "none", stroke: "#16a34a", "stroke-width": .25}});
  }}
  if (on("t-rules")) for (const r of state.rules) {{
    const v = r.axis === "x";
    add("line", {{x1: v ? r.value : 0, y1: v ? 0 : r.value, x2: v ? r.value : state.width,
                  y2: v ? state.height : r.value, stroke: "#dc2626", "stroke-width": .35,
                  "stroke-dasharray": "3 2"}});
  }}
}}

function render(state) {{
  el("size").textContent = `${{state.width}} x ${{state.height}} mm` +
      (state.sheet ? ` on ${{state.sheet[0]}} x ${{state.sheet[1]}} mm` : "");
  el("figure").src = `image/figure.png?stamp=${{state.stamp}}`;
  el("panels").replaceChildren(...state.panels.map(p => {{
    const li = document.createElement("li");
    li.innerHTML = `<b>${{p.label || p.name}}</b> ${{p.name !== p.label ? p.name : ""}}` +
      `<span class="mm"> ${{p.box.map(v => v.toFixed(1)).join(", ")}}` +
      `${{p.axes.length ? " · " + p.axes.map(a => a.name).join(", ") : ""}}</span>`;
    return li;
  }}));
  el("issues").replaceChildren(...(state.issues.length ? state.issues : [{{level: "info",
      text: "no issues"}}]).map(i => {{
    const div = document.createElement("div");
    div.className = `issue ${{i.level}}`;
    div.textContent = i.text;
    return div;
  }}));
  draw(state);
}}

async function poll() {{
  try {{
    const state = await (await fetch("state.json")).json();
    if (state.stamp !== stamp) {{ stamp = state.stamp; window.state = state; render(state); }}
  }} catch (err) {{ /* the server went away; keep the last view */ }}
  setTimeout(poll, 1000);
}}
for (const box of document.querySelectorAll("input[type=checkbox]"))
  box.addEventListener("change", () => window.state && draw(window.state));
poll();
</script>
"""


@dataclass
class Viewer:
    """Reads the layout and its files on demand, so a rebuild is picked up."""

    path: Path

    def layout(self) -> Layout:
        """The layout, re-read from disk."""
        return Layout.load(self.path)

    def stamp(self) -> str:
        """Changes whenever the layout, a panel or the alignment file changes."""
        layout = self.layout()
        watched = [self.path, layout.base_dir / "alignment.yaml"]
        watched += sorted(layout.panels_dir.glob("*.pdf")) + sorted(layout.panels_dir.glob("*.json"))
        return str(sum(p.stat().st_mtime_ns for p in watched if p.exists()))

    def state(self) -> dict[str, Any]:
        """Everything the page draws: boxes, axes, guides, features, rules and checks."""
        from .align import check_rules, read_features, rule_lines
        from .cli import _alignment_rules
        from .render import panel_status

        layout = self.layout()
        features, _ = read_features(layout)
        rules, tolerance = _alignment_rules(layout, None)
        issues = list(layout.validate())
        for info in panel_status(layout).values():
            issues.extend(info["issues"])
        issues.extend(check_rules(features, rules, tolerance))
        lines = rule_lines(features, rules)
        return {
            "name": layout.name,
            "stamp": self.stamp(),
            "width": layout.width,
            "height": layout.height,
            "sheet": (layout.sheet_size() or (None, None))[:2],
            "guides": layout.guides,
            "panels": [
                {
                    "name": name,
                    "label": spec.label,
                    "box": spec.box.to_list(),
                    "axes": [
                        {"name": axes.name, "box": rect.to_list()}
                        for axes in spec.axes.values()
                        for rect in axes.rects()
                    ],
                }
                for name, spec in layout.panels.items()
            ],
            "features": [
                {"name": ref, "kind": feature.kind, **feature.values}
                for ref, feature in features.items()
            ],
            "rules": [
                {"axis": axis, "value": value} for axis, values in lines.items() for value in values
            ],
            "issues": [{"level": issue.level, "text": str(issue)} for issue in issues],
        }

    def figure_png(self, dpi: int = 160) -> bytes:
        """The composed figure as PNG bytes, without writing any file."""
        from .render import compose

        doc = compose(self.layout(), labels=True)
        data: bytes = doc[0].get_pixmap(dpi=dpi).tobytes("png")
        doc.close()
        return data


class _Handler(BaseHTTPRequestHandler):
    """Three routes: the page, its state, and the rendered figure."""

    viewer: Viewer

    def do_GET(self) -> None:
        """Serve the page, the state or the figure image."""
        route = self.path.split("?")[0].lstrip("/")
        try:
            if route in ("", "index.html"):
                body = PAGE.format(name=self.viewer.layout().name).encode()
                self._send(body, "text/html; charset=utf-8")
            elif route == "state.json":
                self._send(json.dumps(self.viewer.state()).encode(), "application/json")
            elif route == "image/figure.png":
                self._send(self.viewer.figure_png(), "image/png")
            else:
                self.send_error(404)
        except Exception as exc:  # noqa: BLE001 - a broken layout must not kill the server
            self._send(json.dumps({"error": str(exc)}).encode(), "application/json", 500)

    def _send(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: Any) -> None:
        """Keep the terminal for plotplate's own output."""


def make_server(path: str | Path, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    """An HTTP server showing the layout at ``path`` (call ``serve_forever`` on it)."""

    class Handler(_Handler):
        viewer = Viewer(Path(path).resolve())

    return ThreadingHTTPServer((host, port), Handler)


def serve(
    path: str | Path, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True
) -> None:
    """Serve the viewer until interrupted."""
    server = make_server(path, host, port)
    url = f"http://{host}:{server.server_port}/"
    print(f"plotplate view on {url}  (Ctrl-C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
