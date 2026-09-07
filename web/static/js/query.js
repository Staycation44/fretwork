// Selecting and ordering rows: what the active filters and sort resolve to.
import { RANGE_MIN_DISTINCT } from "./boot.js";
import { el } from "./dom.js";
import { isMissing, key } from "./format.js";
import { state, cols, idx, rowsAll } from "./state.js";

const SEARCH_COLS = ["Song Title", "Artist", "Charter", "Release", "Code"];

function isNumeric(col) {
  const i = idx(col);
  return rowsAll().some(r => typeof r[i] === "number") &&
         rowsAll().every(r => r[i] === null || typeof r[i] === "number");
}

// Every distinct value in a column, numerically ordered where possible.
export function distinct(col) {
  const i = idx(col);
  return [...new Set(rowsAll().map(r => key(r[i])))].sort((a, b) => {
    const x = parseFloat(a), y = parseFloat(b);
    return !isNaN(x) && !isNaN(y) ? x - y : a.localeCompare(b);
  });
}

// A min/max box suits a numeric column with too many values to list.
export const useRange = col =>
  isNumeric(col) && distinct(col).length > RANGE_MIN_DISTINCT;

function matchesSearch(row, columns) {
  const q = el("q").value.trim().toLowerCase();
  if (!q) return true;
  return SEARCH_COLS.map(n => columns.indexOf(n)).filter(i => i >= 0)
    .some(i => String(row[i] ?? "").toLowerCase().includes(q));
}

function matchesFilter(row, columns, col, filter) {
  const i = columns.indexOf(col);
  if (i < 0) return true;
  const v = row[i];
  if (filter.type === "set") return filter.sel.has(key(v));
  if (typeof v !== "number") return false;
  return (filter.lo === null || v >= filter.lo) &&
         (filter.hi === null || v <= filter.hi);
}

// Rows passing the search and every filter except exceptCol, so a dropdown
// can count values in the context of the other active filters.
export function passing(exceptCol) {
  const columns = cols();
  return rowsAll().filter(row =>
    matchesSearch(row, columns) &&
    Object.entries(state.filters).every(([col, f]) =>
      col === exceptCol || matchesFilter(row, columns, col, f)));
}

// Missing values sort last in both directions.
export function compare(a, b) {
  const am = isMissing(state.sortCol, a), bm = isMissing(state.sortCol, b);
  if (am || bm) return am && bm ? 0 : (am ? 1 : -1);
  if (typeof a === "number" && typeof b === "number")
    return state.sortAsc ? a - b : b - a;
  return state.sortAsc
    ? String(a).localeCompare(String(b))
    : String(b).localeCompare(String(a));
}
