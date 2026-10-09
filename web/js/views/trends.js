import { card, cardWith, dailyChart, fmt, h, stageColor, stageLegend } from "../ui.js";

function emergingCards(t, go) {
  const items = t.emerging;
  if (!t.emerging_checked) {
    return h("p", { class: "note" }, `Rising themes are checked when at least ${t.emerging_needs_days} days are in view: the latest 21 are compared with the 42 before. Widen the date range to see them.`);
  }
  if (!items.length) {
    return h("p", { class: "note" }, "No theme is rising: the latest 21 days were compared with the 42 days before and nothing stood out.");
  }
  return h("div", { class: items.length > 1 ? "grid cols-2" : "grid" }, items.map((e) => h("article", { class: "card finding emerging" },
    h("span", { class: "tag alert", style: { alignSelf: "flex-start" } }, `Up ${e.lift}x`),
    h("h3", {}, `${e.name} is rising`),
    h("p", {}, `From ${e.per_day_before} to ${e.per_day_now} pended claims a day${e.onset ? `, starting around ${fmt.date(e.onset)}` : ""}. That is about ${fmt.int(e.extra_claims)} extra pended claims between ${fmt.date(e.recent_window[0])} and ${fmt.date(e.recent_window[1])}.`),
    h("p", {}, `${e.driver.share_text} of the rise comes from ${e.driver.dimension.toLowerCase()} ${e.driver.value} (${e.driver.per_day_before} to ${e.driver.per_day_now} a day).`),
    h("button", { type: "button", onclick: () => go("causes", { theme: e.key }) }, "See the root causes"))));
}

function heatTable(hot) {
  const max = Math.max(...hot.rows.flatMap((r) => r.per_1000.map((v) => v ?? 0)), 1e-9);
  // Sequential single-hue ramp, light to dark.
  const ramp = ["#f3f7fd", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#1c5cab", "#104281"];
  const cell = (v) => {
    const step = Math.min(ramp.length - 1, Math.floor(((v ?? 0) / max) * (ramp.length - 0.001)));
    return { background: ramp[step], color: step >= 4 ? "#fff" : "#17212e" };
  };
  return h("div", { class: "table-wrap" }, h("table", {},
    h("thead", {}, h("tr", {}, h("th", {}, "Theme"), hot.columns.map((c) => h("th", { class: "r" }, c)))),
    h("tbody", {}, hot.rows.map((r) => h("tr", {}, h("td", {}, r.name),
      r.per_1000.map((v, i) => h("td", { class: "heat", style: cell(v), title: `${fmt.int(r.claims[i])} pended of ${fmt.int(hot.received[i])} received` }, fmt.one(v))))))));
}

export const trendsView = {
  id: "trends", label: "Daily trends", title: "How delays change day by day",
  lede: "Every chart shows one bar per calendar day. Rising themes are flagged automatically, with the date they started and the segment driving them.",
  icon: '<path d="M2 13V3M2 13h12"/><path d="M5 11V8M8 11V5M11 11V7"/>',
  async render({ api, filters, go, state }) {
    const [t, firstHot] = await Promise.all([api.trends(filters), api.hotspots(filters, "platform")]);
    const onset = Object.fromEntries(t.emerging.filter((e) => e.onset).map((e) => [e.key, e.onset]));
    const hotSlot = h("div", {}, heatTable(firstHot));
    const select = h("select", { "aria-label": "Compare by", onchange: async (e) => hotSlot.replaceChildren(heatTable(await api.hotspots(filters, e.target.value))) },
      Object.entries(state.meta.segment_dimensions).map(([key, label]) => h("option", { value: key }, label)));

    return [
      emergingCards(t, go),
      card("Claims pended each day, by stage", "By the date the claim was received. Hover a day for the exact counts.",
        dailyChart(t.dates, t.by_stage.map((s) => ({ label: s.name, data: s.pended, color: stageColor(s.key) })), { height: 260 }),
        h("div", { style: { marginTop: "12px" } }, stageLegend(state.meta.stages))),
      card("Each theme, day by day", "Every theme on its own scale so small themes stay readable. A red line marks the day a rise began.",
        h("div", { class: "minis" }, t.by_theme.map((s) => h("div", {
          class: "mini", role: "button", tabindex: "0", onclick: () => go("causes", { theme: s.key }),
          onkeydown: (e) => { if (e.key === "Enter") go("causes", { theme: s.key }); },
        },
          h("h4", { title: s.name }, s.name),
          h("div", { class: "meta" }, h("span", {}, `${fmt.int(s.claims)} claims`), onset[s.key] && h("span", { class: "tag alert" }, "Rising")),
          dailyChart(t.dates, [{ label: "Pended", data: s.pended, color: stageColor(s.stage) }],
            { height: 96, compact: true, marker: onset[s.key] && { date: onset[s.key], label: fmt.date(onset[s.key]) } }))))),
      cardWith("Hotspots", "Pended claims per 1,000 received. Darker cells are where a theme hits hardest.", select, hotSlot),
    ];
  },
};
