// The graph lightbox and the transient hint, the page's two overlays.
import { UI } from "./boot.js";
import { el, esc } from "./dom.js";
import { cols, rowsAll } from "./state.js";

let hintTimer = null;

export function toast(message) {
  const hint = el("hint");
  hint.firstElementChild.textContent = message;
  hint.classList.add("on");
  clearTimeout(hintTimer);
  hintTimer = setTimeout(() => hint.classList.remove("on"), 1400);
}

// Names the chart being shown, so the graph is never unlabelled.
function heading(code) {
  const columns = cols();
  const row = rowsAll().find(r => r[columns.indexOf("Code")] === code);
  const get = name => {
    const i = columns.indexOf(name);
    return i < 0 || row === undefined ? "" : row[i];
  };
  return '<div class="mhead"><strong>' + esc(get("Song Title")) + '</strong>' +
    '<span class="text-secondary">' + esc(get("Artist")) + '</span>' +
    '<span class="badge rounded-pill lvl ' + esc(get("Level")) + '">' +
    esc(get("Level")) + '</span>' +
    '<span class="text-secondary">' + esc(get("Type")) + '</span></div>';
}

export function openGraph(code) {
  const modal = el("modal"), card = modal.querySelector(".mcard");
  const head = heading(code);
  const message = text => head + '<div class="text-secondary py-4">' + esc(text) + "</div>";

  modal.classList.add("on");
  card.innerHTML = message(UI.rendering);

  const img = new Image();
  img.onload = () => { card.innerHTML = head; card.appendChild(img); };
  img.onerror = () => { card.innerHTML = message(UI.render_failed); };
  img.src = "/graph/" + code + ".png";
}

export const closeGraph = () => el("modal").classList.remove("on");
