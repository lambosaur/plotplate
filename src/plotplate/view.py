"""A local page that shows a figure with its layout drawn on top.

``plotplate view figures/figure_1`` serves one page on localhost. It shows

- the figure, composed from the panel files, on the sheet it is meant for (A4 by default),
  so the page, the text block, the figure area and the caption space are all visible;
- toggleable overlays: panel boxes, axes rectangles, guides, alignment rules and the
  measured geometry of the drawn panels;
- every layout variant of the figure (``layout.yaml``, ``layout.optimized.yaml``, ...): one
  is active and drawn in full, the others can be laid over it as outlines, which is how you
  see what an optimization did.

With ``--edit``, panel boxes can also be dragged and resized on the page, and saved as
another variant (``layout.custom.yaml``). Two rules make that safe to offer:

- the server only ever writes ``layout.<name>.yaml`` next to the figure, and never
  ``layout.yaml`` itself -- the file you maintain keeps its comments, its ``mosaic:`` and its
  journal widths, none of which survive being written back as numbers;
- what is saved is a resolved layout, the same thing ``plotplate optimize`` writes, through
  the same function, so a box moved by hand and a box moved by the solver land identically.

Anything a drag cannot express -- adding a panel, drawing an annotation -- still belongs in
the layout file or in a drawing program (``plotplate svg-export`` / ``svg-import``).

Files are re-read on every request, so a rebuild in another terminal shows up without
restarting anything. Only the Python standard library is used, so no server framework is
involved.
"""

from __future__ import annotations

import json
import re
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .geometry import Rect
from .layout import Layout
from .variants import BASE, find_layouts, variant_path

#: What a variant may be called when the page saves one: a file name, not a path.
VARIANT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}")
#: What a panel added or renamed on the page may be called; it also becomes a file name.
PANEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}")

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
 #edit input[type=number] { width: 58px; font: inherit; }
 #edit .row { display: flex; gap: 6px; align-items: center; margin: 4px 0; }
 #name { width: 82px; font: inherit; }
 .dirty { color: #b45309; }
 #paper.editing { cursor: default; }
</style>
<div id="side">
  <h1>__TITLE__</h1>
  <div class="mm" id="size"></div>
  <h2>Layouts</h2>
  <div id="variants"></div>
  <h2>Show</h2>
  <label><input type="checkbox" id="t-sheet" checked> the sheet (page, margins, caption)</label>
  <label><input type="checkbox" id="t-panels" checked> panel boxes</label>
  <label><input type="checkbox" id="t-axes" checked> axes rectangles
    <span class="mm" id="n-axes"></span></label>
  <label><input type="checkbox" id="t-guides" checked> axis guides (in the layout)
    <span class="mm" id="n-guides"></span></label>
  <label><input type="checkbox" id="t-pguides" checked> page guides (across the sheet)
    <span class="mm" id="n-pguides"></span></label>
  <label><input type="checkbox" id="t-rules"> alignment rules (measured)
    <span class="mm" id="n-rules"></span></label>
  <label><input type="checkbox" id="t-measured"> measured geometry
    <span class="mm" id="n-measured"></span></label>
  <label><input type="checkbox" id="t-figure" checked> the figure itself</label>
  <h2>Zoom</h2>
  <div id="zoom">
    <button id="z-out">-</button><button id="z-fit">fit</button>
    <button id="z-one">1:1</button><button id="z-in">+</button>
    <span class="mm" id="z-level"></span>
  </div>
  <div id="edit" hidden>
    <h2>Edit</h2>
    <div class="mm" id="picked">drag a panel to move it, its corners to resize it</div>
    <div class="row">
      <label>x <input type="number" id="f-x" step="0.5"></label>
      <label>y <input type="number" id="f-y" step="0.5"></label>
    </div>
    <div class="row">
      <label>w <input type="number" id="f-w" step="0.5"></label>
      <label>h <input type="number" id="f-h" step="0.5"></label>
    </div>
    <div class="row">
      <label>name <input id="f-key" size="5"></label>
      <label>letter <input id="f-letter" size="3"></label>
      <label title="locked panels cannot be dragged, and arrange keeps their size">
        <input type="checkbox" id="f-lock"> locked</label>
    </div>
    <div class="row">
      <span class="mm">layout.</span><input id="name" value="custom"><span class="mm">.yaml</span>
    </div>
    <div class="row">
      <button id="guide-x" title="a vertical page guide">+ |</button>
      <button id="guide-y" title="a horizontal page guide">+ &ndash;</button>
      <button id="add" title="one more panel, where there is room">+ panel</button>
      <button id="arrange" title="even the gutters and spend the white space">arrange</button>
    </div>
    <div class="row">
      <button id="save">save</button><button id="revert">revert</button>
      <span class="mm" id="saved"></span>
    </div>
    <div class="mm" id="report"></div>
  </div>
  <h2>Panels</h2>
  <ul id="panels"></ul>
  <h2>Checks</h2>
  <div id="issues"></div>
  <footer id="foot">read-only: edit the layout, run plotplate optimize, or use svg-export /
    svg-import</footer>
</div>
<div id="stage"><svg id="paper" xmlns="http://www.w3.org/2000/svg"></svg></div>
<script>
const SV = "http://www.w3.org/2000/svg";
const COLORS = ["#7c3aed", "#0891b2", "#be185d", "#4d7c0f", "#b45309"];
let stamp = null, state = null, active = null, compare = new Set(), hover = null;
let ppm = null;  // pixels per millimetre; null = fit the stage
let draft = {}, picked = null, drag = null;  // editing: boxes moved but not saved yet
let rulers = null, pickedGuide = null, movedGuides = false;  // the page guides being edited
let locks = {}, letters = {}, renames = {}, extra = {};  // per panel, unsaved like the boxes
let originMM = [0, 0], viewMM = [210, 297];  // what draw() last put in the viewBox
// How close an edge has to come to stick: about five screen pixels, so it feels the same
// whether the figure is drawn at 30 % or at 200 %, and never less than three quarters of a mm.
const snapMM = () => Math.max(0.75, 5 * viewMM[0] / el("paper").getBoundingClientRect().width);
const el = id => document.getElementById(id);
const on = id => el(id).checked;
const editing = () => !!(state && state.editable && !state.error);
const dirty = () => movedGuides
  || [draft, locks, letters, renames, extra].some(held => Object.keys(held).length > 0);
const boxOf = p => draft[p.name] || p.box;
const lockedOf = p => (locks[p.name] === undefined ? !!p.locked : locks[p.name]);
// The panels of the active layout, plus the ones drawn on the page and not saved yet.
const panelsNow = () => (state.panels || []).concat(
  Object.entries(extra).map(([name, box]) => ({name, label: letters[name] || name, box, axes: []})));

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

function mapValue(v, old, now) {
  if (old[1] - old[0] < 1e-6) return now[0] + (v - old[0]);
  return now[0] + (v - old[0]) * (now[1] - now[0]) / (old[1] - old[0]);
}

// The JavaScript twin of plotplate.pack._map_axes: the margins that hold tick labels keep
// their millimetres, everything between them stretches. Only for drawing; the server writes
// the real numbers with the Python one.
function mapAxes(from, to, rects) {
  const band = i => {
    const lo = Math.min(...rects.map(r => r[i])), hi = Math.max(...rects.map(r => r[i] + r[i + 2]));
    const before = lo - from[i], after = from[i] + from[i + 2] - hi;
    let target = [to[i] + before, to[i] + to[i + 2] - after];
    if (target[1] - target[0] < 2)
      target = [mapValue(lo, [from[i], from[i] + from[i + 2]], [to[i], to[i] + to[i + 2]]),
                mapValue(hi, [from[i], from[i] + from[i + 2]], [to[i], to[i] + to[i + 2]])];
    return [[lo, hi], target];
  };
  if (!rects.length) return [];
  const bx = band(0), by = band(1);
  return rects.map(r => {
    const x0 = mapValue(r[0], bx[0], bx[1]), x1 = mapValue(r[0] + r[2], bx[0], bx[1]);
    const y0 = mapValue(r[1], by[0], by[1]), y1 = mapValue(r[1] + r[3], by[0], by[1]);
    return [x0, y0, x1 - x0, y1 - y0];
  });
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
  for (const p of (data === state ? panelsNow() : data.panels)) {
    const rect = boxOf(p);
    const lit = p.name === hover || p.name === picked;
    const locked = editing() && lockedOf(p);
    if (on("t-panels")) {
      box(layer, rect, {fill: locked ? "#64748b" : "#3b82f6", "fill-opacity": lit ? .22 : .07,
                        stroke: locked ? "#475569" : "#1d4ed8", "stroke-width": lit ? 1 : .4,
                        "stroke-dasharray": locked ? "2 1.5" : "none",
                        "data-panel": p.name});
      const letter = letters[p.name] !== undefined ? letters[p.name] : p.label;
      if (letter)
        node(layer, "text", {x: rect[0] + 1.5, y: rect[1] + 5, "font-size": 4,
                             fill: locked ? "#475569" : "#1d4ed8", "font-weight": "bold"}, letter);
    }
    if (on("t-axes")) {
      const rects = draft[p.name]
        ? mapAxes(p.box, rect, p.axes.map(a => a.box)) : p.axes.map(a => a.box);
      for (const a of rects)
        box(layer, a, {fill: "none", stroke: "#d97706", "stroke-width": .3,
                       "stroke-dasharray": "1.5 1.5"});
    }
  }
  const chosen = data === state && picked ? panelsNow().find(p => p.name === picked) : null;
  if (editing() && chosen && !lockedOf(chosen)) drawHandles(layer, boxOf(chosen));
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

function drawHandles(layer, rect) {
  const size = Math.max(1.6, 4 / (ppm === null ? 3 : ppm / 3.78) / 2);
  for (const [cx, cy] of corners(rect))
    box(layer, [cx - size / 2, cy - size / 2, size, size],
        {fill: "#fff", stroke: "#1d4ed8", "stroke-width": .35});
}

const corners = r => [[r[0], r[1]], [r[0] + r[2], r[1]], [r[0], r[1] + r[3]],
                      [r[0] + r[2], r[1] + r[3]]];

function atEvent(ev) {  // page pixels -> layout millimetres
  const r = el("paper").getBoundingClientRect();
  return [(ev.clientX - r.left) * viewMM[0] / r.width - originMM[0],
          (ev.clientY - r.top) * viewMM[1] / r.height - originMM[1]];
}

// What the pointer grabbed: a corner of the selected panel, or the smallest panel under it
// (so an inset wins over the panel it sits in).
function grab(at) {
  const near = 4 * viewMM[0] / el("paper").getBoundingClientRect().width;
  if (on("t-pguides") && rulers)
    for (const axis of ["x", "y"]) {
      const index = (rulers[axis] || []).findIndex(
        value => Math.abs(value - at[axis === "x" ? 0 : 1]) < near);
      if (index >= 0) return {mode: "guide", axis, index, at};
    }
  const chosen = panelsNow().find(p => p.name === picked && !lockedOf(p));
  if (chosen) {
    const rect = boxOf(chosen);
    const hit = corners(rect).findIndex(
      c => Math.abs(c[0] - at[0]) < near && Math.abs(c[1] - at[1]) < near);
    if (hit >= 0) return {name: picked, mode: "resize", corner: hit, rect, at};
  }
  const inside = panelsNow().filter(p => {
    const r = boxOf(p);
    return !lockedOf(p)
      && at[0] >= r[0] && at[0] <= r[0] + r[2] && at[1] >= r[1] && at[1] <= r[1] + r[3];
  }).sort((a, b) => boxOf(a)[2] * boxOf(a)[3] - boxOf(b)[2] * boxOf(b)[3]);
  if (!inside.length) return null;
  return {name: inside[0].name, mode: "move", rect: boxOf(inside[0]), at};
}

// Every edge a dragged edge may stick to: the figure, the guides, the other panels -- and,
// one gutter away from each of those panels, where a neighbour belongs. Without that second
// kind an edge can only ever land flush against another panel, which is the one arrangement a
// figure never wants.
function magnets() {
  const xs = [0, state.width], ys = [0, state.height];
  const gap = state.gap || 0;
  for (const p of panelsNow()) {
    if (p.name === (drag && drag.name)) continue;
    const r = boxOf(p);
    xs.push(r[0], r[0] + r[2], r[0] - gap, r[0] + r[2] + gap);
    ys.push(r[1], r[1] + r[3], r[1] - gap, r[1] + r[3] + gap);
  }
  const held = drag && drag.mode === "guide" ? drag : {};
  xs.push(...Object.values(state.guides.x),
          ...((rulers && rulers.x) || []).filter((_v, i) => held.axis !== "x" || held.index !== i));
  ys.push(...Object.values(state.guides.y),
          ...((rulers && rulers.y) || []).filter((_v, i) => held.axis !== "y" || held.index !== i));
  return [xs, ys];
}

// The nearest magnet within reach, or null when there is none: an edge that does not stick
// must not win over one that does, which is what deciding by "how far it moved" would do.
function snap(value, others, free) {
  if (free) return null;
  let best = null, gap = snapMM();
  for (const other of others)
    if (Math.abs(other - value) < gap) {
      gap = Math.abs(other - value);
      best = other;
    }
  return best === null ? null : {value: best, shift: best - value};
}

const nearest = candidates =>
  candidates.filter(Boolean).sort((a, b) => Math.abs(a.shift) - Math.abs(b.shift))[0]
  || {shift: 0};

const stuck = (value, others, free) => (snap(value, others, free) || {value}).value;

function moved(at, free) {
  const [xs, ys] = magnets();
  if (drag.mode === "guide") {  // a guide sticks to the panel edges, like a panel does to it
    const axis = drag.axis === "x" ? 0 : 1;
    return stuck(at[axis], drag.axis === "x" ? xs : ys, free);
  }
  const dx = at[0] - drag.at[0], dy = at[1] - drag.at[1];
  const r = drag.rect;
  if (drag.mode === "move") {
    const x = r[0] + dx, y = r[1] + dy;
    const sx = nearest([snap(x, xs, free), snap(x + r[2], xs, free)]);
    const sy = nearest([snap(y, ys, free), snap(y + r[3], ys, free)]);
    return [x + sx.shift, y + sy.shift, r[2], r[3]];
  }
  const right = drag.corner === 1 || drag.corner === 3, low = drag.corner >= 2;
  let x0 = r[0], y0 = r[1], x1 = r[0] + r[2], y1 = r[1] + r[3];
  if (right) x1 = stuck(x1 + dx, xs, free); else x0 = stuck(x0 + dx, xs, free);
  if (low) y1 = stuck(y1 + dy, ys, free); else y0 = stuck(y0 + dy, ys, free);
  return [Math.min(x0, x1 - 1), Math.min(y0, y1 - 1),
          Math.max(1, x1 - x0), Math.max(1, y1 - y0)];
}

const round2 = r => r.map(v => Math.round(v * 100) / 100);

function edit(name, rect) {
  if (extra[name]) extra[name] = round2(rect);
  else draft[name] = round2(rect);
  renderEdit();
  draw();
}

function editGuide(axis, index, value) {
  rulers[axis][index] = Math.round(value * 100) / 100;
  movedGuides = true;
  renderEdit();
  draw();
}

function addGuide(axis) {
  if (!rulers) rulers = {x: [], y: []};
  rulers[axis].push(Math.round((axis === "x" ? state.width : state.height) / 2 * 100) / 100);
  pickedGuide = {axis, index: rulers[axis].length - 1};
  picked = null;
  movedGuides = true;
  renderEdit();
  draw();
}

// A free-ish spot for one more panel: under everything drawn so far, or the middle.
function addPanel() {
  const taken = new Set(panelsNow().map(p => p.name));
  const letter = [..."ABCDEFGHIJKLMNOPQRSTUVWXYZ"].find(one => !taken.has(one))
    || "P" + (taken.size + 1);
  const gap = state.gap || 4;
  const bottom = panelsNow().reduce((low, p) => Math.max(low, boxOf(p)[1] + boxOf(p)[3]), 0);
  const top = bottom + gap < state.height - 20 ? bottom + gap : Math.round(state.height / 3);
  const rect = [0, Math.round(top * 100) / 100,
                Math.min(state.width, 60), Math.min(40, Math.max(20, state.height - top))];
  extra[letter] = rect;
  picked = letter;
  pickedGuide = null;
  renderEdit();
  render();
}

function dropGuide() {
  rulers[pickedGuide.axis].splice(pickedGuide.index, 1);
  pickedGuide = null;
  movedGuides = true;
  renderEdit();
  draw();
}

// Page guides run across the whole sheet, margins included, the way a guide dragged off a
// ruler does in a drawing program. The layer is translated to the figure, so the line simply
// starts before it and ends after it.
function drawPageGuides(layer) {
  const from = [-originMM[0], -originMM[1]], to = [viewMM[0] - originMM[0], viewMM[1] - originMM[1]];
  (rulers.x || []).forEach((value, index) => {
    const lit = pickedGuide && pickedGuide.axis === "x" && pickedGuide.index === index;
    node(layer, "line", {x1: value, y1: from[1], x2: value, y2: to[1], stroke: "#0ea5e9",
                         "stroke-width": lit ? .7 : .3, "data-guide": "x" + index});
  });
  (rulers.y || []).forEach((value, index) => {
    const lit = pickedGuide && pickedGuide.axis === "y" && pickedGuide.index === index;
    node(layer, "line", {x1: from[0], y1: value, x2: to[0], y2: value, stroke: "#0ea5e9",
                         "stroke-width": lit ? .7 : .3, "data-guide": "y" + index});
  });
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
  viewMM = view;
  originMM = origin;
  svg.classList.toggle("editing", editing());
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
  if (on("t-pguides") && rulers) drawPageGuides(layer);
  drawCompared(layer);
}

function renderEdit() {
  el("edit").hidden = !editing();
  if (!editing()) return;
  el("foot").textContent = "editing: drag, or nudge with the arrow keys; shift ignores the "
    + "magnets; a locked panel stays put; a guide dragged off the sheet is removed. Saving "
    + "writes layout.<name>.yaml, never layout.yaml";
  const panel = panelsNow().find(p => p.name === picked);
  const rect = panel ? boxOf(panel) : null;
  el("picked").innerHTML = panel
    ? `<b>${panel.label || panel.name}</b> ${draft[panel.name] ? "moved" : "unchanged"}`
    : pickedGuide
      ? `page guide ${pickedGuide.axis} at `
        + `<b>${rulers[pickedGuide.axis][pickedGuide.index]} mm</b> — delete removes it`
      : "drag a panel to move it, its corners to resize it";
  for (const [i, key] of ["f-x", "f-y", "f-w", "f-h"].entries()) {
    el(key).disabled = !rect || lockedOf(panel || {});
    el(key).value = rect ? rect[i] : "";
  }
  for (const key of ["f-key", "f-letter", "f-lock"]) el(key).disabled = !panel;
  el("f-key").value = panel ? (renames[panel.name] || panel.name) : "";
  el("f-letter").value = panel
    ? (letters[panel.name] !== undefined ? letters[panel.name] : (panel.label || "")) : "";
  el("f-lock").checked = panel ? lockedOf(panel) : false;
  const count = Object.keys(draft).length;
  el("saved").className = "mm" + (dirty() ? " dirty" : "");
  if (dirty())
    el("saved").textContent =
      (count ? `${count} panel${count > 1 ? "s" : ""} moved` : "guides changed") + ", not saved";
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
    input.addEventListener("change", () => {
      active = input.value;
      draft = {};
      locks = {}; letters = {}; renames = {}; extra = {};
      picked = null;
      pickedGuide = null;
      movedGuides = false;
      refresh(true);
    });
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

// A layer nothing has yet -- axes before any panel is drawn, rules before an alignment.yaml --
// says so and switches itself off, instead of leaving an empty box to wonder about.
function renderLayers() {
  const counts = {
    axes: (state.panels || []).reduce((total, p) => total + p.axes.length, 0),
    guides: Object.keys(state.guides.x).length + Object.keys(state.guides.y).length,
    pguides: ((rulers || {}).x || []).length + ((rulers || {}).y || []).length,
    rules: (state.rules || []).length,
    measured: (state.features || []).length,
  };
  for (const [key, count] of Object.entries(counts)) {
    el("n-" + key).textContent = count ? `(${count})` : "(none yet)";
    el("t-" + key).disabled = !count;
  }
}

function render() {
  renderVariants();
  renderEdit();
  if (state.error) return showError(state.error);
  renderLayers();
  el("size").textContent = `${state.width} x ${state.height} mm`
    + (state.sheet ? ` on ${state.sheet.paper.toUpperCase()}` : "");
  el("panels").replaceChildren(...panelsNow().map(p => {
    const li = document.createElement("li");
    const rect = boxOf(p);
    li.innerHTML = (editing()
        ? `<input type="checkbox" data-lock="${p.name}" title="locked"`
          + `${lockedOf(p) ? " checked" : ""}> ` : "")
      + `<b>${letters[p.name] !== undefined ? letters[p.name] : (p.label || p.name)}</b> `
      + `${p.name !== p.label ? (renames[p.name] || p.name) : ""}`
      + `<span class="mm"> ${rect.map(v => Number(v).toFixed(1)).join(", ")}`
      + `${p.axes.length ? " · " + p.axes.map(a => a.name).join(", ") : ""}</span>`;
    li.addEventListener("mouseenter", () => { hover = p.name; draw(); });
    li.addEventListener("mouseleave", () => { hover = null; draw(); });
    return li;
  }));
  for (const input of el("panels").querySelectorAll("input[data-lock]"))
    input.addEventListener("change", () => {
      locks[input.dataset.lock] = input.checked;
      if (input.checked && picked === input.dataset.lock) picked = null;
      renderEdit();
      draw();
    });
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

// One entry per panel the page changed: its box, its lock, its letter, its new name.
function edited() {
  const changes = {};
  for (const p of panelsNow()) {
    const entry = {};
    if (draft[p.name] || extra[p.name]) entry.box = boxOf(p);
    if (locks[p.name] !== undefined) entry.locked = locks[p.name];
    if (letters[p.name] !== undefined) entry.label = letters[p.name];
    if (renames[p.name] && renames[p.name] !== p.name) entry.rename = renames[p.name];
    if (Object.keys(entry).length) changes[p.name] = entry;
  }
  return changes;
}

async function arrange() {
  el("report").textContent = "arranging...";
  try {
    const answer = await (await fetch("optimize", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({layout: active, panels: draft,
                            locked: panelsNow().filter(lockedOf).map(p => p.name)}),
    })).json();
    if (answer.error) {
      el("report").className = "mm dirty";
      el("report").textContent = answer.error;
      return;
    }
    // The result is another edit, not a saved layout: it can be nudged, reverted or saved.
    for (const [name, rect] of Object.entries(answer.panels)) draft[name] = rect;
    el("report").className = "mm";
    el("report").textContent =
      [answer.summary, ...answer.notes.map(note => note.message)].join(" — ");
    renderEdit();
    draw();
  } catch (err) {
    el("report").className = "mm dirty";
    el("report").textContent = "could not arrange: " + err;
  }
}

async function save() {
  const name = el("name").value.trim();
  el("saved").className = "mm";
  el("saved").textContent = "saving...";
  try {
    const answer = await fetch("save", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({layout: active, variant: name, panels: edited(),
                            page_guides: rulers}),
    });
    const result = await answer.json();
    if (result.error) {
      el("saved").className = "mm dirty";
      el("saved").textContent = result.error;
      return;
    }
    draft = {};
    locks = {}; letters = {}; renames = {}; extra = {};
    movedGuides = false;
    picked = null;
    pickedGuide = null;
    active = result.variant;
    await refresh(true);
    el("saved").textContent = "wrote " + result.saved;
  } catch (err) {
    el("saved").className = "mm dirty";
    el("saved").textContent = "could not save: " + err;
  }
}

async function refresh(force) {
  if (!force && dirty()) return;  // do not overwrite edits that are not saved yet
  try {
    const url = "state.json" + (active ? `?layout=${active}` : "");
    const fresh = await (await fetch(url)).json();
    if (force || fresh.stamp !== stamp) {
      stamp = fresh.stamp;
      state = fresh;
      active = fresh.active;
      rulers = {x: [...((fresh.page_guides || {}).x || [])],
                y: [...((fresh.page_guides || {}).y || [])]};
      movedGuides = false;
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

el("paper").addEventListener("pointerdown", ev => {
  if (!editing()) return;
  const got = grab(atEvent(ev));
  drag = got;
  picked = got && got.mode !== "guide" ? got.name : null;
  pickedGuide = got && got.mode === "guide" ? {axis: got.axis, index: got.index} : null;
  if (got) el("paper").setPointerCapture(ev.pointerId);
  renderEdit();
  draw();
});
el("paper").addEventListener("pointermove", ev => {
  if (!drag) return;
  ev.preventDefault();
  const to = moved(atEvent(ev), ev.shiftKey);  // shift: ignore the magnets
  if (drag.mode === "guide") editGuide(drag.axis, drag.index, to);
  else edit(drag.name, to);
});
el("paper").addEventListener("pointerup", ev => {
  if (drag) el("paper").releasePointerCapture(ev.pointerId);
  // Dragged off the sheet, a guide is gone -- the gesture a drawing program uses to remove one.
  if (drag && drag.mode === "guide") {
    const at = atEvent(ev);
    const out = at[0] < -originMM[0] || at[0] > viewMM[0] - originMM[0]
             || at[1] < -originMM[1] || at[1] > viewMM[1] - originMM[1];
    if (out) {
      pickedGuide = {axis: drag.axis, index: drag.index};
      dropGuide();
    }
  }
  drag = null;
});
document.addEventListener("keydown", ev => {
  if (!editing() || ev.target.tagName === "INPUT") return;
  if (pickedGuide && (ev.key === "Delete" || ev.key === "Backspace")) {
    ev.preventDefault();
    return dropGuide();
  }
  const step = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]}[ev.key];
  if (!step) return;
  const by = ev.shiftKey ? 2 : 0.5;
  if (pickedGuide) {
    ev.preventDefault();
    const along = pickedGuide.axis === "x" ? step[0] : step[1];
    if (along)
      editGuide(pickedGuide.axis, pickedGuide.index,
                rulers[pickedGuide.axis][pickedGuide.index] + along * by);
    return;
  }
  if (!picked) return;
  ev.preventDefault();
  const chosen = panelsNow().find(p => p.name === picked);
  if (lockedOf(chosen)) return;
  const rect = boxOf(chosen);
  edit(picked, [rect[0] + step[0] * by, rect[1] + step[1] * by, rect[2], rect[3]]);
});
for (const [i, key] of ["f-x", "f-y", "f-w", "f-h"].entries())
  el(key).addEventListener("change", () => {
    if (!picked) return;
    const rect = boxOf(panelsNow().find(p => p.name === picked)).slice();
    rect[i] = parseFloat(el(key).value);
    if (!isNaN(rect[i])) edit(picked, rect);
  });
el("save").onclick = save;
el("arrange").onclick = arrange;
el("add").onclick = addPanel;
el("f-key").addEventListener("change", () => {
  if (picked) renames[picked] = el("f-key").value.trim();
  renderEdit();
});
el("f-letter").addEventListener("change", () => {
  if (picked) letters[picked] = el("f-letter").value.trim();
  renderEdit();
  draw();
});
el("f-lock").addEventListener("change", () => {
  if (picked) locks[picked] = el("f-lock").checked;
  renderEdit();
  render();
});
el("guide-x").onclick = () => addGuide("x");
el("guide-y").onclick = () => addGuide("y");
el("revert").onclick = () => {
  draft = {};
  locks = {}; letters = {}; renames = {}; extra = {};
  picked = null;
  pickedGuide = null;
  movedGuides = false;
  rulers = {x: [...((state.page_guides || {}).x || [])], y: [...((state.page_guides || {}).y || [])]};
  el("saved").textContent = "";
  el("report").textContent = "";
  renderEdit();
  draw();
};
el("z-in").onclick = () => { ppm = (ppm || 3.78) * 1.25; draw(); };
el("z-out").onclick = () => { ppm = (ppm || 3.78) / 1.25; draw(); };
el("z-one").onclick = () => { ppm = 3.78; draw(); };
el("z-fit").onclick = () => { ppm = null; draw(); };
window.addEventListener("resize", () => state && ppm === null && draw());
poll();
</script>
"""


def _checked_rect(name: str, value: Any) -> Rect:
    """One ``[x, y, w, h]`` from the page, refused unless it is a usable box in millimetres."""
    try:
        x, y, w, h = (float(v) for v in value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}: not a box of four numbers: {value!r}") from exc
    if not all(abs(v) < 1e4 for v in (x, y, w, h)):
        raise ValueError(f"{name}: {value!r} is not a box in millimetres")
    if w < 1.0 or h < 1.0:
        raise ValueError(f"{name}: a panel smaller than 1 x 1 mm is a mistake, not a layout")
    return Rect(round(x, 2), round(y, 2), round(w, 2), round(h, 2))


def _set_label(entry: dict[str, Any], text: str) -> None:
    """The letter drawn on a panel; an empty one goes back to the default."""
    if text.strip():
        entry["label"] = {**(entry.get("label") or {}), "text": text.strip()}
    else:
        entry.pop("label", None)


def _set_lock(data: dict[str, Any], name: str, locked: bool) -> None:
    """A locked panel is a frozen one: the page will not drag it, the optimizer will not resize it."""
    panels = data.setdefault("optimize", {}).setdefault("panels", {})
    entry = panels.setdefault(name, {})
    if locked:
        entry["freeze"] = True
        return
    entry.pop("freeze", None)
    if not entry:
        panels.pop(name)
    if not panels:
        data["optimize"].pop("panels")
        if not data["optimize"]:
            data.pop("optimize")


def _panel_edit(name: str, value: Any) -> dict[str, Any]:
    """One panel's edits from the page: a bare box, or a mapping of what changed."""
    if isinstance(value, dict):
        box = value.get("box")
        return {
            "box": None if box is None else _checked_rect(name, box),
            "locked": None if value.get("locked") is None else bool(value["locked"]),
            "label": value.get("label"),
            "rename": value.get("rename"),
        }
    return {"box": _checked_rect(name, value), "locked": None, "label": None, "rename": None}


def _inside_sheet(guides: dict[str, list[float]], sheet: Any) -> dict[str, list[float]]:
    """Page guides that still fall on the sheet; a guide dragged off it is gone, as intended.

    The sheet is the largest thing drawn, so a line outside it cannot be seen, cannot be
    grabbed again, and would silently come back with the layout. Without a sheet (a layout with
    no ``page:`` and ``--paper none``) there is nothing to fall off, and every guide is kept.
    """
    if sheet is None:
        return guides
    bounds = {
        "x": (-sheet.area.x, sheet.size[0] - sheet.area.x),
        "y": (-sheet.area.y, sheet.size[1] - sheet.area.y),
    }
    return {
        axis: [v for v in values if bounds[axis][0] <= v <= bounds[axis][1]]
        for axis, values in guides.items()
    }


def _margin_guides(sheet: Any) -> dict[str, list[float]]:
    """The four margins of the sheet, in layout millimetres: where page guides start from.

    A figure is arranged against the text block before anything else, so those are the lines
    the page offers when a layout carries none of its own.
    """
    if sheet is None:
        return {"x": [], "y": []}
    return {
        "x": sorted({round(sheet.text.left - sheet.area.x, 2),
                     round(sheet.text.right - sheet.area.x, 2)}),
        "y": sorted({round(sheet.text.top - sheet.area.y, 2),
                     round(sheet.text.bottom - sheet.area.y, 2)}),
    }  # fmt: skip


def _checked_guides(guides: dict[str, Any]) -> dict[str, list[float]]:
    """The page guides from the page, refused unless they are millimetres on the sheet."""
    checked: dict[str, list[float]] = {}
    for axis in ("x", "y"):
        values = list(guides.get(axis) or [])
        if len(values) > 40:
            raise ValueError(f"{len(values)} {axis} page guides is more than a figure can use")
        try:
            numbers = sorted({round(float(v), 2) for v in values})
        except (TypeError, ValueError) as exc:
            raise ValueError(f"page guides on {axis} must be numbers: {values!r}") from exc
        if not all(abs(v) < 1e4 for v in numbers):
            raise ValueError(f"page guides on {axis} are not millimetres: {values!r}")
        checked[axis] = numbers
    return checked


@dataclass
class Viewer:
    """Reads the layouts and the panel files on demand, so a rebuild is picked up.

    Args:
        target: a layout file, or the figure folder holding ``layout.yaml``.
        paper: sheet to show when a layout declares no ``page:`` section.
        editable: allow the page to save a variant (``plotplate view --edit``).
    """

    target: Path
    paper: str | None = "a4"
    editable: bool = False

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
        from .pack import Target
        from .render import panel_status

        variants = self.variants()
        active = key if key in variants else BASE if BASE in variants else next(iter(variants))
        common = {
            "stamp": self.stamp(),
            "active": active,
            "editable": self.editable,
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
        target = Target.from_layout(layout)
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
            "page_guides": layout.page_guides
            if (layout.page_guides["x"] or layout.page_guides["y"])
            else _margin_guides(sheet),
            "page_guides_from_margins": not (layout.page_guides["x"] or layout.page_guides["y"]),
            "gap": target.gap,
            "panels": [
                {
                    "name": name,
                    "label": spec.label,
                    "locked": name in target.freeze,
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

    def save(
        self,
        key: str | None,
        variant: str,
        panels: dict[str, Any],
        guides: dict[str, Any] | None = None,
    ) -> Path:
        """Write what the page holds as ``layout.<variant>.yaml``.

        The result is a resolved layout written by :func:`plotplate.pack.place_boxes`, so the
        axes keep the millimetres that hold their tick labels and the guides are re-derived
        from the edges that still coincide.

        Args:
            key: the variant that was edited, which the saved one is based on.
            variant: the name to save under, which becomes ``layout.<variant>.yaml``.
            panels: one entry per edited panel, either ``[x, y, w, h]`` or a mapping with
                ``box``, ``locked``, ``label`` and ``rename``. A name the layout does not
                have is a new panel, and then ``box`` is required.
            guides: the page guides to store, as ``{"x": [...], "y": [...]}`` in the same
                millimetres; ``None`` keeps the ones the layout already has. Guides that fall
                outside the sheet are dropped.

        Returns:
            The file that was written.

        Raises:
            PermissionError: the viewer was not started with ``--edit``.
            ValueError: the name, a box, a new panel or a rename cannot be used.
        """
        from .config import dump_yaml
        from .pack import place_boxes

        if not self.editable:
            raise PermissionError("this viewer is read-only; start it with `plotplate view --edit`")
        if not VARIANT_NAME.fullmatch(variant):
            raise ValueError(f"{variant!r} is not a variant name (letters, digits, - and _)")
        if variant == BASE:
            raise ValueError(
                "layout.yaml is the file you maintain: its comments, mosaic and journal widths "
                "would be replaced by numbers. Save under another name, and copy it over yourself"
            )
        layout = self.layout(key)
        edits = {name: _panel_edit(name, value) for name, value in panels.items()}
        old = {name: spec.box for name, spec in layout.panels.items()}
        fresh = {name: edit for name, edit in edits.items() if name not in old}
        for name, edit in fresh.items():
            if not PANEL_NAME.fullmatch(name):
                raise ValueError(f"{name!r} is not a panel name (letters, digits, - and _)")
            if edit["box"] is None:
                raise ValueError(f"{name!r} is not a panel of this layout, and has no box")
        moved = {
            name: edit["box"]
            for name, edit in edits.items()
            if name in old and edit["box"] is not None
        }
        data = layout.resolved()
        place_boxes(data, layout, old, {**old, **moved})
        for name, edit in fresh.items():  # a panel drawn on the page for the first time
            data["panels"][name] = {"box": edit["box"].to_list()}
        self._apply_panel_edits(data, layout, edits)
        if guides is not None:
            kept = _inside_sheet(_checked_guides(guides), layout.sheet_geometry(self.paper))
            data["page_guides"] = kept
            if not (kept["x"] or kept["y"]):
                data.pop("page_guides")
        path = variant_path(self.path(key), variant)
        dump_yaml(data, path)
        return path

    def _apply_panel_edits(
        self, data: dict[str, Any], layout: Layout, edits: dict[str, dict[str, Any]]
    ) -> None:
        """Locks, panel letters and renames, applied to a resolved layout in place.

        Raises:
            ValueError: a rename would orphan a drawn panel file, or collide with a panel.
        """
        for name, edit in edits.items():
            if edit["label"] is not None:
                _set_label(data["panels"][name], str(edit["label"]))
            if edit["locked"] is not None:
                _set_lock(data, name, bool(edit["locked"]))
        for name, edit in edits.items():
            if edit["rename"]:
                self._rename_panel(data, layout, name, str(edit["rename"]).strip())

    def _rename_panel(self, data: dict[str, Any], layout: Layout, name: str, fresh: str) -> None:
        """Give a panel another name, unless something has already been drawn under the old one.

        A panel's name is the name of its file (``panels/A.pdf``) and of whatever draws it, so
        renaming one that exists only on paper is free, and renaming one that has been drawn is
        a change to the figure's code that this page cannot make.

        Raises:
            ValueError: the name is not usable, is taken, or the panel is already drawn.
        """
        if not PANEL_NAME.fullmatch(fresh):
            raise ValueError(f"{fresh!r} is not a panel name (letters, digits, - and _)")
        if fresh in data["panels"]:
            raise ValueError(f"this figure already has a panel called {fresh!r}")
        drawn = sorted(p.name for p in layout.panels_dir.glob(f"{name}.*"))
        if drawn:
            raise ValueError(
                f"{name} is already drawn ({', '.join(drawn)}): renaming it here would leave "
                f"those files behind. To change only the letter, set it in this panel's `letter` "
                f"field; to change the name, use `plotplate merge <layout> {name} --as {fresh}` "
                f"and rename the panel code with it"
            )
        # Rebuilt rather than popped and re-added: panels are written in reading order, which is
        # what `labels: auto` hands out letters by, so a renamed panel keeps its place.
        data["panels"] = {
            (fresh if key == name else key): entry for key, entry in data["panels"].items()
        }
        frozen = (data.get("optimize") or {}).get("panels") or {}
        if name in frozen:
            data["optimize"]["panels"] = {
                (fresh if key == name else key): entry for key, entry in frozen.items()
            }

    def arrange(
        self, key: str | None, boxes: dict[str, Any], locked: list[str] | None = None
    ) -> dict[str, Any]:
        """What ``plotplate optimize`` makes of the boxes currently on the page.

        Nothing is written: the new boxes go back to the page as another edit, which can be
        nudged further, reverted or saved like any other. The figure keeps the size it has, so
        the button rearranges the panels inside the area instead of resizing the area under the
        pointer.

        Raises:
            PermissionError: the viewer was not started with ``--edit``.
            PackError: the panels are not a grid, or no arrangement fits.
        """
        from dataclasses import replace

        from .pack import Target, bring_inside, optimize, place_boxes

        if not self.editable:
            raise PermissionError("this viewer is read-only; start it with `plotplate view --edit`")
        layout = self.layout(key)
        old = {name: spec.box for name, spec in layout.panels.items()}
        new = {**old, **{name: _checked_rect(name, value) for name, value in boxes.items()}}
        new = bring_inside(new, layout.width, layout.height)
        data = layout.resolved()
        place_boxes(data, layout, old, new)
        # The same file path as the layout it came from: style files, journal presets and panel
        # files are all resolved relative to it, and a draft that forgot where it lives cannot
        # even be read (`../style.yaml` would be looked for next to the working directory).
        drafted = Layout(data, self.path(key))
        target = replace(
            Target.from_layout(drafted),
            width=drafted.width,
            height=drafted.height,
            freeze=tuple(sorted(set(Target.from_layout(drafted).freeze) | set(locked or ()))),
        )
        arranged, report = optimize(drafted, target)
        return {
            "panels": {name: entry["box"] for name, entry in (arranged.get("panels") or {}).items()},
            "width": report.width,
            "height": report.height,
            "summary": (
                f"gutters {report.gutters[0][0]:.1f}-{report.gutters[0][1]:.1f}"
                f" -> {report.gutters[1][0]:.1f} mm"
                f" · panels {report.occupancy[0]:.0%} -> {report.occupancy[1]:.0%}"
                f" of the figure · up to {report.stretch:.2f}x"
                + (" (chosen for you)" if report.automatic else "")
            ),
            "notes": [note.as_dict() for note in report.notes],
        }

    def figure_png(self, key: str | None = None, dpi: int = 160) -> bytes:
        """The composed figure as PNG bytes, without writing any file."""
        from .render import compose

        doc = compose(self.layout(key), labels=True)
        data: bytes = doc[0].get_pixmap(dpi=dpi).tobytes("png")
        doc.close()
        return data


class _Handler(BaseHTTPRequestHandler):
    """Three routes to read (the page, its state, the figure) and one to save a variant."""

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

    def do_POST(self) -> None:
        """Write a variant (``/save``) or re-arrange the edited boxes (``/optimize``).

        Both need ``--edit``: one writes a file, and the other only makes sense as a step
        towards writing one.
        """
        route = urlparse(self.path).path.lstrip("/")
        if route not in ("save", "optimize"):
            self.send_error(404)
            return
        # A page on another site can POST to localhost, but not with this content type and not
        # from another origin: both are checked before anything is written.
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).hostname not in ("127.0.0.1", "localhost", "::1"):
            self.send_error(403, "refused: this write came from another site")
            return
        if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
            self.send_error(415, "send application/json")
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > 1_000_000:
            self.send_error(413)
            return
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            panels = dict(payload.get("panels") or {})
            if route == "optimize":
                answer = self.viewer.arrange(payload.get("layout"), panels)
            else:
                variant = str(payload.get("variant") or "custom")
                saved = self.viewer.save(
                    payload.get("layout"), variant, panels, payload.get("page_guides")
                )
                answer = {"saved": saved.name, "variant": variant}
        except Exception as exc:  # noqa: BLE001 - the page shows the reason and stays open
            self._send(json.dumps({"error": str(exc)}).encode(), "application/json", 400)
            return
        self._send(json.dumps(answer).encode(), "application/json")

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
    path: str | Path,
    host: str = "127.0.0.1",
    port: int = 8765,
    paper: str | None = "a4",
    editable: bool = False,
) -> ThreadingHTTPServer:
    """An HTTP server showing the figure at ``path`` (call ``serve_forever`` on it)."""

    class Handler(_Handler):
        viewer = Viewer(Path(path).resolve(), paper, editable)

    return ThreadingHTTPServer((host, port), Handler)


def serve(
    path: str | Path,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    paper: str | None = "a4",
    editable: bool = False,
) -> None:
    """Serve the viewer until interrupted."""
    server = make_server(path, host, port, paper, editable)
    url = f"http://{host}:{server.server_port}/"
    viewer: Viewer = server.RequestHandlerClass.viewer  # type: ignore[attr-defined]
    print(f"plotplate view on {url}  (Ctrl-C to stop)")
    print(f"  layouts: {', '.join(viewer.variants())}")
    if editable:
        print("  editing on: drag the panels, then save them as layout.<name>.yaml")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
