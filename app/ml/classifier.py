"""Delay-theme classifier.

Reads what an adjuster wrote plus the pend code and assigns one of the delay
themes. It learns from a small labelled seed, the equivalent of a subject
matter expert tagging a sample of pended claims, and is scored on a held-out
quarter of that seed. Predictions under the confidence floor are not forced
into a theme; they are routed to "needs human review".
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline, make_pipeline

from app.domain import GENERIC_PEND_CODE, NEEDS_REVIEW, THEME_BY_CODE, THEMES


def to_text(notes: pd.Series, codes: pd.Series) -> pd.Series:
    """One document per claim: the note plus the pend code as a single token."""
    return notes.fillna("") + " pendcode_" + codes.fillna("none").str.replace("-", "_").str.lower()


def _model() -> Pipeline:
    return make_pipeline(
        TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=2),
        LogisticRegression(C=10.0, max_iter=2000),
    )


def train_and_classify(pended: pd.DataFrame, seed_size: int, min_confidence: float, seed: int):
    """Returns (predicted_theme, confidence, report) for every pended claim."""
    text = to_text(pended.adjuster_note, pended.pend_code)
    labelled = pended.sample(n=min(seed_size, len(pended)), random_state=seed).index
    x_train, x_test, y_train, y_test = train_test_split(
        text.loc[labelled], pended.true_theme.loc[labelled],
        test_size=0.25, random_state=seed, stratify=pended.true_theme.loc[labelled])

    held_out = _model().fit(x_train, y_train)
    predicted = held_out.predict(x_test)
    labels = [t.key for t in THEMES]
    precision, recall, _, support = precision_recall_fscore_support(
        y_test, predicted, labels=labels, zero_division=0)

    final = _model().fit(text.loc[labelled], pended.true_theme.loc[labelled])
    proba = final.predict_proba(text)
    confidence = proba.max(axis=1)
    theme = np.where(confidence >= min_confidence, final.classes_[proba.argmax(axis=1)], NEEDS_REVIEW)

    unlabelled = ~pended.index.isin(labelled)
    assigned = unlabelled & (theme != NEEDS_REVIEW)
    code_theme = pended.pend_code.map(lambda c: THEME_BY_CODE[c].key if c in THEME_BY_CODE else None)
    report = {
        "pended_claims": int(len(pended)),
        "labelled_seed": int(len(labelled)),
        "train_size": int(len(x_train)),
        "test_size": int(len(x_test)),
        "holdout_accuracy": round(float(accuracy_score(y_test, predicted)), 4),
        "holdout_macro_f1": round(float(f1_score(y_test, predicted, average="macro")), 4),
        "per_theme": [
            {"theme": k, "precision": round(float(p), 3), "recall": round(float(r), 3), "support": int(s)}
            for k, p, r, s in zip(labels, precision, recall, support)
        ],
        "confusion": {"labels": labels, "matrix": confusion_matrix(y_test, predicted, labels=labels).tolist()},
        "min_confidence": min_confidence,
        "auto_classified_share": round(float((theme != NEEDS_REVIEW).mean()), 4),
        "needs_review_share": round(float((theme == NEEDS_REVIEW).mean()), 4),
        # Possible only because the data is synthetic and the true cause is known.
        "accuracy_on_unlabelled_assigned": round(float(
            (theme[assigned] == pended.true_theme.to_numpy()[assigned]).mean()), 4),
        # What operations can see today from pend codes alone.
        "generic_code_share": round(float((pended.pend_code == GENERIC_PEND_CODE).mean()), 4),
        "code_only_correct_share": round(float((code_theme == pended.true_theme).mean()), 4),
    }
    return theme, confidence, report
