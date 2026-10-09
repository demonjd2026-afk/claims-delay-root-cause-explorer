"""HTTP API. Routes only parse input and delegate to the services."""
from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.agent.analyst import SUGGESTIONS, Analyst
from app.agent.tools import build_tools
from app.config import settings
from app.data.store import Store, get_store, rebuild
from app.domain import THEME_BY_KEY, NEEDS_REVIEW, theme_name
from app.services import analytics as an

router = APIRouter(prefix="/api")
analyst = Analyst(settings)


def filters(
    date_from: date | None = None, date_to: date | None = None,
    lob: str | None = None, platform: str | None = None,
) -> an.Filters:
    return an.Filters(date_from, date_to, lob or None, platform or None)


StoreDep = Annotated[Store, Depends(get_store)]
FiltersDep = Annotated[an.Filters, Depends(filters)]


def scoped(store: Store, f: an.Filters):
    df = f.apply(store.claims)
    if df.empty:
        raise HTTPException(404, "No claims match these filters.")
    return df


@router.get("/meta")
def get_meta(store: StoreDep):
    return {**an.meta(store), "analyst": {"mode": analyst.mode, "model": settings.llm_model or None,
                                           "suggestions": SUGGESTIONS}}


@router.get("/overview")
def get_overview(store: StoreDep, f: FiltersDep):
    df = scoped(store, f)
    return {"kpis": an.kpis(df), "daily": an.daily_overview(df), "themes": an.theme_table(df),
            "findings": an.key_findings(df), "interventions": an.interventions(df)["rows"][:3],
            "stages": [{k: s[k] for k in ("key", "name", "pended", "pended_share", "pend_days", "pend_days_share")}
                       for s in an.journey(df)["stages"]]}


@router.get("/journey")
def get_journey(store: StoreDep, f: FiltersDep):
    return an.journey(scoped(store, f))


@router.get("/themes/{key}")
def get_theme(key: str, store: StoreDep, f: FiltersDep):
    detail = an.theme_detail(store, scoped(store, f), key)
    if detail is None:
        raise HTTPException(404, "No pended claims for this theme in the current filters.")
    return detail


@router.get("/trends")
def get_trends(store: StoreDep, f: FiltersDep):
    return an.trends(scoped(store, f))


@router.get("/hotspots")
def get_hotspots(store: StoreDep, f: FiltersDep, dimension: str = "platform"):
    if dimension not in an.SEGMENT_DIMENSIONS:
        raise HTTPException(400, f"dimension must be one of {list(an.SEGMENT_DIMENSIONS)}")
    return an.hotspots(scoped(store, f), dimension)


@router.get("/interventions")
def get_interventions(store: StoreDep, f: FiltersDep):
    return an.interventions(scoped(store, f))


@router.get("/claims")
def get_claims(store: StoreDep, f: FiltersDep, theme: str | None = None, status: str | None = None,
               q: str | None = None, over_target: bool = False,
               page: Annotated[int, Query(ge=1)] = 1, size: Annotated[int, Query(ge=5, le=100)] = 25):
    return an.claim_list(scoped(store, f), theme or None, status or None, q or None, over_target, page, size)


@router.get("/claims/{claim_id}")
def get_claim(claim_id: str, store: StoreDep):
    detail = an.claim_detail(store, claim_id)
    if detail is None:
        raise HTTPException(404, "Claim not found.")
    return detail


@router.get("/model")
def get_model(store: StoreDep):
    report = store.model_report
    classifier = dict(report["classifier"])
    classifier["per_theme"] = [{**row, "name": theme_name(row["theme"])} for row in classifier["per_theme"]]
    clustering = [{**row, "name": theme_name(row["theme"])} for row in report["clustering"]["per_theme"]
                  if row["theme"] in THEME_BY_KEY or row["theme"] == NEEDS_REVIEW]
    return {"classifier": classifier, "clustering": clustering, "build_seconds": report["build_seconds"],
            "analyst": {"mode": analyst.mode, "model": settings.llm_model or None}}


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=6000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)
    lob: str | None = None
    platform: str | None = None
    date_from: date | None = None
    date_to: date | None = None


@router.post("/chat")
def chat(body: ChatRequest, store: StoreDep):
    f = an.Filters(body.date_from, body.date_to, body.lob or None, body.platform or None)
    scoped(store, f)
    tools = build_tools(store, f)
    return analyst.answer(body.question, [m.model_dump() for m in body.history], tools)


class RebuildRequest(BaseModel):
    date_from: date
    date_to: date
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)


@router.post("/data/rebuild")
def rebuild_data(body: RebuildRequest):
    """Generate synthetic claims for another period and rerun classification and clustering."""
    try:
        store = rebuild(body.date_from, body.date_to, body.seed)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"claims": int(len(store.claims)), "pended": int(store.claims.pended.sum()),
            "build_seconds": store.model_report["build_seconds"], **an.meta(store)["window"]}
