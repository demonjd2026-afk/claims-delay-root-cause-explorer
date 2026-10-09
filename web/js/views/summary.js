import { bars, card, cardWith, dailyChart, fmt, h, kpi, segmented, stageColor, stageLegend } from "../ui.js";

function findings(items, go) {
  return h("div", { class: "grid cols-4" }, items.map((f) => h("article", { class: `card finding ${f.kind}` },
    f.kind === "emerging" && h("span", { class: "tag alert", style: { alignSelf: "flex-start" } }, "Rising now"),
    h("h3", {}, f.title), h("p", {}, f.text),
    f.theme && h("button", { type: "button", onclick: () => go("causes", { theme: f.theme }) }, "See the root causes"))));
}

function rail(stages) {
  return h("div", { class: "rail" }, stages.map((s, i) => h("div", { class: "rail-stage" },
    h("div", { class: "step" }, `Stage ${i + 1} of 4`),
    h("h3", {}, h("i", { style: { background: stageColor(s.key) } }), s.name),
    h("div", { class: "big num" }, fmt.pct(s.pend_days_share)),
    h("div", { class: "cap" }, "of all days lost"),
    h("div", { class: "rail-meter" }, h("b", { style: { width: `${(s.pend_days_share ?? 0) * 100}%`, background: stageColor(s.key) } })),
    h("div", { class: "cap num", style: { marginTop: "8px" } }, `${fmt.int(s.pended)} claims pended here`))));
}

function themeBars(themes, metric, go) {
  const spec = metric === "pend_days"
    ? { value: (t) => t.pend_days, text: (t) => fmt.int(t.pend_days), sub: (t) => fmt.pct(t.pend_days_share) }
    : { value: (t) => t.claims, text: (t) => fmt.int(t.claims), sub: (t) => fmt.pct(t.claims_share) };
  return bars([...themes].sort((a, b) => spec.value(b) - spec.value(a)).map((t) => ({
    name: t.name, value: spec.value(t), text: spec.text(t), sub: spec.sub(t), color: stageColor(t.stage),
    title: `${t.name}: ${fmt.int(t.claims)} claims, ${t.avg_pend_days} days pended on average, ${fmt.int(t.pend_days)} days lost`,
    onClick: () => go("causes", { theme: t.key }),
  })));
}

export const summaryView = {
  id: "summary", label: "Summary", title: "Why claims are delayed, and where to act first",
  lede: "A claim is delayed when it cannot be processed automatically and is pended for a person to work. This page shows how often that happens, what causes it and what it costs in days.",
  icon: '<rect x="2" y="2" width="5" height="5" rx="1"/><rect x="9" y="2" width="5" height="5" rx="1"/><rect x="2" y="9" width="5" height="5" rx="1"/><rect x="9" y="9" width="5" height="5" rx="1"/>',
  async render({ api, filters, go, state }) {
    const o = await api.overview(filters);
    const k = o.kpis;
    const bySlot = h("div");
    const draw = (metric) => bySlot.replaceChildren(themeBars(o.themes, metric, go));
    draw("pend_days");

    return [
      findings(o.findings, go),
      h("div", { class: "grid cols-6" },
        kpi("Claims received", fmt.int(k.claims), `${fmt.pct(k.first_pass_rate, 1)} went straight through`),
        kpi("Pended for manual work", fmt.int(k.pended), `${fmt.pct(k.pended_rate, 1)} of claims received`),
        kpi("Time to finish a pended claim", fmt.one(k.avg_days_pended), `against ${fmt.one(k.avg_days_clean)} days when not pended`, "days"),
        kpi("Days lost to pends", fmt.int(k.pend_days_total), `${fmt.int(k.manual_touches)} manual touches`),
        kpi(`Over the ${k.target_days}-day target`, fmt.int(k.over_target), `${fmt.pct(k.over_target_pended_share)} of them were pended`),
        kpi("Pended and still open", fmt.int(k.open_pended), `${fmt.money(k.open_pended_billed)} billed, waiting`)),
      card("Where in the process the time is lost",
        "Every claim passes through four stages. The share shown is each stage's part of the total days claims spent pended.",
        rail(o.stages)),
      card("Claims pended, each day",
        "One bar per calendar day, by the date the claim was received. Weekends are lower because fewer claims arrive.",
        dailyChart(o.daily.dates, [{ label: "Pended", data: o.daily.pended, color: "#1c5cab" }], { height: 200 }),
        h("p", { class: "small muted", style: { margin: "14px 0 6px" } }, "Claims received, each day"),
        dailyChart(o.daily.dates, [{ label: "Received", data: o.daily.received, color: "#aab4c1" }], { height: 110 })),
      h("div", { class: "grid cols-2" },
        cardWith("Delay themes",
          "Each pended claim is assigned a theme from its adjuster note and pend code. Colour shows the stage. Select a theme to see its root causes.",
          segmented([["pend_days", "Days lost"], ["claims", "Claims"]], "pend_days", draw),
          bySlot, h("div", { style: { marginTop: "14px" } }, stageLegend(state.meta.stages))),
        card("Where to intervene first", "Ranked by delay days that could be removed for the effort involved.",
          h("div", {}, o.interventions.map((r) => h("div", { class: "rank" },
            h("div", { class: "no" }, r.rank),
            h("div", {},
              h("h3", {}, r.name), h("p", {}, r.intervention),
              h("div", { class: "facts" },
                h("span", { class: "tag" }, `${fmt.int(r.recoverable_days)} days removable`),
                h("span", { class: "tag" }, `${r.effort} effort`), h("span", { class: "tag" }, r.owner)))))),
          h("button", { class: "btn ghost", type: "button", style: { marginTop: "16px" }, onclick: () => go("act") }, "See the full plan and business case"))),
    ];
  },
};
