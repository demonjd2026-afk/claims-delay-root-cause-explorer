// Application shell: navigation, global filters and view lifecycle.
import { api } from "./api.js";
import { destroyCharts, failure, fmt, h, loading } from "./ui.js";
import { closeClaim } from "./views/claims.js";
import { VIEWS } from "./views/index.js";

const state = { view: "summary", params: {}, filters: { date_from: "", date_to: "", lob: "", platform: "" }, meta: null };
const viewEl = document.getElementById("view");
const form = document.getElementById("filters");
let renderToken = 0;

function go(view, params = {}) {
  const hash = `#${view}${params.theme ? `/${params.theme}` : ""}`;
  if (location.hash === hash) render(); else location.hash = hash;
}

function readHash() {
  const [view, theme] = location.hash.replace(/^#/, "").split("/");
  state.view = VIEWS.some((v) => v.id === view) ? view : "summary";
  state.params = theme ? { theme } : {};
}

async function render() {
  const token = ++renderToken;
  const view = VIEWS.find((v) => v.id === state.view);
  document.getElementById("page-title").textContent = view.title;
  document.getElementById("page-lede").textContent = view.lede;
  document.title = `${view.title} | Claims Delay Root-Cause Explorer`;
  document.querySelectorAll("#nav button").forEach((b) =>
    (b.dataset.view === view.id ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current")));
  form.style.visibility = view.usesFilters === false ? "hidden" : "visible";
  closeClaim();
  destroyCharts();
  viewEl.replaceChildren(loading());
  try {
    const content = await view.render({ api, state, go, reloadData, rerender: render, filters: { ...state.filters } });
    if (token !== renderToken) return;
    viewEl.replaceChildren(...[content].flat().filter(Boolean));
    window.scrollTo({ top: 0 });
  } catch (error) {
    if (token === renderToken) viewEl.replaceChildren(failure(error));
  }
}

function buildNav() {
  const nav = document.getElementById("nav");
  for (const view of VIEWS) {
    const icon = h("span", { "aria-hidden": "true" });
    icon.innerHTML = `<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">${view.icon}</svg>`;
    nav.append(h("button", { type: "button", "data-view": view.id, onclick: () => go(view.id) }, icon.firstChild, view.label));
  }
}

function fillSelect(select, values) {
  select.replaceChildren(h("option", { value: "" }, "All"), ...values.map((value) => h("option", { value }, value)));
}

/** Point the filters and the sidebar note at the data currently loaded. */
function applyMeta(meta) {
  state.meta = meta;
  fillSelect(form.lob, meta.lobs);
  fillSelect(form.platform, meta.platforms);
  for (const name of ["date_from", "date_to"]) { form[name].min = meta.date_min; form[name].max = meta.date_max; }
  form.date_from.value = meta.date_min; form.date_to.value = meta.date_max;
  state.filters = { date_from: meta.date_min, date_to: meta.date_max, lob: "", platform: "" };
  document.getElementById("side-note").textContent =
    `Synthetic data for demonstration. Claims received ${fmt.dateFull(meta.date_min)} to ${fmt.dateFull(meta.date_max)}, status as of ${fmt.dateFull(meta.as_of)}.`;
}

function bindFilters() {
  form.addEventListener("change", () => {
    if (form.date_from.value && form.date_to.value && form.date_from.value > form.date_to.value) form.date_to.value = form.date_from.value;
    state.filters = { date_from: form.date_from.value, date_to: form.date_to.value, lob: form.lob.value, platform: form.platform.value };
    render();
  });
  form.addEventListener("reset", (event) => { event.preventDefault(); applyMeta(state.meta); render(); });
}

/** Called after the data has been rebuilt for another period. */
async function reloadData() {
  applyMeta(await api.meta());
}

async function start() {
  buildNav();
  bindFilters();
  try {
    await document.fonts?.ready;  // charts draw text on canvas, so wait for the typeface
    applyMeta(await api.meta());
  } catch (error) {
    viewEl.replaceChildren(failure(error));
    return;
  }
  readHash();
  window.addEventListener("hashchange", () => { readHash(); render(); });
  render();
}

start();
