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
for (const id of ["t-sheet", "t-panels", "t-axes", "t-guides", "t-pguides", "t-figure"])
  el(id).checked = true;
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
  if (url.startsWith("optimize")) {
    posted.push(JSON.parse(options.body));
    return {json: async () => ({                       // what the real route answers with
      panels: {A: [0, 0, 89.5, 62], B: [93.5, 0, 89.5, 62], C: [0, 66, 183, 54]},
      width: 183, height: 120, summary: "panels 90% -> 96% of the figure", notes: [],
    })};
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
const guides = () => el("paper").children.flatMap(function lines(node) {
  return (node.tag === "line" && node.attrs["data-guide"] ? [node] : [])
    .concat(node.children.flatMap(lines));
}).map(node => node.attrs);

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
  check("B moved, and its bottom stuck to C's top edge", boxes().B.join() === "73.5,4,89.5,62");
  check("A stayed where it was", boxes().A.join() === "0,0,89.5,62");
  check("the fields follow the drag", el("f-x").value === 73.5);
  check("unsaved changes are announced", el("saved").textContent.includes("not saved"));
  const axes = el("paper").rects().filter(rect => rect.attrs.stroke === "#d97706");
  check("the axes rode along", axes.some(a => Math.abs(a.attrs.x - 84.5) < 0.01));

  pointer("pointerdown", mm(118.25, 35));           // drag it back towards A, stopping short
  pointer("pointermove", mm(137.95, 35));
  pointer("pointerup", mm(137.95, 35));
  check("it stops one gutter away from A, not against it",
        boxes().B[0] === 93.5);                     // A ends at 89.5, and the gutter is 4 mm

  pointer("pointerdown", mm(60, 30));   // select A, then drag its bottom-right corner
  pointer("pointerdown", mm(89.5, 62));
  pointer("pointermove", mm(182, 65.2));
  pointer("pointerup", mm(182, 65.2));
  check("the corner snapped to the figure edge and to B's bottom",
        boxes().A.join() === "0,0,183,66");

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

  // --- page guides ---------------------------------------------------------------------
  check("the layout's page guide is drawn across the sheet", guides().length === 1
        && Number(guides()[0].x1) === 91.5
        && Number(guides()[0].y1) < 0            // it starts above the figure, on the sheet
        && Number(guides()[0].y2) > state.height);
  el("guide-y").onclick();
  check("a guide can be added", guides().length === 2
        && el("picked").innerHTML.includes("page guide y"));
  document.handlers.keydown[0]({key: "ArrowDown", shiftKey: true, preventDefault: () => {},
                                target: {tagName: "DIV"}});
  check("an arrow key moves the selected guide", guides().some(g => Number(g.y1) === 62));
  check("changed guides count as unsaved", el("saved").textContent.includes("not saved"));

  pointer("pointerdown", mm(60, 62));               // grab that guide and drag it up a little
  pointer("pointermove", mm(60, 60.9));
  pointer("pointerup", mm(60, 60.9));
  check("a dragged guide sticks to a panel edge",
        guides().some(g => Number(g.y1) === 62));   // B's bottom edge, not 60.9
  document.handlers.keydown[0]({key: "Delete", preventDefault: () => {},
                                target: {tagName: "DIV"}});
  check("delete removes the selected guide", guides().length === 1);

  // and the other way round: a panel dragged near a page guide sticks to it
  pointer("pointerdown", mm(40, 30));               // A, dragged right until its edge nears 91.5
  pointer("pointermove", mm(42.2, 30));
  pointer("pointerup", mm(42.2, 30));
  check("a panel sticks to a page guide", boxes().A[0] === 2);

  // --- locking, adding, renaming ---------------------------------------------------------
  pointer("pointerdown", mm(40, 30));                 // select A and lock it
  el("f-lock").checked = true;
  el("f-lock").fire("change");
  check("it stays selected while locked", el("picked").innerHTML.includes("<b>A"));
  check("its fields are read-only", el("f-x").disabled === true);
  const before = boxes().A.join();
  pointer("pointerdown", mm(40, 30));                 // ... and now it cannot be dragged
  pointer("pointermove", mm(52, 38));
  pointer("pointerup", mm(52, 38));
  check("a locked panel does not move", boxes().A.join() === before);
  check("clicking it selects it again, which is how it is unlocked",
        el("picked").innerHTML.includes("<b>A") && el("f-lock").checked === true);
  pointer("pointerdown", mm(40, 30));                 // a click on a locked panel must not
  pointer("pointermove", mm(40, 30));                 // fall through to whatever is under it
  pointer("pointerup", mm(40, 30));
  check("nothing under it is dragged instead", boxes().B.join() === "93.5,0,89.5,62");
  el("f-lock").checked = false;                       // unlock it from the same panel
  el("f-lock").fire("change");
  pointer("pointerdown", mm(40, 30));
  pointer("pointermove", mm(44, 30));
  pointer("pointerup", mm(44, 30));
  check("unlocked, it moves again", boxes().A[0] === 6);  // it was at 2, dragged 4 mm right
  el("f-lock").checked = true;                        // lock it again for what follows
  el("f-lock").fire("change");
  check("a locked panel is drawn differently",
        el("paper").rects().some(r => r.attrs["data-panel"] === "A"
                                      && r.attrs["stroke-dasharray"] !== "none"));

  el("add").onclick();
  check("a panel can be added", Object.keys(boxes()).length === 4 && boxes().D);
  check("it is selected, and named after the next free letter", el("f-key").value === "D");
  el("f-letter").value = "d";
  el("f-letter").fire("change");
  pointer("pointerdown", mm(30, boxes().D[1] + 5));   // the new panel drags like any other
  pointer("pointermove", mm(34, boxes().D[1] + 5));
  pointer("pointerup", mm(34, boxes().D[1] + 5));
  check("the new panel moves", boxes().D[0] === 4);

  posted.length = 0;
  await el("save").onclick();
  const sent = posted[0].panels;
  check("the save carries the box, the lock and the letter",
        sent.A.locked === true && sent.D.box.length === 4 && sent.D.label === "d");

  // --- a guide dragged off the sheet is removed --------------------------------------------
  el("guide-y").onclick();
  const kept = guides().length;
  pointer("pointerdown", mm(60, boxes().C ? state.height / 2 : 60));
  pointer("pointermove", [105, 320]);                 // below the bottom of the A4 sheet
  pointer("pointerup", [105, 320]);
  check("dragging a guide off the sheet removes it", guides().length === kept - 1);

  // --- arrange -------------------------------------------------------------------------
  pointer("pointerdown", mm(40, 30));                 // lock A again: saving cleared the edits
  el("f-lock").checked = true;
  el("f-lock").fire("change");
  posted.length = 0;
  await el("arrange").onclick();
  check("arranging sends the draft, the locks included",
        posted.length === 1 && posted[0].locked.join() === "A");
  check("the answer becomes the new draft", boxes().A.join() === "0,0,89.5,62");
  check("the report is shown", el("report").textContent.includes("96%"));
  el("revert").onclick();
  check("revert puts everything back: boxes, guides, locks and added panels",
        guides().length === 1 && Object.keys(boxes()).length === 3
        && boxes().A.join() === "0,0,89.5,62"
        && el("paper").rects().every(r => r.attrs["stroke-dasharray"] !== "2 1.5"));
  process.exit(failures ? 1 : 0);
});
