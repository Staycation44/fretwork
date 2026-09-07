// The button-group renderer shared by the sheet row and the level row.
import { el, esc } from "./dom.js";

export function chips(hostId, items, active, onPick) {
  el(hostId).innerHTML = items.map(v =>
    '<button type="button" class="btn btn-fw btn-outline-secondary' +
    (v === active ? " active" : "") + '" data-v="' + esc(v) + '">' +
    esc(v) + "</button>").join("");
  el(hostId).querySelectorAll("button")
    .forEach(b => b.onclick = () => onPick(b.dataset.v));
}
