// The two bodies the filter panel can show: a min/max box, or a value list.
import { UI, MISSING, MISS_TEXT, TIMECOLS } from "./boot.js";
import { esc } from "./dom.js";
import { lab, t, mmss, key } from "./format.js";
import { distinct, passing } from "./query.js";
import { state, idx, rowsAll } from "./state.js";

// A sentinel reads as the em dash but still matches on its raw key.
const shown = (col, k) =>
  (MISSING[col] || []).indexOf(parseFloat(k)) >= 0 ? MISS_TEXT : k;

export function rangeBody(col) {
  const f = state.filters[col], i = idx(col);
  const vals = rowsAll().map(r => r[i]).filter(v => typeof v === "number");
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const asText = v => TIMECOLS.has(col) ? mmss(v) : v.toFixed(2);
  const value = k => f && f[k] !== null && f[k] !== undefined ? f[k] : "";
  return '<div class="input-group input-group-sm">' +
    '<input type="number" class="form-control" id="ddLo" placeholder="' +
    esc(t("range_min", { v: asText(lo) })) + '" value="' + value("lo") + '">' +
    '<span class="input-group-text">&ndash;</span>' +
    '<input type="number" class="form-control" id="ddHi" placeholder="' +
    esc(t("range_max", { v: asText(hi) })) + '" value="' + value("hi") + '"></div>' +
    '<div class="d-flex gap-2 mt-2">' +
    '<button class="btn btn-sm btn-primary flex-fill" data-act="apply">' +
    esc(UI.range_apply) + '</button>' +
    '<button class="btn btn-sm btn-outline-secondary flex-fill" data-act="clear">' +
    esc(UI.range_clear) + '</button></div>' +
    '<div class="form-text mt-2">' + esc(t("range_hint", { label: lab(col) })) + '</div>';
}

export function checkboxBody(col, query) {
  const all = distinct(col);
  const matches = query
    ? all.filter(v => shown(col, v).toLowerCase().includes(query.toLowerCase()) ||
                      v.toLowerCase().includes(query.toLowerCase()))
    : all;
  const f = state.filters[col], i = idx(col), counts = {};
  passing(col).forEach(r => {
    const k = key(r[i]);
    counts[k] = (counts[k] || 0) + 1;
  });
  const search = all.length > 12
    ? '<input type="search" class="form-control form-control-sm mb-2" id="ddq" ' +
      'placeholder="' + esc(UI.value_search) + '" value="' + esc(query) + '">'
    : "";
  const items = matches.map(v =>
    '<div class="form-check"><input class="form-check-input" type="checkbox" id="cb' +
    esc(v) + '" data-v="' + esc(v) + '"' + (!f || f.sel.has(v) ? " checked" : "") + '>' +
    '<label class="form-check-label" for="cb' + esc(v) + '"><span class="v">' +
    esc(shown(col, v)) + '</span><span class="n">' + (counts[v] || 0) +
    "</span></label></div>").join("");
  return search +
    '<div class="d-flex gap-2 mb-2">' +
    '<button class="btn btn-sm btn-outline-secondary flex-fill" data-act="all">' +
    esc(UI.select_all) + '</button>' +
    '<button class="btn btn-sm btn-outline-secondary flex-fill" data-act="none">' +
    esc(UI.select_none) + '</button></div>' +
    '<div class="list">' + items + "</div>";
}
