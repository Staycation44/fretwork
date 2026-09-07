// The per-column filter panel: a min/max box for wide numeric columns,
// a checkbox list otherwise.
import { el, placeUnder } from "./dom.js";
import { rangeBody, checkboxBody } from "./dropdown_view.js";
import { distinct, useRange } from "./query.js";
import { state } from "./state.js";
import { draw } from "./table.js";

function renderDD(query) {
  const col = state.ddCol;
  el("dd").innerHTML = useRange(col) ? rangeBody(col) : checkboxBody(col, query);
  const box = el("ddq");
  if (box) { box.oninput = () => renderDD(box.value); box.focus(); }
}

export function openDD(col, anchor) {
  state.ddCol = col;
  const dd = el("dd");
  dd.classList.add("show");
  renderDD("");
  placeUnder(dd, anchor);
}

export function closeDD() {
  state.ddCol = null;
  el("dd").classList.remove("show");
}

// Every value checked is the same as no filter at all.
function applyChecked() {
  const boxes = [...el("dd").querySelectorAll("input[type=checkbox]")];
  const picked = new Set(boxes.filter(b => b.checked).map(b => b.dataset.v));
  if (picked.size === distinct(state.ddCol).length) delete state.filters[state.ddCol];
  else state.filters[state.ddCol] = { type: "set", sel: picked };
  draw();
}

function applyRange() {
  const lo = el("ddLo").value, hi = el("ddHi").value;
  if (lo === "" && hi === "") delete state.filters[state.ddCol];
  else state.filters[state.ddCol] = {
    type: "range", lo: lo === "" ? null : +lo, hi: hi === "" ? null : +hi,
  };
  draw();
  closeDD();
}

const ACTIONS = {
  all:   () => { delete state.filters[state.ddCol]; draw(); renderDD(""); },
  none:  () => { state.filters[state.ddCol] = { type: "set", sel: new Set() };
                 draw(); renderDD(""); },
  clear: () => { delete state.filters[state.ddCol]; draw(); closeDD(); },
  apply: applyRange,
};

export function initDropdown() {
  el("dd").addEventListener("change", e => {
    if (e.target.type === "checkbox") applyChecked();
  });
  el("dd").addEventListener("click", e => {
    const act = ACTIONS[e.target.dataset.act];
    if (act) act();
  });
}
