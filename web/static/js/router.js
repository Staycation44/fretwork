// The one document-level click handler. Order is behaviour: each branch
// returns so a more specific target wins over the row click beneath it.
import { DATA } from "./boot.js";
import { chips } from "./chips.js";
import { el } from "./dom.js";
import { t } from "./format.js";
import { openDD, closeDD } from "./dropdown.js";
import { toggleCD, closeCD } from "./chooser.js";
import { openGraph, closeGraph, toast } from "./overlay.js";
import { state, idx } from "./state.js";
import { draw } from "./table.js";

function sortBy(col) {
  if (col === state.sortCol) state.sortAsc = !state.sortAsc;
  else { state.sortCol = col; state.sortAsc = false; }
  draw();
}

function copyCode(event, cell) {
  event.stopPropagation();
  navigator.clipboard?.writeText(cell.dataset.copy);
  toast(t("copied", { code: cell.dataset.copy }));
}

function onClick(e) {
  if (e.target.closest("#dd") || e.target.closest("#cd")) return;

  if (e.target.closest("#cols")) { closeDD(); toggleCD(el("cols")); return; }
  closeCD();

  const flt = e.target.closest("[data-flt]");
  if (flt) {
    const col = flt.dataset.flt;
    if (state.ddCol === col) closeDD(); else openDD(col, flt.closest("th"));
    return;
  }
  closeDD();

  const label = e.target.closest("[data-sort]");
  if (label) { sortBy(label.dataset.sort); return; }

  const pip = e.target.closest("[data-copy]");
  if (pip) { copyCode(e, pip); return; }

  const row = e.target.closest("tbody tr[data-code]");
  if (row) { openGraph(row.dataset.code); return; }

  if (e.target.closest("#modal")) closeGraph();
}

function onKeydown(e) {
  if (e.key !== "Escape") return;
  closeDD();
  closeCD();
  closeGraph();
}

// Repaint the sheet chips too, since switching sheets re-enters here.
export function render() {
  chips("sheets", Object.keys(DATA), state.sheet, v => {
    state.sheet = v;
    state.filters = {};
    if (idx(state.sortCol) < 0) state.sortCol = "D";
    render();
  });
  draw();
}

export function initRouter() {
  document.addEventListener("click", onClick);
  document.addEventListener("keydown", onKeydown);
  el("q").addEventListener("input", draw);
  el("clear").addEventListener("click", () => { state.filters = {}; draw(); });
}
