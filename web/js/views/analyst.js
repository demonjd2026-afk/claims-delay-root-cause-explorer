import { h, markdown } from "../ui.js";

// Kept at module level so the conversation survives switching tabs.
const conversation = [];
const TOOL_LABEL = {
  summary: "Headline numbers", rank_delay_themes: "Theme ranking", explain_theme: "Theme detail",
  find_emerging_themes: "Rising themes", recommend_interventions: "Intervention ranking",
  compare_segments: "Segment comparison", stage_breakdown: "Stage breakdown", lookup_claim: "Claim lookup",
};

function bubble(message) {
  if (message.role === "user") return h("div", { class: "msg user" }, message.content);
  const node = h("div", { class: "msg bot" }, markdown(message.content));
  if (message.notice) node.prepend(h("p", { class: "small muted" }, message.notice));
  if (message.evidence?.length) {
    node.append(h("div", { class: "evidence" }, "Based on:",
      [...new Set(message.evidence.map((e) => TOOL_LABEL[e.tool] ?? e.tool))].map((t) => h("span", { class: "tag" }, t))));
  }
  return node;
}

export const analystView = {
  id: "analyst", label: "Ask the analyst", title: "Ask a question about claim delays",
  lede: "Ask in plain English. The analyst looks up the answer in the same figures the dashboard shows and tells you which ones it used.",
  icon: '<path d="M2.5 3.5h11v7h-6l-3 2.5v-2.5h-2z"/>',
  async render({ api, filters, state }) {
    const meta = state.meta.analyst;
    const log = h("div", { class: "chat-log", "aria-live": "polite" });
    const input = h("input", { type: "text", placeholder: "For example: where should we intervene first?", "aria-label": "Your question", maxlength: "1000", autocomplete: "off" });
    const send = h("button", { class: "btn", type: "submit" }, "Ask");

    const paint = () => {
      log.replaceChildren(
        h("div", { class: "msg bot" },
          h("p", {}, meta.mode === "llm"
            ? `Answers are written by the language model ${meta.model}, using figures it looks up in the claims data.`
            : "Answers come from the built-in analyst, which looks up figures in the claims data. Connect a language model in the .env file for free-form conversation."),
          h("p", { class: "small muted" }, "Questions use the filters selected at the top of the other pages.")),
        ...conversation.map(bubble));
      log.scrollTop = log.scrollHeight;
    };

    const ask = async (question) => {
      const text = question.trim();
      if (!text || send.disabled) return;
      const history = conversation.map(({ role, content }) => ({ role, content })).slice(-10);
      conversation.push({ role: "user", content: text });
      paint();
      const waiting = h("div", { class: "msg bot muted" }, "Looking that up…");
      log.append(waiting); log.scrollTop = log.scrollHeight;
      input.value = ""; send.disabled = true;
      try {
        const reply = await api.chat({ question: text, history, lob: filters.lob || null, platform: filters.platform || null,
          date_from: filters.date_from || null, date_to: filters.date_to || null });
        conversation.push({ role: "assistant", content: reply.answer || "I could not produce an answer.", evidence: reply.evidence, notice: reply.notice });
      } catch (error) {
        conversation.push({ role: "assistant", content: `That did not work: ${error.message}` });
      }
      send.disabled = false; paint(); input.focus();
    };

    paint();
    return h("section", { class: "card chat" }, log,
      h("form", { class: "chat-form", onsubmit: (e) => { e.preventDefault(); ask(input.value); } },
        h("div", { class: "suggest" }, meta.suggestions.map((s) => h("button", { type: "button", onclick: () => ask(s) }, s))),
        h("div", { class: "rowi" }, input, send)));
  },
};
