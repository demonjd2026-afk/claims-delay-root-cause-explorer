import { card, fmt, h, kpi } from "../ui.js";

const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

const STEPS = [
  ["Claims data", "Claim records, status timestamps for each stage, pend and denial codes, and adjuster notes."],
  ["Classify", "A model reads each note and pend code and assigns one delay theme. Unsure cases go to a person."],
  ["Cluster", "Within each theme, notes that say the same thing are grouped to expose the specific root causes."],
  ["Measure", "Days lost, daily trends, rising themes and segment hotspots are computed from the claim rows."],
  ["Decide", "The dashboard ranks interventions, and the analyst answers questions from the same figures."],
];

export const methodView = {
  id: "method", label: "How it works", title: "How the explorer works, and how far to trust it",
  lede: "What the data is, how themes and root causes are found, how accurate the model is and which numbers are assumptions.",
  usesFilters: false,
  icon: '<circle cx="8" cy="8" r="6"/><path d="M8 7.2v4M8 4.8v.2"/>',
  async render({ api, state, reloadData, rerender }) {
    const m = await api.model();
    const w = state.meta.window;
    const c = m.classifier;
    const from = h("input", { type: "date", value: w.start, "aria-label": "First receipt date" });
    const to = h("input", { type: "date", value: w.end, "aria-label": "Last receipt date" });
    const status = h("p", { class: "status", "aria-live": "polite" });
    const button = h("button", { class: "btn", type: "submit" }, "Generate data");
    const setRange = (days) => {
      const end = new Date(`${to.value || w.end}T00:00:00`);
      const start = new Date(end); start.setDate(end.getDate() - (days - 1));
      from.value = iso(start); to.value = iso(end);
    };
    const generate = async (event) => {
      event.preventDefault();
      if (!from.value || !to.value) return;
      button.disabled = true; status.className = "status";
      status.textContent = "Generating claims, classifying themes and clustering root causes. A quarter takes about 10 seconds, a year about 30.";
      try {
        const r = await api.rebuild({ date_from: from.value, date_to: to.value });
        await reloadData();
        status.textContent = `Done in ${r.build_seconds} seconds: ${fmt.int(r.claims)} claims, ${fmt.int(r.pended)} pended. Every tab now shows ${fmt.dateFull(r.start)} to ${fmt.dateFull(r.end)}.`;
        setTimeout(rerender, 2500);
      } catch (error) {
        status.className = "status bad"; status.textContent = error.message; button.disabled = false;
      }
    };

    return [
      card("Data period", `Showing synthetic claims received ${fmt.dateFull(w.start)} to ${fmt.dateFull(w.end)}. To look at a different period, generate a fresh data set for it here: one set of claims for every calendar day in the range. Choose between ${w.min_days} and ${w.max_days} days.`,
        h("form", { class: "period", onsubmit: generate },
          h("label", { class: "field" }, "First receipt date", from),
          h("label", { class: "field" }, "Last receipt date", to),
          button,
          h("div", { class: "quick" }, [[90, "Last 90 days"], [180, "Last 180 days"], [365, "Last 365 days"]].map(([days, label]) =>
            h("button", { class: "btn ghost", type: "button", onclick: () => setRange(days) }, label))),
          status),
        h("p", { class: "note", style: { marginTop: "6px" } }, "To narrow the view inside the current period, use the From and To filters at the top of the other tabs; that needs no rebuild.")),
      card("From raw claims to a decision", "Five steps, run once when the data is built.",
        h("div", { class: "flow" }, STEPS.map(([name, text], i) => h("div", {}, h("span", { class: "step" }, `Step ${i + 1}`), h("h4", {}, name), h("p", {}, text))))),
      h("div", { class: "grid cols-4" },
        kpi("Classifier accuracy", fmt.pct(c.holdout_accuracy, 1), `on ${fmt.int(c.test_size)} labelled claims it had not seen`),
        kpi("Assigned automatically", fmt.pct(c.auto_classified_share, 1), `${fmt.pct(c.needs_review_share, 1)} sent to human review`),
        kpi("Visible from pend codes alone", fmt.pct(c.code_only_correct_share), `${fmt.pct(c.generic_code_share)} of pends carry a generic code`),
        kpi("Labelled examples needed", fmt.int(c.labelled_seed), `out of ${fmt.int(c.pended_claims)} pended claims`)),
      h("div", { class: "grid cols-2" },
        card("Accuracy for each theme", "Precision: when the model names this theme, how often it is right. Recall: how many of this theme's claims it finds. Measured on held-out labelled claims.",
          h("div", { class: "table-wrap" }, h("table", {},
            h("thead", {}, h("tr", {}, h("th", {}, "Theme"), h("th", { class: "r" }, "Precision"), h("th", { class: "r" }, "Recall"), h("th", { class: "r" }, "Test claims"))),
            h("tbody", {}, c.per_theme.map((r) => h("tr", {}, h("td", {}, r.name), h("td", { class: "r" }, fmt.pct(r.precision)), h("td", { class: "r" }, fmt.pct(r.recall)), h("td", { class: "r" }, r.support))))))),
        card("Root-cause grouping quality", "Agreement between the automatic groups and the sub-causes built into the synthetic data. 1.00 is a perfect match. This check is only possible because the data is synthetic.",
          h("div", { class: "table-wrap" }, h("table", {},
            h("thead", {}, h("tr", {}, h("th", {}, "Theme"), h("th", { class: "r" }, "Groups found"), h("th", { class: "r" }, "Sub-causes built in"), h("th", { class: "r" }, "Agreement"))),
            h("tbody", {}, m.clustering.map((r) => h("tr", {}, h("td", {}, r.name), h("td", { class: "r" }, r.clusters), h("td", { class: "r" }, r.planted_sub_causes), h("td", { class: "r" }, r.adjusted_rand_index.toFixed(2))))))))),
      card("What is measured and what is assumed", null,
        h("ul", { class: "plain-list" },
          h("li", {}, h("strong", {}, "The data is synthetic. "), "It was generated for this demonstration and contains no real member, provider or claim information. Results show what the tool can do, not how any real operation performs."),
          h("li", {}, h("strong", {}, "Measured from claim rows: "), "claim counts, days pended, days lost, manual touches, daily trends, rising themes and segment rates."),
          h("li", {}, h("strong", {}, "Assumed in the playbook: "), "how much of each theme an intervention can remove, how much effort it takes, and the cost of a manual touch in the business case."),
          h("li", {}, h("strong", {}, "Accuracy will be lower on real notes. "), "Synthetic notes are cleaner and more consistent than real ones. Expect to label a sample of real claims and re-measure before relying on the themes."),
          h("li", {}, h("strong", {}, "Pend and denial codes: "), "pend codes are invented for the demo. Denial codes are standard claim adjustment reason codes."),
          h("li", {}, h("strong", {}, "The analyst: "), m.analyst.mode === "llm"
            ? `a language model (${m.analyst.model}) chooses which figures to look up and writes the answer. It is instructed to quote only what it looked up.`
            : "running in built-in mode. It matches your question to a lookup and reports the result. No language model is connected."))),
    ];
  },
};
