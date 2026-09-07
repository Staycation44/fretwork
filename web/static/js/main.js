// Entry module: label the chrome, wire the panels, then first paint.
import { UI } from "./boot.js";
import { el, esc } from "./dom.js";
import { initDropdown } from "./dropdown.js";
import { initChooser } from "./chooser.js";
import { initRouter, render } from "./router.js";
import { state } from "./state.js";

function labelChrome() {
  el("brand").innerHTML = esc(UI.title) +
    ' <span class="fw-accent">&#9679;</span> <span class="fw-normal">' +
    esc(UI.subtitle) + "</span>";
  el("q").placeholder = UI.search;
  el("cols").textContent = UI.columns;
  el("cols").title = UI.columns_tip;
}

labelChrome();
initDropdown();
initChooser();
initRouter();

// Open on Expert only; the chips read this back as their active state.
state.filters["Level"] = { type: "set", sel: new Set(["Expert"]) };
render();
