"""Root-cause clustering.

Within each delay theme, groups adjuster notes that say the same thing so a
theme such as "prior authorization" breaks into the specific situations behind
it. Clusters are described by their most distinctive phrases and the note
closest to the cluster centre; nothing is named by hand.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import adjusted_rand_score, silhouette_score

from app.domain import NEEDS_REVIEW, THEME_BY_KEY

MIN_CLAIMS_TO_SPLIT = 60
K_RANGE = range(2, 6)
SIMPLER_SPLIT_TOLERANCE = 0.03


def _key_phrases(centre: np.ndarray, overall: np.ndarray, terms: np.ndarray, limit: int = 4) -> list[str]:
    """Most distinctive phrases, skipping ones already covered by a chosen phrase."""
    chosen: list[str] = []
    for idx in np.argsort(centre - overall)[::-1]:
        term = terms[idx]
        words = set(term.split())
        if any(words <= set(c.split()) or set(c.split()) <= words for c in chosen):
            continue
        chosen.append(term)
        if len(chosen) == limit:
            break
    return chosen


def cluster_theme(notes: pd.Series, seed: int) -> tuple[np.ndarray, list[dict]]:
    """Returns (cluster index per note, cluster descriptions ordered largest first)."""
    if len(notes) < MIN_CLAIMS_TO_SPLIT:
        return np.zeros(len(notes), dtype=int), [{"key_phrases": [], "example_note": notes.iloc[0], "silhouette": None}]

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", min_df=3, sublinear_tf=True)
    matrix = vectorizer.fit_transform(notes)
    fits = []
    for k in K_RANGE:
        model = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(matrix)
        score = silhouette_score(matrix, model.labels_, sample_size=min(1500, len(notes)), random_state=seed)
        fits.append((score, model))
    # Prefer the simplest split that is nearly as clean as the best one.
    top = max(score for score, _ in fits)
    score, model = next(fit for fit in fits if fit[0] >= top - SIMPLER_SPLIT_TOLERANCE)

    order = np.argsort(-np.bincount(model.labels_))
    rank = {old: new for new, old in enumerate(order)}
    labels = np.array([rank[label] for label in model.labels_])
    terms = vectorizer.get_feature_names_out()
    overall = np.asarray(matrix.mean(axis=0)).ravel()
    distance = model.transform(matrix)
    described = []
    for old in order:
        members = np.flatnonzero(model.labels_ == old)
        nearest = members[distance[members, old].argmin()]
        described.append({
            "key_phrases": _key_phrases(model.cluster_centers_[old], overall, terms),
            "example_note": notes.iloc[nearest],
            "silhouette": round(float(score), 3),
        })
    return labels, described


def cluster_all(pended: pd.DataFrame, seed: int) -> tuple[pd.Series, dict, dict]:
    """Clusters every theme. Returns (cluster_id per claim, cluster catalogue, quality report)."""
    cluster_id = pd.Series(None, index=pended.index, dtype=object)
    catalogue: dict[str, dict] = {}
    quality: list[dict] = []
    for theme, group in pended[pended.predicted_theme != NEEDS_REVIEW].groupby("predicted_theme"):
        labels, described = cluster_theme(group.adjuster_note, seed)
        ids = [f"{theme}:{label + 1}" for label in labels]
        cluster_id.loc[group.index] = ids
        for i, info in enumerate(described):
            catalogue[f"{theme}:{i + 1}"] = {"theme": theme, **info}
        quality.append({
            "theme": theme,
            "clusters": len(described),
            "planted_sub_causes": len(THEME_BY_KEY[theme].sub_causes),
            # Agreement with the planted sub-causes; measurable only on synthetic data.
            "adjusted_rand_index": round(float(adjusted_rand_score(group.true_sub_cause, labels)), 3),
        })
    return cluster_id, catalogue, {"per_theme": quality}
