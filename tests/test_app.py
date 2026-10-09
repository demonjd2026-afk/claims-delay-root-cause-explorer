"""End-to-end checks against the built data set. Run with `pytest`."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.agent.analyst import Analyst
from app.agent.tools import build_tools
from app.config import settings
from app.data.store import get_store
from app.main import app
from app.services import analytics as an


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_every_calendar_day_is_present(client):
    daily = client.get("/api/overview").json()["daily"]
    expected = (settings.window_end - settings.window_start).days + 1
    assert len(daily["dates"]) == expected
    assert daily["dates"][0] == settings.window_start.isoformat()
    assert daily["dates"][1] == (settings.window_start + timedelta(days=1)).isoformat()
    assert all(count > 0 for count in daily["received"])


def test_totals_reconcile(client):
    overview = client.get("/api/overview").json()
    kpis, themes = overview["kpis"], overview["themes"]
    assert sum(overview["daily"]["received"]) == kpis["claims"]
    assert sum(overview["daily"]["pended"]) == kpis["pended"]
    assert sum(t["claims"] for t in themes) == kpis["pended"]
    assert abs(sum(t["pend_days"] for t in themes) - kpis["pend_days_total"]) <= len(themes)
    assert sum(s["pended"] for s in overview["stages"]) == kpis["pended"]


def test_trend_series_reconcile(client):
    trends = client.get("/api/trends").json()
    for series in trends["by_theme"]:
        assert len(series["pended"]) == len(trends["dates"])
        assert sum(series["pended"]) == series["claims"]


def test_planted_incident_is_found(client):
    emerging = client.get("/api/trends").json()["emerging"]
    hit = next(e for e in emerging if e["key"] == "provider_match")
    assert hit["driver"]["value"] == "COSMOS"
    assert hit["onset"] == (settings.window_end - timedelta(days=20)).isoformat()


def test_filters_narrow_the_data(client):
    everything = client.get("/api/overview").json()["kpis"]["claims"]
    medicaid = client.get("/api/overview", params={"lob": "Medicaid"}).json()["kpis"]["claims"]
    assert 0 < medicaid < everything
    assert client.get("/api/overview", params={"lob": "Nope"}).status_code == 404


def test_classifier_quality(client):
    classifier = client.get("/api/model").json()["classifier"]
    assert classifier["holdout_accuracy"] > 0.9
    assert classifier["accuracy_on_unlabelled_assigned"] > 0.9
    assert classifier["code_only_correct_share"] < classifier["holdout_accuracy"]


def test_claim_detail_timeline_is_ordered(client):
    claim_id = client.get("/api/claims", params={"size": 5}).json()["rows"][0]["claim_id"]
    detail = client.get(f"/api/claims/{claim_id}").json()
    stamps = [event["at"] for event in detail["timeline"]]
    assert stamps == sorted(stamps)
    assert detail["pend"]["theme_name"]
    assert client.get("/api/claims/C2600000000").status_code == 404


def test_built_in_analyst_cites_its_lookup(client):
    reply = client.post("/api/chat", json={"question": "Where should we intervene first?"}).json()
    assert reply["evidence"][0]["tool"] == "recommend_interventions"
    assert "Start with" in reply["answer"]


def test_intake_is_covered(client):
    journey = client.get("/api/journey").json()
    intake = journey["stages"][0]
    assert intake["key"] == "intake" and len(intake["themes"]) >= 2
    slowest = journey["intake_by_channel"][0]
    assert slowest["channel"].startswith("Paper") and slowest["avg_intake_days_clean"] > 0.5


def test_rebuild_rejects_a_range_that_is_too_short(client):
    reply = client.post("/api/data/rebuild", json={"date_from": "2026-01-01", "date_to": "2026-01-20"})
    assert reply.status_code == 400 and "63" in reply.json()["detail"]


def test_llm_tool_loop(monkeypatch):
    """The model asks for a tool, receives real figures, then answers."""
    monkeypatch.setattr(type(settings), "llm_enabled", property(lambda self: True))
    analyst = Analyst(settings)
    seen = []

    def fake_complete(messages, tools):
        seen.append(messages)
        if len(seen) == 1:
            return {"content": None, "tool_calls": [{"id": "call_1", "type": "function", "function": {
                "name": "rank_delay_themes", "arguments": '{"metric": "pend_days"}'}}]}
        return {"content": "Prior authorization costs the most days."}

    monkeypatch.setattr(analyst._client, "complete", fake_complete)
    tools = build_tools(get_store(), an.Filters())
    reply = analyst.answer("What costs the most?", [], tools)
    assert reply["mode"] == "llm"
    assert reply["evidence"] == [{"tool": "rank_delay_themes", "args": {"metric": "pend_days"}}]
    tool_message = seen[1][-1]
    assert tool_message["role"] == "tool" and "Prior authorization" in tool_message["content"]


def test_rebuild_for_another_period(client):
    """Runs last: swaps in a different window, checks it, then restores the default."""
    try:
        reply = client.post("/api/data/rebuild", json={"date_from": "2026-01-01", "date_to": "2026-03-31"})
        assert reply.status_code == 200
        meta = client.get("/api/meta").json()
        assert (meta["date_min"], meta["date_max"], meta["as_of"]) == ("2026-01-01", "2026-03-31", "2026-04-02")
        daily = client.get("/api/overview").json()["daily"]
        assert len(daily["dates"]) == 90 and all(count > 0 for count in daily["received"])
        emerging = client.get("/api/trends").json()["emerging"]
        assert any(e["key"] == "provider_match" and e["onset"] == "2026-03-11" for e in emerging)
    finally:
        client.post("/api/data/rebuild", json={"date_from": settings.window_start.isoformat(),
                                               "date_to": settings.window_end.isoformat()})
