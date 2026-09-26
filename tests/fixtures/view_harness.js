// Runs the viewer's own script (src/plotplate/view.py, the PAGE constant) against a DOM small
// enough to live here, so that dragging, snapping and saving are exercised without a browser.
// Usage: node view_harness.js <folder with state.json and page.js>. Exits 1 on the first failure.
const fs = require("fs");
const folder = process.argv[2];
const state = JSON.parse(fs.readFileSync(folder + "/state.json", "utf8"));
const posted = [];
let failures = 0;

class Node {
  constructor(tag) {
    this.tag = tag; this.children = []; this.attrs = {}; this.handlers = {};
    this.style = {}; this.dataset = {}; this.checked = false; this.value = "";
    this.textContent = ""; this.innerHTML = ""; this.hidden = false; this.className = "";
    this.classList = {toggle: () => {}, add: () => {}, remove: () => {}};
  }
  setAttribute(k, v) { this.attrs[k] = v; }
  getAttribute(k) { return this.attrs[k]; }
  appendChild(node) { this.children.push(node); return node; }
  replaceChildren(...nodes) { this.children = nodes; }
  addEventListener(type, fn) { (this.handlers[type] ||= []).push(fn); }
  fire(type, event) { for (const fn of this.handlers[type] || []) fn(event); }
  querySelectorAll() { return []; }
  setPointerCapture() {} releasePointerCapture() {}
  getBoundingClientRect() { return {left: 0, top: 0, width: 794, height: 1123}; }
  get clientWidth() { return 900; }
  rects() {
    const found = this.tag === "rect" ? [this] : [];
    for (const child of this.children) found.push(...child.rects());
    return found;
  }
}

const ids = {};
const el = id => (ids[id] ||= new Node("div"));
for (const id of ["t-sheet", "t-panels", "t-axes", "t-guides", "t-figure"]) el(id).checked = true;
el("paper").tag = "svg";

global.document = {
  getElementById: el,
  createElementNS: (ns, tag) => new Node(tag),
  createElement: tag => new Node(tag),
  querySelectorAll: () => [],
  addEventListener: (type, fn) => ((document.handlers[type] ||= []).push(fn)),
  handlers: {},
};
global.window = {addEventListener: () => {}};
global.setTimeout = () => {};  // the polling chain stops here
global.fetch = async (url, options) => {
  if (url.startsWith("save")) {
    posted.push(JSON.parse(options.body));
    return {json: async () => ({saved: "layout.custom.yaml", variant: "custom"})};
  }
  return {json: async () => state};
};

eval(fs.readFileSync(folder + "/page.js", "utf8"));

const area = state.sheet.area;  // the figure sits here on the sheet, and events are in sheet mm
const mm = (x, y) => [area[0] + x, area[1] + y];
const pointer = (type, at, extra = {}) => el("paper").fire(type, {
  clientX: at[0] / state.sheet.size[0] * 794, clientY: at[1] / state.sheet.size[1] * 1123,
  pointerId: 1, preventDefault: () => {}, ...extra,
});
const boxes = () => Object.fromEntries(el("paper").rects()
  .filter(rect => rect.attrs["data-panel"])
  .map(rect => [rect.attrs["data-panel"],
                [rect.attrs.x, rect.attrs.y, rect.attrs.width, rect.attrs.height]]));

function check(name, got) {
  if (!got) failures += 1;
  console.log((got ? "ok   " : "FAIL ") + name);
}

setImmediate(async () => {
  await new Promise(resolve => setImmediate(resolve));  // let the first refresh land
  check("the three panels are drawn", Object.keys(boxes()).length === 3);
  check("nothing is selected yet", el("picked").innerHTML.includes("drag a panel"));

  pointer("pointerdown", mm(130, 30));  // grab B in the middle, drag it left and down
  check("B is selected", el("picked").innerHTML.includes("<b>B</b>"));
  pointer("pointermove", mm(110, 33));
  pointer("pointerup", mm(110, 33));
  check("B moved, and stuck to the gutter next to A", boxes().B.join() === "73.5,3,89.5,62");
  check("A stayed where it was", boxes().A.join() === "0,0,89.5,62");
  check("the fields follow the drag", el("f-x").value === 73.5);
  check("unsaved changes are announced", el("saved").textContent.includes("not saved"));
  const axes = el("paper").rects().filter(rect => rect.attrs.stroke === "#d97706");
  check("the axes rode along", axes.some(a => Math.abs(a.attrs.x - 84.5) < 0.01));

  pointer("pointerdown", mm(60, 30));   // select A, then drag its bottom-right corner
  pointer("pointerdown", mm(89.5, 62));
  pointer("pointermove", mm(182, 65.2));
  pointer("pointerup", mm(182, 65.2));
  check("the corner snapped to the figure edge and to B's bottom",
        boxes().A.join() === "0,0,183,65");

  document.handlers.keydown[0]({key: "ArrowRight", shiftKey: false, preventDefault: () => {},
                                target: {tagName: "DIV"}});
  check("an arrow key nudges by 0.5 mm", boxes().A[0] === 0.5);

  el("revert").onclick();
  check("revert brings back the file's boxes", boxes().B.join() === "93.5,0,89.5,62");

  pointer("pointerdown", mm(130, 30));
  pointer("pointermove", mm(110, 33));
  pointer("pointerup", mm(110, 33));
  await el("save").onclick();
  check("only the panel that moved is sent",
        posted.length === 1 && Object.keys(posted[0].panels).join() === "B");
  check("the save says where it went", el("saved").textContent.includes("wrote"));
  process.exit(failures ? 1 : 0);
});
