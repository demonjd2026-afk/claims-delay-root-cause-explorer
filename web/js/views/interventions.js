import { bars, card, fmt, h, stageColor } from "../ui.js";

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

function businessCase(plan) {
  const chosen = new Set(plan.rows.slice(0, 3).map((r) => r.key));
  const inputs = { cost: 8, realised: 70, volume: plan.claims_per_year_at_this_rate };
  const out = h("div", { class: "case-out", "aria-live": "polite" });

  const recompute = () => {
    const rows = plan.rows.filter((r) => chosen.has(r.key));
    const scale = (inputs.realised / 100) * (inputs.volume / plan.claims_in_window);
    const touches = rows.reduce((a, r) => a + r.recoverable_touches, 0) * scale;
    const days = rows.reduce((a, r) => a + r.recoverable_days, 0) * scale;
    const claims = rows.reduce((a, r) => a + r.recoverable_claims, 0) * scale;
    out.replaceChildren(
      h("div", {}, h("div", { class: "l" }, "Manual work avoided, per year"), h("div", { class: "v num" }, money.format(touches * inputs.cost))),
      h("div", { class: "row" },
        h("div", {}, h("div", { class: "l" }, "Manual touches avoided"), h("div", { class: "v num" }, fmt.int(touches))),
        h("div", {}, h("div", { class: "l" }, "Claims no longer delayed"), h("div", { class: "v num" }, fmt.int(claims)))),
      h("div", {}, h("div", { class: "l" }, "Days of delay removed, per year"), h("div", { class: "v num" }, fmt.int(days))),
      h("p", {}, `${rows.length} of ${plan.rows.length} interventions selected. Rates measured on the ${fmt.int(plan.claims_in_window)} claims in view, applied to ${fmt.int(inputs.volume)} claims a year. Covers manual handling cost only; late-payment interest, provider calls and appeals are not included.`));
  };

  const slider = (key, label, min, max, step, show) => {
    const value = h("strong", { class: "num" }, show(inputs[key]));
    return h("div", { class: "slider" },
      h("label", { for: `case-${key}` }, h("span", {}, label), value),
      h("input", { id: `case-${key}`, type: "range", min, max, step, value: inputs[key],
        oninput: (e) => { inputs[key] = Number(e.target.value); value.textContent = show(inputs[key]); recompute(); } }));
  };
  recompute();

  return card("Business case", "Set your claim volume, adjust the two assumptions and choose which interventions to fund. The result updates as you change them.",
    h("div", { class: "case" },
      h("div", { class: "case-inputs" },
        h("label", { class: "field", style: { fontSize: "13.5px", color: "var(--text)" } }, "Claims received per year",
          h("input", { type: "number", min: "1000", step: "1000", value: inputs.volume, style: { maxWidth: "220px" },
            oninput: (e) => { inputs.volume = Math.max(0, Number(e.target.value) || 0); recompute(); } }),
          h("span", { class: "small muted" }, `Starts at the pace of the data in view. Enter your own annual volume to scale the result.`)),
        slider("cost", "Cost of one manual touch", 2, 30, 0.5, (v) => `$${v.toFixed(2)}`),
        slider("realised", "Share of the benefit actually achieved", 20, 100, 5, (v) => `${v}%`),
        h("div", {}, h("p", { class: "small muted", style: { marginBottom: "6px" } }, "Interventions to fund"),
          h("div", { class: "checks" }, plan.rows.map((r) => h("label", {},
            h("input", { type: "checkbox", checked: chosen.has(r.key), onchange: (e) => { e.target.checked ? chosen.add(r.key) : chosen.delete(r.key); recompute(); } }),
            h("span", {}, `${r.rank}. ${r.name}`), h("span", { class: "muted num" }, `${fmt.int(r.recoverable_days)} days`))))),
        h("p", { class: "note" }, "The cost per touch is a placeholder. Replace it with Finance's loaded cost for a claims processor touch before using this figure.")),
      out));
}

export const interventionsView = {
  id: "act", label: "Where to act", title: "Where to intervene first",
  lede: "Themes ranked by the delay days that could be removed for the effort involved, with the recommended action, the owner and a business case you can adjust.",
  icon: '<path d="M8 2v12M8 2 4.5 5.5M8 2l3.5 3.5"/>',
  async render({ api, filters, go }) {
    const plan = await api.interventions(filters);
    const top = plan.rows.slice(0, 5);
    return [
      card("Top five interventions", "Priority is removable days divided by effort. Select a theme name to see its root causes.",
        h("div", {}, top.map((r) => h("div", { class: "rank" },
          h("div", { class: "no" }, r.rank),
          h("div", {},
            h("h3", {}, h("a", { href: `#causes/${r.key}`, style: { color: "inherit" } }, r.name)),
            h("p", {}, r.intervention),
            h("p", { class: "muted", style: { fontSize: "13px" } }, `Why it happens: ${r.why}`),
            h("div", { class: "facts" },
              h("span", { class: "tag" }, `${fmt.int(r.claims)} claims, ${fmt.one(r.avg_pend_days)} days each`),
              h("span", { class: "tag" }, `${fmt.int(r.recoverable_days)} of ${fmt.int(r.pend_days)} days removable`),
              h("span", { class: "tag" }, `Owner: ${r.owner}`),
              h("span", { class: "tag assume" }, `Assumed ${fmt.pct(r.addressability)} addressable, ${r.effort.toLowerCase()} effort`))))))),
      card("Days lost and days removable, every theme",
        "The pale bar is all days lost to the theme. The solid bar is the part the recommended action could remove.",
        bars(plan.rows.map((r) => ({
          name: `${r.rank}. ${r.name}`, value: r.recoverable_days, under: r.pend_days, color: stageColor(r.stage),
          text: fmt.int(r.recoverable_days), sub: `of ${fmt.int(r.pend_days)}`,
          title: `${r.effort} effort, ${fmt.pct(r.addressability)} assumed addressable`, onClick: () => go("causes", { theme: r.key }),
        }))),
        h("p", { class: "note", style: { marginTop: "14px" } }, "How much of a theme is addressable and how much effort the fix takes are planning assumptions set in the playbook, not measurements. Days lost, claims and touches are measured from the claims data.")),
      businessCase(plan),
    ];
  },
};
