"""Tools the AI analyst can call. Each one is a thin, read-only wrapper over
the analytics service, so the analyst can only quote numbers the dashboard
itself would show."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.data.store import Store
from app.domain import NEEDS_REVIEW, THEMES
from app.services import analytics as an

THEME_KEYS = [t.key for t in THEMES] + [NEEDS_REVIEW]
RANK_METRICS = {"pend_days": "days lost", "claims": "pended claims", "avg_pend_days": "average days pended"}


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict
    run: Callable[..., dict]

    def schema(self) -> dict:
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": {"type": "object", "additionalProperties": False, **self.parameters}}}


def build_tools(store: Store, filters: an.Filters) -> dict[str, Tool]:
    df = filters.apply(store.claims)

    def summary() -> dict:
        return {"kpis": an.kpis(df), "key_findings": an.key_findings(df)}

    def rank_delay_themes(metric: str = "pend_days") -> dict:
        metric = metric if metric in RANK_METRICS else "pend_days"
        rows = sorted(an.theme_table(df), key=lambda r: -(r[metric] or 0))
        keep = ("key", "name", "stage_name", "claims", "claims_share", "avg_pend_days", "pend_days",
                "pend_days_share", "over_target", "open")
        return {"ranked_by": RANK_METRICS[metric], "themes": [{k: r[k] for k in keep} for r in rows]}

    def explain_theme(theme: str) -> dict:
        detail = an.theme_detail(store, df, theme)
        if detail is None:
            return {"error": f"No pended claims for theme '{theme}' in the current filters."}
        return {
            "name": detail["name"], "stage": detail["stage_name"], "claims": detail["claims"],
            "avg_pend_days": detail["avg_pend_days"], "pend_days": detail["pend_days"],
            "pend_days_share": detail["pend_days_share"], "over_target": detail["over_target"],
            "what_it_is": detail["playbook"]["plain"], "why_it_happens": detail["playbook"]["why"],
            "recommended_action": detail["playbook"]["intervention"], "owner": detail["playbook"]["owner"],
            "root_cause_clusters": [{k: c[k] for k in ("claims", "share", "avg_pend_days", "key_phrases", "example_note")}
                                    for c in detail["clusters"]],
            "most_affected_segments": {v["label"]: v["rows"][:2] for v in detail["segments"].values()},
        }

    def find_emerging_themes() -> dict:
        return {"emerging": an.emerging(df),
                "method": f"latest {an.RECENT_DAYS} days against the {an.BASELINE_DAYS} days before"}

    def recommend_interventions(top_n: int = 3) -> dict:
        plan = an.interventions(df)
        keep = ("rank", "name", "intervention", "owner", "effort", "addressability", "claims", "pend_days",
                "recoverable_days", "recoverable_touches", "priority_score")
        return {"interventions": [{k: r[k] for k in keep} for r in plan["rows"][:max(1, min(top_n, 12))]],
                "note": "Addressability and effort are planning assumptions, not measurements.",
                "days_in_window": plan["days_in_window"]}

    def compare_segments(dimension: str, theme: str | None = None) -> dict:
        if dimension not in an.SEGMENT_DIMENSIONS:
            return {"error": f"dimension must be one of {list(an.SEGMENT_DIMENSIONS)}"}
        if theme:
            detail = an.theme_detail(store, df, theme)
            if detail is None:
                return {"error": f"No pended claims for theme '{theme}'."}
            return {"theme": detail["name"], "unit": "pended claims per 1,000 received", **detail["segments"][dimension]}
        return {"unit": "pended claims per 1,000 received", **an.hotspots(df, dimension)}

    def stage_breakdown() -> dict:
        stages = an.journey(df)["stages"]
        return {"stages": [{**{k: s[k] for k in ("name", "pended", "pended_share", "pend_days", "pend_days_share",
                                                 "avg_days_clean", "avg_days_when_pended_here")},
                            "themes": [t["name"] for t in s["themes"]]} for s in stages]}

    def lookup_claim(claim_id: str) -> dict:
        return an.claim_detail(store, claim_id) or {"error": f"Claim {claim_id} not found."}

    theme_param = {"type": "string", "enum": THEME_KEYS, "description": "Delay theme key."}
    dim_param = {"type": "string", "enum": list(an.SEGMENT_DIMENSIONS)}
    tools = [
        Tool("summary", "Headline numbers and key findings for the current filters.", {"properties": {}}, summary),
        Tool("rank_delay_themes", "Rank delay themes by days lost, claim count or average days pended.",
             {"properties": {"metric": {"type": "string", "enum": list(RANK_METRICS)}}}, rank_delay_themes),
        Tool("explain_theme", "Everything about one delay theme: why it happens, its root-cause clusters, "
             "who is most affected and the recommended action.",
             {"properties": {"theme": theme_param}, "required": ["theme"]}, explain_theme),
        Tool("find_emerging_themes", "Themes whose daily volume has risen recently, with onset date and driver.",
             {"properties": {}}, find_emerging_themes),
        Tool("recommend_interventions", "Ranked list of where to intervene first.",
             {"properties": {"top_n": {"type": "integer", "minimum": 1, "maximum": 12}}}, recommend_interventions),
        Tool("compare_segments", "Pend rate per 1,000 claims by platform, line of business, specialty, channel, "
             "network status or claim type; optionally for one theme.",
             {"properties": {"dimension": dim_param, "theme": theme_param}, "required": ["dimension"]}, compare_segments),
        Tool("stage_breakdown", "Where in Intake, Pre-Adjudication, Adjudication and Post-Adjudication claims pend.",
             {"properties": {}}, stage_breakdown),
        Tool("lookup_claim", "Timeline, pend reason and adjuster note for one claim ID.",
             {"properties": {"claim_id": {"type": "string"}}, "required": ["claim_id"]}, lookup_claim),
    ]
    return {t.name: t for t in tools}
