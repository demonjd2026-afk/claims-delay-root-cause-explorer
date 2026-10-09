"""The AI analyst.

With an LLM configured it runs a tool-calling loop: the model decides which
analytics tools to call, reads the results and writes the answer. Without one,
or if the LLM call fails, a built-in analyst routes the question to the same
tools by keyword. Either way every figure comes from a tool result.
"""
from __future__ import annotations

import json
import logging
import re

from app.agent.llm import ChatClient, LLMError
from app.agent.tools import Tool
from app.config import Settings
from app.domain import NEEDS_REVIEW

log = logging.getLogger("cde.analyst")
MAX_TOOL_ROUNDS = 6
MAX_HISTORY = 10

SYSTEM_PROMPT = """You are the analyst inside the Claims Delay Root-Cause Explorer, used by healthcare \
claims operations leaders. Claims move through four stages: Intake, Pre-Adjudication, Adjudication, \
Post-Adjudication. A claim that cannot be processed automatically is "pended" for manual work; that is the delay.

Rules:
- Answer only from tool results. Call tools before stating any number. Never estimate or invent a figure.
- If the tools cannot answer the question, say so and say what data would be needed.
- Write for a business reader: lead with the answer in one sentence, then at most five short bullets.
- "Days lost" means total days claims spent pended. Prefer it over claim counts when judging impact.
- Addressability and effort in intervention rankings are planning assumptions; say so when you use them.
- The data is synthetic. Do not present it as real company performance.
- Plain text with simple markdown (bold, bullets). No tables, no headings."""

THEME_WORDS = {
    "edi_validation": ("format", "edi", "syntax", "hipaa", "paper", "scan", "data error"),
    "intake_routing": ("misrout", "routing", "wrong queue", "split"),
    "member_match": ("member match", "member could", "member pick", "newborn", "subscriber id"),
    "provider_match": ("provider match", "provider or tax", "tax id", "tin", "npi", "provider pick", "roster"),
    "duplicate": ("duplicate", "dup ", "resubmi"),
    "fwa_review": ("fraud", "fwa", "waste", "abuse", "siu"),
    "eligibility": ("eligib", "coverage", "termed", "retro"),
    "prior_auth": ("prior auth", "authoriz", "authoris", "precert", " pa ", "auth"),
    "clinical_edit": ("clinical edit", "bundl", "coding", "modifier"),
    "medical_records": ("medical record", "records", "medical necessity", "clinical review"),
    "cob": ("cob", "coordination", "other insurance", "primary insurer", "secondary"),
    "pricing": ("pricing", "price", "contract", "fee schedule", "out of network", "out-of-network", "non-par"),
    "payment_hold": ("payment", "eft", "check run", "bank"),
    NEEDS_REVIEW: ("needs review", "human review", "unclassified", "low confidence"),
}
DIMENSION_WORDS = {
    "platform": ("platform", "cosmos", "tops", "csp", "usp", "system"),
    "lob": ("line of business", "lob", "commercial", "medicare", "medicaid"),
    "specialty": ("specialty", "specialties", "radiology", "orthop", "cardio"),
    "channel": ("channel", "clearinghouse", "portal", "mail"),
    "network_status": ("network", "par "),
    "claim_type": ("institutional", "professional", "claim type"),
}
SUGGESTIONS = [
    "Where should we intervene first?",
    "Which delay theme costs us the most days?",
    "Is anything getting worse recently?",
    "Why do prior authorization claims pend?",
    "Which platform has the highest pend rate?",
    "At which stage do most claims get stuck?",
]


def _pct(value) -> str:
    return "n/a" if value is None else f"{value:.0%}"


class Analyst:
    def __init__(self, cfg: Settings):
        self._cfg = cfg
        self._client = ChatClient(cfg) if cfg.llm_enabled else None

    @property
    def mode(self) -> str:
        return "llm" if self._client else "built_in"

    def answer(self, question: str, history: list[dict], tools: dict[str, Tool]) -> dict:
        if self._client:
            try:
                return self._answer_with_llm(question, history, tools)
            except LLMError as exc:
                log.warning("LLM unavailable, using built-in analyst: %s", exc)
                result = self._answer_built_in(question, tools)
                result["notice"] = "The language model could not be reached, so the built-in analyst answered."
                return result
        return self._answer_built_in(question, tools)

    # ------------------------------------------------------------ LLM path

    def _answer_with_llm(self, question: str, history: list[dict], tools: dict[str, Tool]) -> dict:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages += [{"role": m["role"], "content": m["content"]} for m in history[-MAX_HISTORY:]
                     if m.get("role") in ("user", "assistant") and m.get("content")]
        messages.append({"role": "user", "content": question})
        schemas = [t.schema() for t in tools.values()]
        evidence: list[dict] = []

        for _ in range(MAX_TOOL_ROUNDS):
            reply = self._client.complete(messages, schemas)
            calls = reply.get("tool_calls") or []
            if not calls:
                return {"answer": (reply.get("content") or "").strip(), "evidence": evidence,
                        "mode": "llm", "model": self._cfg.llm_model}
            messages.append({"role": "assistant", "content": reply.get("content"), "tool_calls": calls})
            for call in calls:
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"].get("arguments") or "{}")
                    result = tools[name].run(**args)
                except KeyError:
                    args, result = {}, {"error": f"Unknown tool {name}."}
                except (TypeError, ValueError) as exc:
                    args, result = {}, {"error": f"Bad arguments: {exc}"}
                evidence.append({"tool": name, "args": args})
                messages.append({"role": "tool", "tool_call_id": call["id"],
                                 "content": json.dumps(result, default=str)})
        raise LLMError("tool loop did not finish")

    # ------------------------------------------------------- built-in path

    def _answer_built_in(self, question: str, tools: dict[str, Tool]) -> dict:
        q = f" {question.lower().strip()} "
        evidence: list[dict] = []

        def call(name: str, **args) -> dict:
            evidence.append({"tool": name, "args": args})
            return tools[name].run(**args)

        claim = re.search(r"\bC26\d{8}\b", question.upper())
        theme = next((k for k, words in THEME_WORDS.items() if any(w in q for w in words)), None)
        dimension = next((k for k, words in DIMENSION_WORDS.items() if any(w in q for w in words)), None)
        has = lambda *words: any(w in q for w in words)  # noqa: E731

        if claim:
            text = self._say_claim(call("lookup_claim", claim_id=claim.group()))
        elif has("interven", "first", "priorit", "fix", "recommend", "what should", "action", "invest"):
            text = self._say_interventions(call("recommend_interventions", top_n=3))
        elif has("worse", "emerging", "rising", "spike", "increas", "recent", "trend", "changed", "new "):
            text = self._say_emerging(call("find_emerging_themes"))
        elif theme and not dimension:
            text = self._say_theme(call("explain_theme", theme=theme))
        elif dimension:
            text = self._say_segments(call("compare_segments", dimension=dimension, **({"theme": theme} if theme else {})))
        elif has("stage", "intake", "adjudication", "stuck", "where in", "journey"):
            text = self._say_stages(call("stage_breakdown"))
        elif has("most", "top", "biggest", "rank", "driver", "theme", "cause", "why", "cost"):
            metric = "claims" if has("volume", "count", "how many", "frequent") else \
                "avg_pend_days" if has("longest", "slowest") else "pend_days"
            text = self._say_ranking(call("rank_delay_themes", metric=metric))
        else:
            text = self._say_summary(call("summary"))
        return {"answer": text, "evidence": evidence, "mode": "built_in", "model": None}

    @staticmethod
    def _say_summary(data: dict) -> str:
        k = data["kpis"]
        lines = [f"**{k['pended']:,} of {k['claims']:,} claims ({_pct(k['pended_rate'])}) were pended for manual work.** "
                 f"A clean claim finishes in {k['avg_days_clean']} days; a pended one takes {k['avg_days_pended']}."]
        lines += [f"- **{f['title']}.** {f['text']}" for f in data["key_findings"]]
        return "\n".join(lines)

    @staticmethod
    def _say_ranking(data: dict) -> str:
        top = data["themes"][:5]
        lines = [f"**{top[0]['name']} ranks first by {data['ranked_by']}.** The top five:"]
        lines += [f"- **{t['name']}** ({t['stage_name'] or 'no stage'}): {t['claims']:,} claims, "
                  f"{t['avg_pend_days']} days each, {t['pend_days']:,.0f} days lost ({_pct(t['pend_days_share'])})"
                  for t in top]
        return "\n".join(lines)

    @staticmethod
    def _say_theme(data: dict) -> str:
        if "error" in data:
            return data["error"]
        lines = [f"**{data['name']}** pends in {data['stage'] or 'no single stage'}: {data['claims']:,} claims, "
                 f"{data['avg_pend_days']} days each, {_pct(data['pend_days_share'])} of all days lost.",
                 f"- **Why it happens:** {data['why_it_happens']}"]
        for c in data["root_cause_clusters"][:3]:
            phrases = ", ".join(c["key_phrases"][:3]) or "no distinctive phrases"
            lines.append(f"- **Root-cause cluster, {_pct(c['share'])} of claims** ({c['avg_pend_days']} days each): "
                         f"notes mention {phrases}.")
        hot = max((rows[0] | {"dimension": label} for label, rows in data["most_affected_segments"].items() if rows),
                  key=lambda r: r["index"] or 0)
        lines.append(f"- **Most affected:** {hot['dimension'].lower()} {hot['value']}, at {hot['per_1000']} per 1,000 "
                     f"claims ({hot['index']}x the average).")
        lines.append(f"- **Recommended action ({data['owner']}):** {data['recommended_action']}")
        return "\n".join(lines)

    @staticmethod
    def _say_emerging(data: dict) -> str:
        if not data["emerging"]:
            return f"**No theme is rising.** I compared the {data['method']} and nothing cleared the threshold."
        lines = []
        for e in data["emerging"]:
            d = e["driver"]
            lines.append(f"**{e['name']} is up {e['lift']}x**, from {e['per_day_before']} to {e['per_day_now']} "
                         f"pended claims a day" + (f", starting around {e['onset']}." if e["onset"] else "."))
            lines.append(f"- About {e['extra_claims']:,} extra pended claims in the {data['method'].split(' against')[0]}.")
            lines.append(f"- {d['share_text']} of the rise is {d['dimension'].lower()} {d['value']} "
                         f"({d['per_day_before']} to {d['per_day_now']} a day).")
        lines.append(f"- Method: {data['method']}.")
        return "\n".join(lines)

    @staticmethod
    def _say_interventions(data: dict) -> str:
        rows = data["interventions"]
        lines = [f"**Start with {rows[0]['name'].lower()}.** Ranked by delay days that can be removed per unit of effort:"]
        lines += [f"- **{r['rank']}. {r['name']}** ({r['owner']}, {r['effort'].lower()} effort): {r['intervention']} "
                  f"Removes about {r['recoverable_days']:,.0f} of {r['pend_days']:,.0f} days lost." for r in rows]
        lines.append(f"- {data['note']}")
        return "\n".join(lines)

    @staticmethod
    def _say_segments(data: dict) -> str:
        if "error" in data:
            return data["error"]
        if "rows" in data and "columns" not in data:
            rows = data["rows"]
            lines = [f"**For {data['theme'].lower()}, {data['label'].lower()} {rows[0]['value']} is highest** "
                     f"at {rows[0]['per_1000']} pended per 1,000 claims."]
            lines += [f"- {r['value']}: {r['per_1000']} per 1,000 ({r['pended']:,} claims, {r['index']}x average)" for r in rows[:6]]
            return "\n".join(lines)
        totals = [(col, sum(r["claims"][i] for r in data["rows"]) / data["received"][i] * 1000)
                  for i, col in enumerate(data["columns"])]
        totals.sort(key=lambda t: -t[1])
        lines = [f"**{totals[0][0]} has the highest pend rate** at {totals[0][1]:.1f} per 1,000 claims received."]
        for col, rate in totals[:6]:
            i = data["columns"].index(col)
            worst = max(data["rows"], key=lambda r: r["per_1000"][i] or 0)
            lines.append(f"- {col}: {rate:.1f} per 1,000; largest theme is {worst['name'].lower()} ({worst['per_1000'][i]})")
        return "\n".join(lines)

    @staticmethod
    def _say_stages(data: dict) -> str:
        stages = data["stages"]
        top = max(stages, key=lambda s: s["pend_days"] or 0)
        lines = [f"**{top['name']} is where most time is lost**: {_pct(top['pend_days_share'])} of days lost "
                 f"and {_pct(top['pended_share'])} of pended claims."]
        lines += [f"- **{s['name']}:** {s['pended']:,} pended, {s['pend_days']:,.0f} days lost. A claim normally spends "
                  f"{s['avg_days_clean']} days here; {s['avg_days_when_pended_here']} when it pends." for s in stages]
        return "\n".join(lines)

    @staticmethod
    def _say_claim(data: dict) -> str:
        if "error" in data:
            return data["error"]
        lines = [f"**Claim {data['claim_id']}** is {data['status'].lower()}, {data['age_days']} days from receipt"
                 + (f", over the {data['target_days']}-day target." if data["over_target"] else ".")]
        if data["pend"]:
            p = data["pend"]
            lines.append(f"- Pended in {p['stage_name']} for {p['pend_days']} days with code {p['pend_code']}.")
            lines.append(f"- Theme: **{p['theme_name']}** (confidence {_pct(p['confidence'])}).")
            lines.append(f"- Adjuster note: “{p['note']}”")
        else:
            lines.append("- It was not pended; it went straight through.")
        if data["denial"]:
            lines.append(f"- Denied with code {data['denial']['code']}: {data['denial']['text']}.")
        return "\n".join(lines)


