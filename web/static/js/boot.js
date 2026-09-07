// Server-injected data, parsed once from the JSON island in index.html.
// Re-exported under the names the rest of the page uses.
const BOOT = JSON.parse(document.getElementById("fw-boot").textContent);

export const DATA = BOOT.data;
export const LABELS = BOOT.labels;
export const HELP = BOOT.help;
export const UI = BOOT.ui;
export const SCALED = new Set(BOOT.scaled);
export const TIMECOLS = new Set(BOOT.timecols);
export const MISSING = BOOT.missing;
export const MISS_TEXT = BOOT.missText;
export const MISS_HELP = BOOT.missHelp;

export const LEVELS = ["Expert", "Hard", "Medium", "Easy"];

// Numeric columns with more distinct values than this get a min/max box
// instead of a checkbox list.
export const RANGE_MIN_DISTINCT = 25;
