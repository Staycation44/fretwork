// All mutable page state, in one object because ES module imports are
// read-only bindings and several of these are reassigned wholesale.
import { DATA } from "./boot.js";

const STORAGE_KEY = "fw.hidden";

function loadHidden() {
  try { return new Set(JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]")); }
  catch (e) { return new Set(); }
}

export const state = {
  sheet: Object.keys(DATA)[0],
  sortCol: "D",
  sortAsc: false,
  filters: {},        // column -> {type:"set", sel:Set} | {type:"range", lo, hi}
  ddCol: null,        // column whose filter dropdown is open
  hidden: loadHidden(),
};

// Remember hidden columns per browser; storage may be unavailable.
export function saveHidden() {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify([...state.hidden])); }
  catch (e) {}
}

export const cols = () => DATA[state.sheet].columns;
export const rowsAll = () => DATA[state.sheet].rows;
export const idx = name => cols().indexOf(name);

// [column, index-into-row] for every column still on screen.
export const visible = () =>
  cols().map((c, i) => [c, i]).filter(([c]) => !state.hidden.has(c));
