import { card, fmt, h, stackedRows, stageColor, stageLegend } from "../ui.js";

export const journeyView = {
  id: "journey", label: "Claim journey", title: "Where claims get stuck on their way to payment",
  lede: "Intake, Pre-Adjudication, Adjudication and Post-Adjudication. For each stage: what it does, how many claims pend there and which themes are responsible.",
  icon: '<circle cx="3" cy="8" r="1.6"/><circle cx="8" cy="8" r="1.6"/><circle cx="13" cy="8" r="1.6"/><path d="M4.6 8h1.8M9.6 8h1.8"/>',
  async render({ api, filters, go, state }) {
    const j = await api.journey(filters);
    const stages = j.stages;
    const cleanTotal = stages.reduce((a, s) => a + (s.avg_days_clean ?? 0), 0);
    const pendedTotal = stages.reduce((a, s) => a + (s.avg_days_all_pended ?? 0), 0);

    return [
      card("Time spent in each stage",
        `A claim that goes straight through takes ${fmt.one(cleanTotal)} days from receipt to payment. A pended claim takes ${fmt.one(pendedTotal)}. The difference is waiting time, not processing time.`,
        stackedRows(["Straight-through claim", "Pended claim"],
          stages.map((s) => ({ label: s.name, color: stageColor(s.key), data: [s.avg_days_clean, s.avg_days_all_pended] }))),
        h("div", { style: { marginTop: "10px" } }, stageLegend(state.meta.stages))),
      h("div", { class: "grid cols-4" }, stages.map((s, i) => h("section", { class: "card", style: { borderTop: `4px solid ${stageColor(s.key)}` } },
        h("p", { class: "small muted" }, `Stage ${i + 1} of 4`),
        h("h2", { style: { fontSize: "17px", fontWeight: "650" } }, s.name),
        h("p", { class: "small muted", style: { margin: "4px 0 14px", minHeight: "76px" } }, s.does),
        h("div", { class: "kv" },
          h("div", {}, h("span", {}, "Claims pended here"), h("strong", { class: "num" }, fmt.int(s.pended))),
          h("div", {}, h("span", {}, "Days lost"), h("strong", { class: "num" }, `${fmt.int(s.pend_days)} (${fmt.pct(s.pend_days_share)})`)),
          h("div", {}, h("span", {}, "Normal time here"), h("strong", { class: "num" }, `${s.avg_days_clean} days`)),
          h("div", {}, h("span", {}, "When pended here"), h("strong", { class: "num" }, `${s.avg_days_when_pended_here ?? "n/a"} days`))),
        h("p", { class: "small muted", style: { margin: "16px 0 8px" } }, "Themes at this stage, by days lost"),
        s.themes.length ? h("div", { class: "bars" }, s.themes.map((t) => h("div", {
          class: "clickable", style: { cursor: "pointer", display: "grid", gap: "3px" }, role: "button", tabindex: "0",
          title: `${fmt.int(t.claims)} claims, ${t.avg_pend_days} days each`,
          onclick: () => go("causes", { theme: t.key }),
          onkeydown: (e) => { if (e.key === "Enter") go("causes", { theme: t.key }); },
        },
          h("div", { style: { display: "flex", justifyContent: "space-between", gap: "8px", fontSize: "13px" } },
            h("span", {}, t.name), h("span", { class: "num muted" }, fmt.int(t.pend_days))),
          h("div", { class: "bar-track", style: { height: "8px" } },
            h("div", { class: "bar-fill", style: { background: stageColor(s.key), width: `${(t.pend_days / Math.max(...stages.flatMap((x) => x.themes.map((y) => y.pend_days)))) * 100}%` } })))))
          : h("p", { class: "small muted" }, "No pended claims at this stage.")))),
      card("Intake: how the claim arrives decides how fast it starts",
        "Intake delay is not only pends. Paper claims are scanned and keyed before anything else can happen, so they start later even when nothing is wrong, and they are stopped at intake more often.",
        h("div", { class: "table-wrap" }, h("table", {},
          h("thead", {}, h("tr", {}, h("th", {}, "How the claim was submitted"), h("th", { class: "r" }, "Claims"),
            h("th", { class: "r" }, "Time in intake when not pended"), h("th", { class: "r" }, "Stopped at intake, per 1,000"))),
          h("tbody", {}, j.intake_by_channel.map((c) => h("tr", {}, h("td", {}, c.channel), h("td", { class: "r" }, fmt.int(c.claims)),
            h("td", { class: "r" }, c.avg_intake_days_clean < 0.2 ? `${fmt.one(c.avg_intake_days_clean * 24)} hours` : `${c.avg_intake_days_clean.toFixed(1)} days`),
            h("td", { class: "r" }, fmt.one(c.intake_pends_per_1000)))))))),
      j.unattributed && h("p", { class: "note" },
        `${fmt.int(j.unattributed.claims)} pended claims (${fmt.pct(j.unattributed.claims_share)}) had notes too vague to assign a theme with confidence. They are counted at the stage where they pended and listed under "Needs human review" in Root causes.`),
    ];
  },
};
