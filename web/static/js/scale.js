// The green-yellow-red ramp shared with the spreadsheet's colour scale.
import { SCALED } from "./boot.js";
import { isMissing } from "./format.js";
import { cols } from "./state.js";

const LOW = [198, 239, 206], MID = [255, 235, 156], HIGH = [255, 199, 206];

// Position v within [lo, hi] on the ramp.
export function scaleColor(v, lo, hi) {
  const ratio = hi === lo ? 0.5 : Math.max(0, Math.min(1, (v - lo) / (hi - lo)));
  const [from, to, step] = ratio < 0.5
    ? [LOW, MID, ratio * 2]
    : [MID, HIGH, (ratio - 0.5) * 2];
  const mix = from.map((n, i) => Math.round(n + (to[i] - n) * step));
  return "rgb(" + mix.join(",") + ")";
}

// Min/max per scaled column across the given rows, ignoring missing values.
export function ranges(rows) {
  const out = {}, columns = cols();
  SCALED.forEach(c => {
    const i = columns.indexOf(c);
    if (i < 0) return;
    const vals = rows.map(r => r[i]).filter(v => !isMissing(c, v));
    if (vals.length) out[c] = [Math.min(...vals), Math.max(...vals)];
  });
  return out;
}
