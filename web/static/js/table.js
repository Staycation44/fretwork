// One repaint: filter, sort, render, then refresh the footer and level chips.
import { LEVELS, UI } from "./boot.js";
import { chips } from "./chips.js";
import { el } from "./dom.js";
import { t } from "./format.js";
import { headerCell, bodyRow, emptyRow } from "./markup.js";
import { passing, compare } from "./query.js";
import { ranges } from "./scale.js";
import { state, cols, idx, rowsAll, visible } from "./state.js";

function paintFooter(shown, total) {
  el("count").textContent = t("count", { shown: shown, total: total });
  const n = Object.keys(state.filters).length;
  const clear = el("clear");
  clear.textContent = n === 1 ? UI.clear_one : t("clear_many", { n: n });
  clear.classList.toggle("d-none", n === 0);
}

// The level chips are a shortcut into the Level column filter, so they read
// their active state back out of it.
function paintLevelChips() {
  const f = state.filters["Level"];
  const active = f && f.type === "set" && f.sel.size === 1 ? [...f.sel][0] : null;
  chips("levels", LEVELS, active, v => {
    if (active === v) delete state.filters["Level"];
    else state.filters["Level"] = { type: "set", sel: new Set([v]) };
    draw();
  });
}

export function draw() {
  const vis = visible();
  const sortIdx = idx(state.sortCol);
  const rows = passing(null);
  if (sortIdx >= 0) rows.sort((a, b) => compare(a[sortIdx], b[sortIdx]));

  el("head").innerHTML = vis.map(([c]) => headerCell(c, {
    sorted: c === state.sortCol,
    ascending: state.sortAsc,
    filtered: Boolean(state.filters[c]),
  })).join("");

  const bounds = ranges(rows);
  const codeIdx = cols().indexOf("Code");
  el("body").innerHTML = rows.length
    ? rows.map(r => bodyRow(r, vis, r[codeIdx], bounds)).join("")
    : emptyRow(vis.length);

  paintFooter(rows.length, rowsAll().length);
  paintLevelChips();
}
