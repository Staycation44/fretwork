// The column show/hide panel.
import { UI } from "./boot.js";
import { el, esc, placeUnder } from "./dom.js";
import { lab } from "./format.js";
import { state, cols, saveHidden } from "./state.js";
import { draw } from "./table.js";

function renderCD() {
  const items = cols().map(c =>
    '<div class="form-check"><input class="form-check-input" type="checkbox" id="cc' +
    esc(c) + '" data-col="' + esc(c) + '"' + (state.hidden.has(c) ? "" : " checked") + '>' +
    '<label class="form-check-label" for="cc' + esc(c) + '">' + esc(lab(c)) +
    "</label></div>").join("");
  el("cd").innerHTML = items +
    '<button class="btn btn-sm btn-outline-secondary w-100 mt-2" data-act="showall">' +
    esc(UI.columns_reset) + "</button>";
}

export function toggleCD(anchor) {
  const cd = el("cd");
  if (cd.classList.contains("show")) { cd.classList.remove("show"); return; }
  renderCD();
  cd.classList.add("show");
  placeUnder(cd, anchor);
}

export const closeCD = () => el("cd").classList.remove("show");

export function initChooser() {
  el("cd").addEventListener("change", e => {
    if (e.target.type !== "checkbox") return;
    const col = e.target.dataset.col;
    if (e.target.checked) state.hidden.delete(col); else state.hidden.add(col);
    saveHidden();
    draw();
  });
  el("cd").addEventListener("click", e => {
    if (e.target.dataset.act !== "showall") return;
    state.hidden.clear();
    saveHidden();
    draw();
    renderCD();
  });
}
