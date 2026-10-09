"""Analytics over the claims store. Every number shown in the UI or quoted by
the AI analyst is computed here from claim rows; nothing is hard-coded."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from app.config import MAX_WINDOW_DAYS, MIN_WINDOW_DAYS, settings
from app.data.store import Store
from app.domain import (
    DENIAL_CODE_TEXT, NEEDS_REVIEW, NEEDS_REVIEW_NAME, STAGE_ORDER, STAGES, THEME_BY_KEY, THEMES, theme_name,
)

RECENT_DAYS, BASELINE_DAYS = 21, 42
EMERGING_MIN_LIFT, EMERGING_MIN_Z = 1.4, 3.0
SEGMENT_DIMENSIONS = {
    "platform": "Platform", "lob": "Line of business", "specialty": "Provider specialty",
    "channel": "Submission channel", "network_status": "Network status", "claim_type": "Claim type",
}


@dataclass(frozen=True)
class Filters:
    date_from: date | None = None
    date_to: date | None = None
    lob: str | None = None
    platform: str | None = None

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        mask = pd.Series(True, index=df.index)
        if self.date_from:
            mask &= df.received_date >= pd.Timestamp(self.date_from)
        if self.date_to:
            mask &= df.received_date <= pd.Timestamp(self.date_to)
        if self.lob:
            mask &= df.lob == self.lob
        if self.platform:
            mask &= df.platform == self.platform
        return df[mask]


def num(value, digits: int = 1):
    """JSON-safe number: None for missing, otherwise a rounded Python float."""
    if value is None or (isinstance(value, float) and math.isnan(value)) or pd.isna(value):
        return None
    return round(float(value), digits)


def _all_days(df: pd.DataFrame) -> pd.DatetimeIndex:
    return pd.date_range(df.received_date.min(), df.received_date.max(), freq="D")


def _daily(df: pd.DataFrame, days: pd.DatetimeIndex) -> pd.Series:
    """Claims per received day, with an explicit zero for days that had none."""
    return df.groupby("received_date").size().reindex(days, fill_value=0)


def _iso(days: pd.DatetimeIndex) -> list[str]:
    return [d.strftime("%Y-%m-%d") for d in days]


# --------------------------------------------------------------------- KPIs

def kpis(df: pd.DataFrame) -> dict:
    pended = df[df.pended]
    done = df[~df.is_open]
    open_pended = pended[pended.released_ts.isna()]
    return {
        "claims": int(len(df)),
        "pended": int(len(pended)),
        "pended_rate": num(len(pended) / len(df), 4) if len(df) else None,
        "first_pass_rate": num(1 - len(pended) / len(df), 4) if len(df) else None,
        "avg_days_clean": num(done[~done.pended].tat_days.mean()),
        "avg_days_pended": num(done[done.pended].tat_days.mean()),
        "avg_pend_days": num(pended.pend_days.mean()),
        "pend_days_total": num(pended.pend_days.sum(), 0),
        "manual_touches": int(pended.touches.sum()),
        "over_target": int(df.over_target.sum()),
        "over_target_pended_share": num(df[df.over_target].pended.mean(), 4),
        "open_pended": int(len(open_pended)),
        "open_pended_billed": num(open_pended.billed_amount.sum(), 0),
        "target_days": settings.sla_days,
    }


# ------------------------------------------------------------------- themes

def theme_table(df: pd.DataFrame) -> list[dict]:
    """One row per delay theme, ordered by days lost."""
    pended = df[df.pended]
    total_claims, total_days = len(pended), pended.pend_days.sum()
    rows = []
    for key, group in pended.groupby("theme"):
        theme = THEME_BY_KEY.get(key)
        rows.append({
            "key": key,
            "name": theme_name(key),
            "stage": theme.stage if theme else None,
            "stage_name": STAGES[theme.stage]["name"] if theme else None,
            "claims": int(len(group)),
            "claims_share": num(len(group) / total_claims, 4),
            "avg_pend_days": num(group.pend_days.mean()),
            "median_pend_days": num(group.pend_days.median()),
            "pend_days": num(group.pend_days.sum(), 0),
            "pend_days_share": num(group.pend_days.sum() / total_days, 4) if total_days else None,
            "billed": num(group.billed_amount.sum(), 0),
            "touches": int(group.touches.sum()),
            "over_target": int(group.over_target.sum()),
            "open": int(group.released_ts.isna().sum()),
            "denied_share": num((group.status == "Denied").mean(), 4),
        })
    return sorted(rows, key=lambda r: -(r["pend_days"] or 0))


def _segments(df: pd.DataFrame, in_theme: pd.DataFrame, dimension: str) -> list[dict]:
    """How often claims in each segment hit this theme, per 1,000 claims received."""
    overall = len(in_theme) / len(df) * 1000 if len(df) else 0
    received = df.groupby(dimension).size()
    hit = in_theme.groupby(dimension).size().reindex(received.index, fill_value=0)
    rows = [{
        "value": str(value),
        "claims_received": int(received[value]),
        "pended": int(hit[value]),
        "per_1000": num(hit[value] / received[value] * 1000),
        "index": num((hit[value] / received[value] * 1000) / overall, 2) if overall else None,
    } for value in received.index]
    return sorted(rows, key=lambda r: -(r["per_1000"] or 0))


def theme_detail(store: Store, df: pd.DataFrame, key: str) -> dict | None:
    row = next((r for r in theme_table(df) if r["key"] == key), None)
    if row is None:
        return None
    in_theme = df[df.pended & (df.theme == key)]
    days = _all_days(df)
    theme = THEME_BY_KEY.get(key)

    clusters = []
    for cluster_id, group in in_theme.groupby("cluster_id"):
        info = store.model_report["clusters"].get(cluster_id, {})
        clusters.append({
            "id": cluster_id,
            "claims": int(len(group)),
            "share": num(len(group) / len(in_theme), 4),
            "avg_pend_days": num(group.pend_days.mean()),
            "pend_days": num(group.pend_days.sum(), 0),
            "key_phrases": info.get("key_phrases", []),
            "example_note": info.get("example_note"),
        })
    clusters.sort(key=lambda c: -c["claims"])

    top_providers = (in_theme.groupby("provider_id").agg(claims=("claim_id", "size"), specialty=("specialty", "first"))
                     .sort_values("claims", ascending=False).head(5))
    playbook = {
        "plain": theme.plain, "why": theme.why, "intervention": theme.intervention, "owner": theme.owner,
        "stage_does": STAGES[theme.stage]["does"],
    } if theme else {
        "plain": "The note and pend code were too vague for a confident theme, so these claims are routed to a person.",
        "why": "The adjuster note carries no specific reason and the pend code is generic.",
        "intervention": "Require a reason on every pend so each delayed claim can be attributed.",
        "owner": "Claims operations", "stage_does": None,
    }
    return {
        **row,
        "playbook": playbook,
        "clusters": clusters,
        "daily": {"dates": _iso(days), "pended": _daily(in_theme, days).tolist()},
        "segments": {dim: {"label": label, "rows": _segments(df, in_theme, dim)}
                     for dim, label in SEGMENT_DIMENSIONS.items()},
        "top_providers": [{"provider_id": pid, "specialty": r.specialty, "claims": int(r.claims)}
                          for pid, r in top_providers.iterrows()],
        "sample_notes": in_theme.sort_values("pend_days", ascending=False).head(6)[
            ["claim_id", "adjuster_note", "pend_code", "pend_days", "confidence"]
        ].assign(pend_days=lambda d: d.pend_days.round(1)).to_dict("records"),
    }


# ------------------------------------------------------------------ journey

def journey(df: pd.DataFrame) -> dict:
    pended, clean = df[df.pended], df[~df.pended]
    themes = theme_table(df)
    stages = []
    for key in STAGE_ORDER:
        at_stage = pended[pended.pend_stage == key]
        column = f"days_{key}"
        stages.append({
            "key": key,
            "name": STAGES[key]["name"],
            "does": STAGES[key]["does"],
            "pended": int(len(at_stage)),
            "pended_share": num(len(at_stage) / len(pended), 4) if len(pended) else None,
            "pend_days": num(at_stage.pend_days.sum(), 0),
            "pend_days_share": num(at_stage.pend_days.sum() / pended.pend_days.sum(), 4) if len(pended) else None,
            "avg_days_clean": num(clean[column].mean(), 2),
            "avg_days_when_pended_here": num(at_stage[column].mean(), 2),
            "avg_days_all_pended": num(pended[column].mean(), 2),
            "themes": [t for t in themes if t["stage"] == key],
        })
    # Intake is also slower for some channels even when nothing pends.
    by_channel = []
    for channel, group in df.groupby("channel"):
        at_intake = group[group.pended & (group.pend_stage == "intake")]
        by_channel.append({
            "channel": channel, "claims": int(len(group)),
            "avg_intake_days_clean": num(group[~group.pended].days_intake.mean(), 2),
            "intake_pends_per_1000": num(len(at_intake) / len(group) * 1000),
            "intake_pended": int(len(at_intake)),
        })
    by_channel.sort(key=lambda r: -(r["avg_intake_days_clean"] or 0))
    return {"stages": stages, "intake_by_channel": by_channel,
            "unattributed": next((t for t in themes if t["key"] == NEEDS_REVIEW), None)}


# ------------------------------------------------------------------- trends

def daily_overview(df: pd.DataFrame) -> dict:
    days = _all_days(df)
    received, pended = _daily(df, days), _daily(df[df.pended], days)
    return {
        "dates": _iso(days),
        "received": received.tolist(),
        "pended": pended.tolist(),
        "pended_rate": [num(p / r * 100, 2) if r else None for p, r in zip(pended, received)],
    }


def trends(df: pd.DataFrame) -> dict:
    days = _all_days(df)
    pended = df[df.pended]
    return {
        "dates": _iso(days),
        "by_stage": [{"key": s, "name": STAGES[s]["name"],
                      "pended": _daily(pended[pended.pend_stage == s], days).tolist()} for s in STAGE_ORDER],
        "by_theme": [{"key": t["key"], "name": t["name"], "stage": t["stage"], "claims": t["claims"],
                      "pended": _daily(pended[pended.theme == t["key"]], days).tolist()}
                     for t in sorted(theme_table(df), key=lambda r: -r["claims"])],
        "emerging": emerging(df),
        "emerging_checked": len(days) >= RECENT_DAYS + BASELINE_DAYS,
        "emerging_needs_days": RECENT_DAYS + BASELINE_DAYS,
    }


def emerging(df: pd.DataFrame) -> list[dict]:
    """Themes whose daily pend volume in the latest three weeks is well above
    the six weeks before, with the segment that explains most of the rise."""
    days = _all_days(df)
    if len(days) < RECENT_DAYS + BASELINE_DAYS:
        return []
    recent_days, base_days = days[-RECENT_DAYS:], days[-(RECENT_DAYS + BASELINE_DAYS):-RECENT_DAYS]
    pended = df[df.pended]
    found = []
    for key, group in pended.groupby("theme"):
        series = _daily(group, days)
        recent, base = series[recent_days], series[base_days]
        if base.mean() == 0:
            continue
        lift = recent.mean() / base.mean()
        z = (recent.mean() - base.mean()) / (base.std(ddof=1) / math.sqrt(RECENT_DAYS) or np.inf)
        if lift < EMERGING_MIN_LIFT or z < EMERGING_MIN_Z:
            continue

        is_recent = group.received_date >= recent_days[0]
        is_base = (group.received_date >= base_days[0]) & ~is_recent
        driver = None
        for dim, label in SEGMENT_DIMENSIONS.items():
            now = group[is_recent].groupby(dim).size() / RECENT_DAYS
            before = (group[is_base].groupby(dim).size() / BASELINE_DAYS).reindex(now.index, fill_value=0)
            gain = (now - before).sort_values(ascending=False)
            if driver is None or gain.iloc[0] > driver["gain"]:
                driver = {"dimension": label, "value": str(gain.index[0]), "gain": float(gain.iloc[0]),
                          "per_day_before": num(before[gain.index[0]]), "per_day_now": num(now[gain.index[0]]),
                          "share_of_rise": num(gain.iloc[0] / (recent.mean() - base.mean()), 2)}
        # Above 100% is possible when other segments fell, so say it in words instead.
        driver["share_text"] = ("Almost all" if driver["share_of_rise"] >= 0.95
                                else "Most" if driver["share_of_rise"] >= 0.6
                                else f"{driver['share_of_rise']:.0%}")
        threshold = base.quantile(0.95)
        above = (recent > threshold) & (recent.shift(-1, fill_value=recent.iloc[-1]) > threshold)
        top_cluster = group[is_recent].cluster_id.value_counts(normalize=True)
        found.append({
            "key": key, "name": theme_name(key),
            "per_day_before": num(base.mean()), "per_day_now": num(recent.mean()),
            "lift": num(lift, 2), "z": num(z, 1),
            "onset": above.idxmax().strftime("%Y-%m-%d") if above.any() else None,
            "extra_claims": int(round((recent.mean() - base.mean()) * RECENT_DAYS)),
            "driver": {k: v for k, v in driver.items() if k != "gain"},
            "top_cluster": {"id": top_cluster.index[0], "share": num(top_cluster.iloc[0], 2)} if len(top_cluster) else None,
            "recent_window": [recent_days[0].strftime("%Y-%m-%d"), recent_days[-1].strftime("%Y-%m-%d")],
            "baseline_window": [base_days[0].strftime("%Y-%m-%d"), base_days[-1].strftime("%Y-%m-%d")],
        })
    return sorted(found, key=lambda r: -r["lift"])


def hotspots(df: pd.DataFrame, dimension: str) -> dict:
    """Pended claims per 1,000 received, for every theme and segment value."""
    received = df.groupby(dimension).size()
    pended = df[df.pended]
    counts = pended.groupby(["theme", dimension]).size().unstack(fill_value=0).reindex(columns=received.index, fill_value=0)
    order = [t["key"] for t in sorted(theme_table(df), key=lambda r: -r["claims"])]
    return {
        "dimension": SEGMENT_DIMENSIONS[dimension],
        "columns": [str(c) for c in received.index],
        "received": [int(v) for v in received],
        "rows": [{"key": key, "name": theme_name(key),
                  "per_1000": [num(counts.loc[key, c] / received[c] * 1000) for c in received.index],
                  "claims": [int(counts.loc[key, c]) for c in received.index]} for key in order],
    }


# ------------------------------------------------------------ interventions

EFFORT = {1: ("Low", 1.0), 2: ("Medium", 2.0), 3: ("High", 3.5)}


def interventions(df: pd.DataFrame) -> dict:
    """Ranks themes by delay days that could realistically be removed per unit
    of effort. Addressability and effort are playbook assumptions."""
    days_in_window = max(1, df.received_date.nunique())
    rows = []
    for row in theme_table(df):
        theme = THEME_BY_KEY.get(row["key"])
        if theme is None:
            continue
        label, weight = EFFORT[theme.effort]
        recoverable = row["pend_days"] * theme.addressability
        rows.append({
            **row,
            "intervention": theme.intervention, "owner": theme.owner, "why": theme.why,
            "addressability": theme.addressability, "effort": label, "effort_level": theme.effort,
            "recoverable_days": num(recoverable, 0),
            "recoverable_claims": int(round(row["claims"] * theme.addressability)),
            "recoverable_touches": int(round(row["touches"] * theme.addressability)),
            "priority_score": num(recoverable / weight, 0),
        })
    rows.sort(key=lambda r: -r["priority_score"])
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return {"rows": rows, "days_in_window": int(days_in_window), "claims_in_window": int(len(df)),
            "claims_per_year_at_this_rate": int(round(len(df) * 365 / days_in_window))}


def key_findings(df: pd.DataFrame) -> list[dict]:
    """The three or four things a leader should take away, built from the data."""
    themes = [t for t in theme_table(df) if t["key"] != NEEDS_REVIEW]
    if not themes:
        return []
    pended = df[df.pended]
    by_days, by_claims = themes[0], max(themes, key=lambda t: t["claims"])
    findings = [{
        "kind": "impact", "theme": by_days["key"],
        "title": f"{by_days['name']} costs the most time",
        "text": (f"{by_days['pend_days_share']:.0%} of all days lost to pends come from this theme: "
                 f"{by_days['claims']:,} claims waiting {by_days['avg_pend_days']} days on average."),
    }]
    quick = min(themes, key=lambda t: t["avg_pend_days"])
    if quick["claims_share"] > quick["pend_days_share"] * 2:
        findings.append({
            "kind": "contrast", "theme": quick["key"],
            "title": "Volume and impact are not the same thing",
            "text": (f"{quick['name']} is {quick['claims_share']:.0%} of pended claims but only "
                     f"{quick['pend_days_share']:.0%} of days lost, because each one clears in about "
                     f"{quick['avg_pend_days']} days. Ranking by claim count alone would overstate it."),
        })
    elif by_claims["key"] != by_days["key"]:
        findings.append({
            "kind": "contrast", "theme": by_claims["key"],
            "title": "The most frequent theme is not the most costly",
            "text": f"{by_claims['name']} has the most pended claims ({by_claims['claims']:,}) but ranks lower on days lost.",
        })
    for item in emerging(df)[:1]:
        d = item["driver"]
        findings.append({
            "kind": "emerging", "theme": item["key"],
            "title": f"{item['name']} is rising",
            "text": (f"Up from {item['per_day_before']} to {item['per_day_now']} pended claims a day"
                     + (f" since about {pd.Timestamp(item['onset']).strftime('%-d %b')}" if item["onset"] else "")
                     + f". {d['share_text']} of the rise is {d['dimension'].lower()} {d['value']}."),
        })
    generic = (pended.pend_code == "PND-000").mean()
    findings.append({
        "kind": "visibility", "theme": None,
        "title": "Pend codes alone hide part of the picture",
        "text": (f"{generic:.0%} of pended claims carry only a generic pend code. Their cause is written in the "
                 f"adjuster note, which is what the classifier reads."),
    })
    return findings


# ------------------------------------------------------------------- claims

CLAIM_LIST_COLUMNS = ["claim_id", "received_date", "lob", "platform", "specialty", "status", "theme",
                      "pend_stage", "pend_code", "pend_days", "age_days", "billed_amount", "confidence"]


def claim_list(df: pd.DataFrame, theme: str | None, status: str | None, query: str | None,
               over_target: bool, page: int, size: int) -> dict:
    rows = df[df.pended]
    if theme:
        rows = rows[rows.theme == theme]
    if status:
        rows = rows[rows.status == status]
    if over_target:
        rows = rows[rows.over_target]
    if query:
        text = query.strip().lower()
        rows = rows[rows.claim_id.str.lower().str.contains(text, regex=False)
                    | rows.adjuster_note.fillna("").str.lower().str.contains(text, regex=False)
                    | rows.provider_id.str.lower().str.contains(text, regex=False)]
    rows = rows.sort_values("pend_days", ascending=False)
    page_rows = rows.iloc[(page - 1) * size: page * size][CLAIM_LIST_COLUMNS]
    records = []
    for r in page_rows.itertuples(index=False):
        records.append({
            "claim_id": r.claim_id, "received_date": r.received_date.strftime("%Y-%m-%d"), "lob": r.lob,
            "platform": r.platform, "specialty": r.specialty, "status": r.status,
            "theme": r.theme, "theme_name": theme_name(r.theme), "stage_name": STAGES[r.pend_stage]["name"],
            "pend_code": r.pend_code, "pend_days": num(r.pend_days), "age_days": num(r.age_days),
            "billed_amount": num(r.billed_amount, 2), "confidence": num(r.confidence, 2),
        })
    return {"total": int(len(rows)), "page": page, "size": size, "rows": records}


def claim_detail(store: Store, claim_id: str) -> dict | None:
    match = store.claims[store.claims.claim_id == claim_id.strip().upper()]
    if match.empty:
        return None
    r = match.iloc[0]

    def ts(value):
        return None if pd.isna(value) else value.strftime("%Y-%m-%d %H:%M")

    events = [("Received", r.received_ts, "intake"), ("Intake complete", r.intake_done_ts, "intake"),
              ("Pre-adjudication complete", r.preadj_done_ts, "pre_adjudication"),
              ("Adjudicated", r.adjudicated_ts, "adjudication"),
              (f"Finalized ({r.status})" if not r.is_open else "Finalized", r.finalized_ts, "post_adjudication")]
    if r.pended:
        events += [(f"Pended in {STAGES[r.pend_stage]['name']}", r.pended_ts, r.pend_stage),
                   ("Pend released", r.released_ts, r.pend_stage)]
    happened = sorted((e for e in events if not pd.isna(e[1])), key=lambda e: e[1])
    cluster = store.model_report["clusters"].get(r.cluster_id) if r.pended and not pd.isna(r.cluster_id) else None
    return {
        "claim_id": r.claim_id, "status": r.status, "lob": r.lob, "platform": r.platform, "channel": r.channel,
        "claim_type": r.claim_type, "specialty": r.specialty, "network_status": r.network_status,
        "provider_id": r.provider_id, "billed_amount": num(r.billed_amount, 2),
        "age_days": num(r.age_days), "over_target": bool(r.over_target), "target_days": settings.sla_days,
        "pended": bool(r.pended),
        "pend": {
            "stage_name": STAGES[r.pend_stage]["name"], "pend_code": r.pend_code, "note": r.adjuster_note,
            "pend_days": num(r.pend_days), "touches": int(r.touches),
            "theme": r.theme, "theme_name": theme_name(r.theme), "confidence": num(r.confidence, 2),
            "cluster_phrases": cluster["key_phrases"] if cluster else [],
            "still_pended": bool(pd.isna(r.released_ts)),
        } if r.pended else None,
        "denial": {"code": r.denial_code, "text": DENIAL_CODE_TEXT.get(str(r.denial_code))}
        if not pd.isna(r.denial_code) else None,
        "timeline": [{"event": name, "at": ts(at), "stage": STAGES[stage]["name"]} for name, at, stage in happened],
        "stage_days": [{"stage": STAGES[s]["name"], "days": num(r[f"days_{s}"], 2)} for s in STAGE_ORDER],
    }


def meta(store: Store) -> dict:
    df = store.claims
    return {
        "date_min": df.received_date.min().strftime("%Y-%m-%d"),
        "date_max": df.received_date.max().strftime("%Y-%m-%d"),
        "as_of": store.as_of.strftime("%Y-%m-%d"),
        "lobs": sorted(df.lob.unique()), "platforms": sorted(df.platform.unique()),
        "themes": [{"key": t.key, "name": t.name, "stage": t.stage} for t in THEMES]
                  + [{"key": NEEDS_REVIEW, "name": NEEDS_REVIEW_NAME, "stage": None}],
        "stages": [{"key": k, **v} for k, v in STAGES.items()],
        "segment_dimensions": SEGMENT_DIMENSIONS,
        "target_days": settings.sla_days,
        "window": {**store.model_report["window"], "min_days": MIN_WINDOW_DAYS, "max_days": MAX_WINDOW_DAYS},
        "statuses": sorted(df[df.pended].status.unique()),
    }
