// The two DOM primitives every other module builds on.

export const el = id => document.getElementById(id);

export const esc = v => String(v)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");

// Drop a panel just under its anchor, kept inside the viewport.
export function placeUnder(panel, anchor) {
  const box = anchor.getBoundingClientRect();
  panel.style.left = Math.min(box.left, window.innerWidth - panel.offsetWidth - 10) + "px";
  panel.style.top = (box.bottom + 4) + "px";
}
