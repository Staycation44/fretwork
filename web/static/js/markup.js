// Builds the table's HTML. Everything it needs is passed in.
import { SCALED, TIMECOLS, HELP, UI, MISS_TEXT, MISS_HELP } from "./boot.js";
import { esc } from "./dom.js";
import { lab, mmss, isMissing } from "./format.js";
import { scaleColor } from "./scale.js";

export function headerCell(col, { sorted, ascending, filtered }) {
  const cls = [sorted ? "sorted" : "", filtered ? "filtered" : ""].join(" ").trim();
  const tip = (HELP[col] ? HELP[col] + "\n\n" : "") + "Column: " + col + "\n" + UI.sort_tip;
  const arrow = sorted ? (ascending ? " &#9650;" : " &#9660;") : "";
  return '<th data-c="' + esc(col) + '"' + (cls ? ' class="' + cls + '"' : '') +
    '><div class="thw">' +
    '<span class="lbl" data-sort="' + esc(col) + '" title="' + esc(tip) + '">' +
    esc(lab(col)) + arrow + '</span>' +
    '<button class="btn btn-sm btn-link p-0 px-1 flt text-secondary" data-flt="' +
    esc(col) + '" title="' + esc(UI.filter_tip) + '">&#9662;</button></div></th>';
}

function numberCell(col, v, bounds) {
  const text = Number.isInteger(v) ? v : v.toFixed(2);
  if (!SCALED.has(col) || !bounds) return '<td class="num">' + text + "</td>";
  return '<td class="num"><span class="scale" style="background:' +
    scaleColor(v, bounds[0], bounds[1]) + '">' + text + "</span></td>";
}

function bodyCell(col, v, bounds) {
  if (col === "Code")
    return '<td class="code" title="' + esc(UI.copy_code_tip) + '">' + esc(v) +
      '<span class="cp" data-copy="' + esc(v) + '">&#128203;</span></td>';
  if (col === "Level")
    return '<td><span class="badge rounded-pill lvl ' + esc(v) + '">' + esc(v) + "</span></td>";
  if (col === "Song Title" || col === "Artist")
    return '<td class="title" title="' + esc(v ?? "") + '">' + esc(v ?? "") + "</td>";
  if (isMissing(col, v)) {
    const tip = MISS_HELP[col] || "";
    return '<td class="num blank"' + (tip ? ' title="' + esc(tip) + '"' : '') +
      ">" + MISS_TEXT + "</td>";
  }
  if (TIMECOLS.has(col) && typeof v === "number")
    return '<td class="num">' + mmss(v) + "</td>";
  if (typeof v === "number") return numberCell(col, v, bounds);
  return "<td>" + esc(v === null ? "" : v) + "</td>";
}

export function bodyRow(row, visibleCols, code, bounds) {
  const cells = visibleCols
    .map(([col, i]) => bodyCell(col, row[i], bounds[col]))
    .join("");
  return '<tr title="' + esc(UI.row_tip) + '" data-code="' + esc(code) + '">' +
    cells + "</tr>";
}

export function emptyRow(span) {
  return '<tr><td colspan="' + span + '" class="text-secondary p-3">' +
    esc(UI.no_data) + "</td></tr>";
}
