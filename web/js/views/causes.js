import { bars, card, cardWith, dailyChart, fmt, h, kpi, stageChip, stageColor } from "../ui.js";
import { openClaim } from "./claims.js";

function segmentBars(segment, color) {
  return bars(segment.rows.slice(0, 10).map((r) => ({
    name: r.value, value: r.per_1000, color, text: fmt.one(r.per_1000), sub: `${r.index}x`,
    title: `${fmt.int(r.pended)} of ${fmt.int(r.claims_received)} claims received`,
  })));
}

function detail(d, go) {
  const color = stageColor(d.stage);
  const segSlot = h("div");
  const select = h("select", { "aria-label": "Break down by", onchange: (e) => segSlot.replaceChildren(segmentBars(d.segments[e.target.value], color)) },
    Object.entries(d.segments).map(([key, s]) => h("option", { value: key }, s.label)));
  segSlot.replaceChildren(segmentBars(d.segments.platform, color));

  return h("div", { class: "grid" },
    h("section", { class: "card" },
      h("div", { class: "card-head" },
        h("div", {}, h("h2", { style: { fontSize: "19px" } }, d.name), h("p", { class: "sub" }, d.playbook.stage_does)),
        stageChip(d.stage, d.stage_name ? `Pends in ${d.stage_name}` : null)),
      h("div", { class: "explain" },
        h("div", {}, h("h4", {}, "What it is"), h("p", {}, d.playbook.plain)),
        h("div", {}, h("h4", {}, "Why it happens"), h("p", {}, d.playbook.why)),
        h("div", {}, h("h4", {}, `What to do (${d.playbook.owner})`), h("p", {}, d.playbook.intervention)))),
    h("div", { class: "grid cols-4" },
      kpi("Claims pended", fmt.int(d.claims), `${fmt.pct(d.claims_share)} of all pended claims`),
      kpi("Average wait", fmt.one(d.avg_pend_days), `half clear within ${fmt.one(d.median_pend_days)} days`, "days"),
      kpi("Days lost", fmt.int(d.pend_days), `${fmt.pct(d.pend_days_share)} of all days lost`),
      kpi("Still open", fmt.int(d.open), `${fmt.int(d.over_target)} over target, ${fmt.money(d.billed)} billed`)),
    card("Root causes found in the adjuster notes",
      "Notes that say the same thing are grouped automatically. Each group is described by its most distinctive phrases and one typical note.",
      d.clusters.length ? h("div", { class: `grid cols-${d.clusters.length === 3 ? 3 : 2}` }, d.clusters.map((c) => h("div", { class: "cluster" },
        h("div", { class: "head" }, h("span", { class: "share num" }, fmt.pct(c.share)),
          h("span", { class: "small muted num" }, `${fmt.int(c.claims)} claims, ${fmt.one(c.avg_pend_days)} days each`)),
        h("div", { class: "chips" }, c.key_phrases.map((p) => h("span", { class: "tag" }, p))),
        h("blockquote", {}, c.example_note))))
        : h("p", { class: "muted" }, "These notes carry no specific reason, so there is nothing to group.")),
    card("Claims pended for this reason, each day", "By the date the claim was received.",
      dailyChart(d.daily.dates, [{ label: d.name, data: d.daily.pended, color }], { height: 190 })),
    h("div", { class: "grid cols-2" },
      cardWith("Who is most affected", "Pended claims per 1,000 received. The multiple compares each group with the average.", select, segSlot),
      card("Providers with the most pended claims", "Top five for this theme.",
        h("div", { class: "table-wrap" }, h("table", {},
          h("thead", {}, h("tr", {}, h("th", {}, "Provider"), h("th", {}, "Specialty"), h("th", { class: "r" }, "Claims"))),
          h("tbody", {}, d.top_providers.map((p) => h("tr", {}, h("td", {}, p.provider_id), h("td", {}, p.specialty), h("td", { class: "r" }, fmt.int(p.claims))))))))),
    card("Longest-waiting examples", "Select a claim to see its full timeline.",
      h("div", { class: "table-wrap" }, h("table", {},
        h("thead", {}, h("tr", {}, h("th", {}, "Claim"), h("th", {}, "Adjuster note"), h("th", {}, "Pend code"), h("th", { class: "r" }, "Days pended"))),
        h("tbody", {}, d.sample_notes.map((n) => h("tr", { class: "clickable", tabindex: "0", onclick: () => openClaim(n.claim_id),
          onkeydown: (e) => { if (e.key === "Enter") openClaim(n.claim_id); } },
          h("td", { style: { whiteSpace: "nowrap" } }, n.claim_id), h("td", {}, n.adjuster_note), h("td", {}, n.pend_code), h("td", { class: "r" }, fmt.one(n.pend_days)))))))));
}

export const causesView = {
  id: "causes", label: "Root causes", title: "What is behind each delay theme",
  lede: "Pick a theme to see why it happens, the specific situations inside it, who it affects most and what to do about it.",
  icon: '<circle cx="7" cy="7" r="4.2"/><path d="M10.2 10.2 14 14"/>',
  async render({ api, filters, go, state }) {
    const overview = await api.overview(filters);
    const themes = [...overview.themes].sort((a, b) => b.pend_days - a.pend_days);
    const selected = themes.find((t) => t.key === state.params.theme) ?? themes[0];
    const d = await api.theme(selected.key, filters);
    return h("div", { class: "grid split" },
      h("nav", { class: "card", style: { padding: "0", position: "sticky", top: "110px" }, "aria-label": "Delay themes" },
        h("p", { class: "small muted", style: { padding: "14px 20px 0" } }, "Themes, by days lost"),
        h("div", { class: "theme-list" }, themes.map((t) => h("button", {
          type: "button", "aria-pressed": String(t.key === selected.key), onclick: () => go("causes", { theme: t.key }),
        }, h("i", { style: { background: stageColor(t.stage) } }), h("span", {}, t.name), h("span", { class: "n" }, fmt.int(t.pend_days)))))),
      detail(d, go));
  },
};
