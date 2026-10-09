import { api } from "../api.js";
import { failure, fmt, h, loading } from "../ui.js";

const drawer = document.getElementById("drawer");
const backdrop = document.getElementById("drawer-backdrop");
let lastFocus = null;

export function closeClaim() {
  if (drawer.hidden) return;
  drawer.hidden = true; backdrop.hidden = true;
  lastFocus?.focus?.();
}
backdrop.addEventListener("click", closeClaim);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeClaim(); });

export async function openClaim(claimId) {
  lastFocus = document.activeElement;
  drawer.hidden = false; backdrop.hidden = false;
  drawer.replaceChildren(loading());
  try {
    const c = await api.claim(claimId);
    const close = h("button", { class: "close", type: "button", "aria-label": "Close", onclick: closeClaim }, "×");
    drawer.replaceChildren(...[
      h("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "12px" } },
        h("div", {}, h("h2", {}, `Claim ${c.claim_id}`),
          h("p", { class: "muted small" }, `${c.status}, ${fmt.one(c.age_days)} days from receipt`),
          c.over_target && h("span", { class: "tag alert", style: { marginTop: "6px" } }, `Over the ${c.target_days}-day target`)),
        close),
      c.pend && h("div", { class: "card", style: { background: "var(--paper)" } },
        h("p", { class: "small muted" }, "Why it was delayed"),
        h("h3", { style: { fontSize: "16px", margin: "2px 0 6px" } }, c.pend.theme_name),
        h("p", { class: "small" }, `Pended in ${c.pend.stage_name} for ${fmt.one(c.pend.pend_days)} days${c.pend.still_pended ? " and still waiting" : ""}. Pend code ${c.pend.pend_code}, ${c.pend.touches} manual touch${c.pend.touches === 1 ? "" : "es"}.`),
        h("blockquote", { style: { margin: "10px 0 8px", padding: "8px 10px", background: "#fff", borderRadius: "6px", fontStyle: "italic", fontSize: "13px" } }, c.pend.note),
        h("p", { class: "small muted" }, `Theme assigned with ${fmt.pct(c.pend.confidence)} confidence.`)),
      c.denial && h("p", { class: "note" }, `Denied with reason code ${c.denial.code}: ${c.denial.text ?? ""}`),
      h("div", {}, h("p", { class: "small muted", style: { marginBottom: "10px" } }, "Timeline"),
        h("ol", { class: "timeline" }, c.timeline.map((e) => h("li", { class: e.event.startsWith("Pend") ? "pend" : "" },
          h("time", {}, e.at), h("strong", {}, e.event), h("span", { class: "muted" }, `  ${e.stage}`))))),
      h("div", {}, h("p", { class: "small muted", style: { marginBottom: "8px" } }, "Days in each stage"),
        h("div", { class: "kv" }, c.stage_days.map((s) => h("div", {}, h("span", {}, s.stage), h("strong", { class: "num" }, s.days === null ? "Not reached" : `${s.days} days`))))),
      h("div", { class: "kv" },
        ...[["Line of business", c.lob], ["Platform", c.platform], ["Submitted by", c.channel], ["Claim type", c.claim_type],
          ["Provider", `${c.provider_id} (${c.specialty})`], ["Network", c.network_status], ["Billed amount", `$${fmt.int(c.billed_amount)}`]]
          .map(([k, v]) => h("div", {}, h("span", {}, k), h("strong", {}, v)))),
    ].filter(Boolean));
    close.focus();
  } catch (error) {
    drawer.replaceChildren(failure(error));
  }
}

export const claimsView = {
  id: "claims", label: "Claims", title: "The delayed claims behind the numbers",
  lede: "Every pended claim, longest wait first. Search the adjuster notes, filter by theme, and open any claim to see its timeline.",
  icon: '<path d="M3 4h10M3 8h10M3 12h10"/>',
  async render({ filters, state }) {
    const query = { theme: state.params.theme ?? "", status: "", q: "", over_target: false, page: 1, size: 25 };
    const body = h("div");
    const load = async () => {
      body.replaceChildren(loading());
      try {
        const data = await api.claims(filters, query);
        const pages = Math.max(1, Math.ceil(data.total / data.size));
        body.replaceChildren(
          data.rows.length ? h("div", { class: "table-wrap" }, h("table", {},
            h("thead", {}, h("tr", {}, ["Claim", "Received", "Delay theme", "Stage", "Status", "Platform", "Specialty"].map((c) => h("th", {}, c)),
              h("th", { class: "r" }, "Days pended"), h("th", { class: "r" }, "Billed"))),
            h("tbody", {}, data.rows.map((r) => h("tr", { class: "clickable", tabindex: "0", onclick: () => openClaim(r.claim_id),
              onkeydown: (e) => { if (e.key === "Enter") openClaim(r.claim_id); } },
              h("td", { style: { whiteSpace: "nowrap" } }, r.claim_id), h("td", { style: { whiteSpace: "nowrap" } }, fmt.date(r.received_date)),
              h("td", { style: { minWidth: "200px" } }, r.theme_name), h("td", { style: { whiteSpace: "nowrap" } }, r.stage_name),
              h("td", { style: { whiteSpace: "nowrap" } }, r.status), h("td", {}, r.platform), h("td", {}, r.specialty),
              h("td", { class: "r" }, fmt.one(r.pend_days)), h("td", { class: "r" }, `$${fmt.int(r.billed_amount)}`))))))
            : h("div", { class: "empty" }, "No claims match. Clear the search or choose a different theme."),
          h("div", { class: "pager" },
            h("span", { class: "num" }, `${fmt.int(data.total)} claims, page ${data.page} of ${pages}`),
            h("div", { style: { display: "flex", gap: "8px" } },
              h("button", { class: "btn ghost", type: "button", disabled: data.page <= 1, onclick: () => { query.page -= 1; load(); } }, "Previous"),
              h("button", { class: "btn ghost", type: "button", disabled: data.page >= pages, onclick: () => { query.page += 1; load(); } }, "Next"))));
      } catch (error) { body.replaceChildren(failure(error)); }
    };
    const set = (key) => (e) => { query[key] = e.target.type === "checkbox" ? e.target.checked : e.target.value; query.page = 1; load(); };
    let timer;
    const toolbar = h("div", { class: "toolbar" },
      h("label", { class: "field grow" }, "Search claim ID, provider or note text",
        h("input", { type: "search", placeholder: "For example: roster, fax, C2610048488", oninput: (e) => { clearTimeout(timer); timer = setTimeout(() => set("q")(e), 250); } })),
      h("label", { class: "field" }, "Delay theme", h("select", { onchange: set("theme") }, h("option", { value: "" }, "All themes"),
        state.meta.themes.map((t) => h("option", { value: t.key, selected: t.key === query.theme }, t.name)))),
      h("label", { class: "field" }, "Status", h("select", { onchange: set("status") }, h("option", { value: "" }, "Any status"),
        state.meta.statuses.map((s) => h("option", { value: s }, s)))),
      h("label", { class: "check" }, h("input", { type: "checkbox", onchange: set("over_target") }), `Over the ${state.meta.target_days}-day target`));
    load();
    return h("section", { class: "card" }, toolbar, body);
  },
};
