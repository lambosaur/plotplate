"""A local page that shows a figure with its layout drawn on top.

``plotplate view figures/figure_1`` serves one page on localhost. It shows

- the figure, composed from the panel files, on the sheet it is meant for (A4 by default),
  so the page, the text block, the figure area and the caption space are all visible;
- toggleable overlays: panel boxes, axes rectangles, guides, alignment rules and the
  measured geometry of the drawn panels;
- every layout variant of the figure (``layout.yaml``, ``layout.optimized.yaml``, ...): one
  is active and drawn in full, the others can be laid over it as outlines, which is how you
  see what an optimization did.

Files are re-read on every request, so a rebuild in another terminal shows up without
restarting anything. The page is read-only on purpose: boxes are edited in the layout file,
by ``plotplate optimize``, or through the Inkscape round trip (``plotplate svg-export`` /
``svg-import``). Only the Python standard library is used, so no server framework is
involved.
"""

from __future__ import annotations

import json
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .layout import Layout
from .variants import BASE, find_layouts

PAGE = """<!doctype html>
<meta charset="utf-8">
<title>plotplate: __TITLE__</title>
<style>
 :root { color-scheme: light dark; --line: #8884; }
 body { margin: 0; font: 13px/1.45 system-ui, sans-serif; display: flex; height: 100vh; }
 #side { width: 300px; padding: 14px 16px; overflow: auto; border-right: 1px solid var(--line); }
 #stage { flex: 1; overflow: auto; padding: 24px; display: grid; place-items: start center; }
 #paper { box-shadow: 0 1px 12px #0003; background: #fff; }
 h1 { font-size: 15px; margin: 0 0 2px; }
 h2 { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; opacity: .6;
      margin: 18px 0 6px; }
 label { display: block; padding: 2px 0; cursor: pointer; }
 ul { list-style: none; margin: 0; padding: 0; }
 li { padding: 2px 4px; border-radius: 4px; cursor: default; font-variant-numeric: tabular-nums; }
 li:hover { background: #3b82f633; }
 .mm { opacity: .6; }
 .swatch { display: inline-block; width: 8px; height: 8px; border-radius: 2px; margin-right: 4px; }
 .issue { padding: 4px 6px; border-radius: 4px; margin-bottom: 4px; }
 .error { background: #dc262622; } .warning { background: #d9770622; }
 .info { background: #8884; }
 #zoom { display: flex; gap: 4px; align-items: center; }
 button { font: inherit; padding: 1px 7px; }
 footer { margin-top: 18px; opacity: .6; font-size: 11px; }
</style>
<div id="side">
  <h1>__TITLE__</h1>
  <div class="mm" id="size"></div>
  <h2>Layouts</h2>
  <div id="variants"></div>
  <h2>Show</h2>
  <label><input type="checkbox" id="t-sheet" checked> the sheet (page, margins, caption)</label>
  <label><input type="checkbox" id="t-panels" checked> panel boxes</label>
  <label><input type="checkbox" id="t-axes" checked> axes rectangles</label>
  <label><input type="checkbox" id="t-guides" checked> guides</label>
  <label><input type="checkbox" id="t-rules"> alignment rules</label>
  <label><input type="checkbox" id="t-measured"> measured geometry</label>
  <label><input type="checkbox" id="t-figure" checked> the figure itself</label>
  <h2>Zoom</h2>
  <div id="zoom">
    <button id="z-out">-</button><button id="z-fit">fit</button>
    <button id="z-one">1:1</button><button id="z-in">+</button>
    <span class="mm" id="z-level"></span>
  </div>
  <h2>Panels</h2>
  <ul id="panels"></ul>
  <h2>Checks</h2>
  <div id="issues"></div>
  <footer>read-only: edit the layout, run plotplate optimize, or use svg-export / svg-import</footer>
</div>
<div id="stage"><svg id="paper" xmlns="http://www.w3.org/2000/svg"></svg></div>
<script>
const SV = "http://www.w3.org/2000/svg";
const COLORS = ["#7c3aed", "#0891b2", "#be185d", "#4d7c0f", "#b45309"];
let stamp = null, state = null, active = null, compare = new Set(), hover = null;
let ppm = null;  // pixels per millimetre; null = fit the stage
const el = id => document.getElementById(id);
const on = id => el(id).checked;

function node(parent, tag, attrs, text) {
  const made = document.createElementNS(SV, tag);
  for (const [k, v] of Object.entries(attrs)) made.setAttribute(k, v);
  if (text !== undefined) made.textContent = text;
  parent.appendChild(made);
  return made;
}

function box(parent, rect, attrs) {
  return node(parent, "rect", Object.assign(
    {x: rect[0], y: rect[1], width: rect[2], height: rect[3]}, attrs));
}

function drawSheet(svg, sheet) {
  box(svg, [0, 0, sheet.size[0], sheet.size[1]],
      {fill: "#fff", stroke: "#0003", "stroke-width": .3});
  box(svg, sheet.text, {fill: "none", stroke: "#0002", "stroke-width": .3,
                        "stroke-dasharray": "3 2"});
  const caption = sheet.caption ? sheet.caption : 0;
  if (caption) {
    box(svg, [sheet.area[0], sheet.area[1] + sheet.area[3], sheet.area[2], caption],
        {fill: "#8881"});
    node(svg, "text", {x: sheet.area[0] + 1, y: sheet.area[1] + sheet.area[3] + 4,
                       "font-size": 3, fill: "#666"}, "caption (" + caption + " mm)");
  }
  node(svg, "text", {x: sheet.margins.left, y: sheet.size[1] - sheet.margins.bottom / 2,
                     "font-size": 3.2, fill: "#666"},
       sheet.paper.toUpperCase() + " " + sheet.size[0] + " x " + sheet.size[1] + " mm"
       + (sheet.assumed ? " (assumed: no page: section in the layout)" : ""));
}

function drawLayout(layer, data) {
  if (on("t-guides")) {
    for (const x of Object.values(data.guides.x))
      node(layer, "line", {x1: x, y1: 0, x2: x, y2: data.height, stroke: "#888",
                           "stroke-width": .3, "stroke-dasharray": "2 2"});
    for (const y of Object.values(data.guides.y))
      node(layer, "line", {x1: 0, y1: y, x2: data.width, y2: y, stroke: "#888",
                           "stroke-width": .3, "stroke-dasharray": "2 2"});
  }
  for (const p of data.panels) {
    if (on("t-panels")) {
      box(layer, p.box, {fill: "#3b82f6", "fill-opacity": p.name === hover ? .22 : .07,
                         stroke: "#1d4ed8", "stroke-width": p.name === hover ? 1 : .4});
      if (p.label)
        node(layer, "text", {x: p.box[0] + 1.5, y: p.box[1] + 5, "font-size": 4,
                             fill: "#1d4ed8", "font-weight": "bold"}, p.label);
    }
    if (on("t-axes"))
      for (const a of p.axes)
        box(layer, a.box, {fill: "none", stroke: "#d97706", "stroke-width": .3,
                           "stroke-dasharray": "1.5 1.5"});
  }
  if (on("t-measured"))
    for (const f of data.features) {
      if (f.kind === "mark") node(layer, "circle", {cx: f.x, cy: f.y, r: .8, fill: "#16a34a"});
      else box(layer, [f.left, f.top, f.right - f.left, f.bottom - f.top],
               {fill: "none", stroke: "#16a34a", "stroke-width": .25});
    }
  if (on("t-rules"))
    for (const r of data.rules) {
      const vertical = r.axis === "x";
      node(layer, "line", {x1: vertical ? r.value : 0, y1: vertical ? 0 : r.value,
                           x2: vertical ? r.value : data.width,
                           y2: vertical ? data.height : r.value,
                           stroke: "#dc2626", "stroke-width": .35, "stroke-dasharray": "3 2"});
    }
}

function drawCompared(layer) {
  let i = 0;
  for (const variant of state.variants) {
    const color = COLORS[i++ % COLORS.length];
    if (variant.key === active || !compare.has(variant.key) || variant.error) continue;
    box(layer, [0, 0, variant.width, variant.height],
        {fill: "none", stroke: color, "stroke-width": .5, "stroke-dasharray": "4 2"});
    for (const [name, rect] of Object.entries(variant.boxes)) {
      box(layer, rect, {fill: "none", stroke: color, "stroke-width": .5});
      node(layer, "text", {x: rect[0] + rect[2] - 1, y: rect[1] + rect[3] - 1, "font-size": 3,
                           fill: color, "text-anchor": "end"}, name);
    }
  }
}

function draw() {
  const svg = el("paper");
  svg.replaceChildren();
  const sheet = on("t-sheet") ? state.sheet : null;
  const view = sheet ? sheet.size : [state.width, state.height];
  const origin = sheet ? [sheet.area[0], sheet.area[1]] : [0, 0];
  svg.setAttribute("viewBox", `0 0 ${view[0]} ${view[1]}`);
  const fit = Math.min(1, (el("stage").clientWidth - 56) / view[0] / 3.78);
  const scale = ppm === null ? fit : ppm / 3.78;
  svg.setAttribute("width", view[0] * 3.78 * scale);
  svg.setAttribute("height", view[1] * 3.78 * scale);
  el("z-level").textContent = Math.round(scale * 100) + "%";
  if (sheet) drawSheet(svg, sheet);
  const layer = node(svg, "g", {transform: `translate(${origin[0]} ${origin[1]})`});
  if (on("t-figure"))
    node(layer, "image", {href: `image/figure.png?layout=${active}&stamp=${state.stamp}`,
                          x: 0, y: 0, width: state.width, height: state.height,
                          preserveAspectRatio: "none"});
  box(layer, [0, 0, state.width, state.height],
      {fill: "none", stroke: "#1d4ed855", "stroke-width": .3});
  drawLayout(layer, state);
  drawCompared(layer);
}

function renderVariants() {
  const holder = el("variants");
  holder.replaceChildren();
  state.variants.forEach((variant, i) => {
    const row = document.createElement("label");
    const color = COLORS[i % COLORS.length];
    const shown = variant.key === active;
    const detail = variant.error
      ? "broken: " + variant.error
      : `${variant.file} · ${variant.width} x ${variant.height} mm`;
    row.innerHTML =
      `<input type="radio" name="active" value="${variant.key}" ${shown ? "checked" : ""}>` +
      (shown ? "" : `<input type="checkbox" data-compare="${variant.key}" ` +
                    `${compare.has(variant.key) ? "checked" : ""}>` +
                    `<span class="swatch" style="background:${color}"></span>`) +
      ` <b>${variant.key}</b> <span class="mm">${detail}</span>`;
    holder.appendChild(row);
  });
  for (const input of holder.querySelectorAll("input[name=active]"))
    input.addEventListener("change", () => { active = input.value; refresh(true); });
  for (const input of holder.querySelectorAll("input[data-compare]"))
    input.addEventListener("change", () => {
      const key = input.dataset.compare;
      input.checked ? compare.add(key) : compare.delete(key);
      draw();
    });
}

function showError(message) {
  el("size").textContent = "this layout cannot be read";
  el("panels").replaceChildren();
  el("paper").replaceChildren();
  const div = document.createElement("div");
  div.className = "issue error";
  div.textContent = message;
  el("issues").replaceChildren(div);
}

function render() {
  renderVariants();
  if (state.error) return showError(state.error);
  el("size").textContent = `${state.width} x ${state.height} mm`
    + (state.sheet ? ` on ${state.sheet.paper.toUpperCase()}` : "");
  el("panels").replaceChildren(...(state.panels || []).map(p => {
    const li = document.createElement("li");
    li.innerHTML = `<b>${p.label || p.name}</b> ${p.name !== p.label ? p.name : ""}`
      + `<span class="mm"> ${p.box.map(v => v.toFixed(1)).join(", ")}`
      + `${p.axes.length ? " · " + p.axes.map(a => a.name).join(", ") : ""}</span>`;
    li.addEventListener("mouseenter", () => { hover = p.name; draw(); });
    li.addEventListener("mouseleave", () => { hover = null; draw(); });
    return li;
  }));
  const issues = state.issues && state.issues.length
    ? state.issues : [{level: "info", text: "no issues"}];
  el("issues").replaceChildren(...issues.map(i => {
    const div = document.createElement("div");
    div.className = `issue ${i.level}`;
    div.textContent = i.text;
    return div;
  }));
  draw();
}

async function refresh(force) {
  try {
    const url = "state.json" + (active ? `?layout=${active}` : "");
    const fresh = await (await fetch(url)).json();
    if (force || fresh.stamp !== stamp) {
      stamp = fresh.stamp;
      state = fresh;
      active = fresh.active;
      render();
    }
  } catch (err) { /* the server went away; keep the last view */ }
}

async function poll() {  // one chain only: refresh() never schedules anything
  await refresh(false);
  setTimeout(poll, 1000);
}
for (const input of document.querySelectorAll("#side > label input"))
  input.addEventListener("change", () => state && draw());
el("z-in").onclick = () => { ppm = (ppm || 3.78) * 1.25; draw(); };
el("z-out").onclick = () => { ppm = (ppm || 3.78) / 1.25; draw(); };
el("z-one").onclick = () => { ppm = 3.78; draw(); };
el("z-fit").onclick = () => { ppm = null; draw(); };
window.addEventListener("resize", () => state && ppm === null && draw());
poll();
</script>
"""


@dataclass
class Viewer:
    """Reads the layouts and the panel files on demand, so a rebuild is picked up.

    Args:
        target: a layout file, or the figure folder holding ``layout.yaml``.
        paper: sheet to show when a layout declares no ``page:`` section.
    """

    target: Path
    paper: str | None = "a4"

    def variants(self) -> dict[str, Path]:
        """Every layout variant of this figure, keyed by variant name."""
        found = find_layouts(self.target)
        if not found:
            raise FileNotFoundError(f"{self.target}: no layout file found")
        return found

    def path(self, key: str | None = None) -> Path:
        """The file of one variant (the base one, or the only one, by default)."""
        found = self.variants()
        if key is None:
            return found.get(BASE) or next(iter(found.values()))
        if key not in found:
            raise KeyError(f"no layout variant {key!r}; have {list(found)}")
        return found[key]

    def layout(self, key: str | None = None) -> Layout:
        """One variant, re-read from disk."""
        return Layout.load(self.path(key))

    def stamp(self) -> str:
        """Changes whenever a layout, a panel or the alignment file changes."""
        folder = self.target if self.target.is_dir() else self.target.parent
        watched = [*self.variants().values(), folder / "alignment.yaml"]
        watched += sorted((folder / "panels").glob("*.pdf"))
        watched += sorted((folder / "panels").glob("*.json"))
        return str(sum(p.stat().st_mtime_ns for p in watched if p.exists()))

    def _summary(self, key: str, path: Path) -> dict[str, Any]:
        """One line per variant for the sidebar: its size and its boxes, or why it failed."""
        entry: dict[str, Any] = {"key": key, "file": path.name}
        try:
            layout = Layout.load(path)
        except Exception as exc:  # noqa: BLE001 - a broken variant must not hide the others
            return {**entry, "error": str(exc), "width": 0, "height": 0, "boxes": {}}
        return {
            **entry,
            "error": None,
            "width": layout.width,
            "height": layout.height,
            "boxes": {name: spec.box.to_list() for name, spec in layout.panels.items()},
        }

    def state(self, key: str | None = None) -> dict[str, Any]:
        """Everything the page draws: the sheet, the variants, and the active layout in full."""
        from .align import check_rules, read_features, rule_lines
        from .cli import _alignment_rules
        from .render import panel_status

        variants = self.variants()
        active = key if key in variants else BASE if BASE in variants else next(iter(variants))
        common = {
            "stamp": self.stamp(),
            "active": active,
            "variants": [self._summary(name, path) for name, path in variants.items()],
        }
        try:
            layout = self.layout(active)
        except Exception as exc:  # noqa: BLE001 - show the error on the page, keep serving
            return {**common, "name": self.target.name, "error": str(exc)}

        features, _ = read_features(layout)
        rules, tolerance = _alignment_rules(layout, None)
        issues = list(layout.validate())
        for info in panel_status(layout).values():
            issues.extend(info["issues"])
        issues.extend(check_rules(features, rules, tolerance))
        lines = rule_lines(features, rules)
        sheet = layout.sheet_geometry(self.paper)
        return {
            **common,
            "name": layout.name,
            "width": layout.width,
            "height": layout.height,
            "sheet": None
            if sheet is None
            else {
                "paper": sheet.paper,
                "size": list(sheet.size),
                "margins": sheet.margins,
                "text": sheet.text.to_list(),
                "area": sheet.area.to_list(),
                "caption": sheet.caption,
                "assumed": sheet.assumed,
            },
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

    def figure_png(self, key: str | None = None, dpi: int = 160) -> bytes:
        """The composed figure as PNG bytes, without writing any file."""
        from .render import compose

        doc = compose(self.layout(key), labels=True)
        data: bytes = doc[0].get_pixmap(dpi=dpi).tobytes("png")
        doc.close()
        return data


class _Handler(BaseHTTPRequestHandler):
    """Three routes: the page, its state, and the rendered figure."""

    viewer: Viewer

    def do_GET(self) -> None:
        """Serve the page, the state or the figure image."""
        parsed = urlparse(self.path)
        route = parsed.path.lstrip("/")
        query = parse_qs(parsed.query)
        key = query.get("layout", [None])[0]
        try:
            if route in ("", "index.html"):
                title = self.viewer.target.name
                self._send(PAGE.replace("__TITLE__", title).encode(), "text/html; charset=utf-8")
            elif route == "state.json":
                self._send(json.dumps(self.viewer.state(key)).encode(), "application/json")
            elif route == "image/figure.png":
                self._send(self.viewer.figure_png(key), "image/png")
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


def make_server(
    path: str | Path, host: str = "127.0.0.1", port: int = 8765, paper: str | None = "a4"
) -> ThreadingHTTPServer:
    """An HTTP server showing the figure at ``path`` (call ``serve_forever`` on it)."""

    class Handler(_Handler):
        viewer = Viewer(Path(path).resolve(), paper)

    return ThreadingHTTPServer((host, port), Handler)


def serve(
    path: str | Path,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    paper: str | None = "a4",
) -> None:
    """Serve the viewer until interrupted."""
    server = make_server(path, host, port, paper)
    url = f"http://{host}:{server.server_port}/"
    viewer: Viewer = server.RequestHandlerClass.viewer  # type: ignore[attr-defined]
    print(f"plotplate view on {url}  (Ctrl-C to stop)")
    print(f"  layouts: {', '.join(viewer.variants())}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
