"""Build step: generate claims, classify delay themes, cluster root causes.

Run with `python -m app.pipeline`. The API runs it automatically on first
start if the output files are missing.
"""
from __future__ import annotations

import json
import logging
import time

from app.config import Settings, settings
from app.data.generator import generate
from app.ml.classifier import train_and_classify
from app.ml.clustering import cluster_all

log = logging.getLogger("cde.pipeline")


def run(cfg: Settings = settings) -> dict:
    started = time.perf_counter()
    cfg.data_dir.mkdir(parents=True, exist_ok=True)

    claims = generate(cfg)
    claims.to_csv(cfg.claims_path, index=False)
    log.info("generated %s claims, %s pended", f"{len(claims):,}", f"{int(claims.pended.sum()):,}")

    pended = claims[claims.pended].copy()
    theme, confidence, classifier_report = train_and_classify(
        pended, cfg.labelled_seed_size, cfg.min_confidence, cfg.seed)
    pended["predicted_theme"] = theme
    pended["confidence"] = confidence.round(4)
    log.info("classifier hold-out accuracy %.1f%%", classifier_report["holdout_accuracy"] * 100)

    cluster_id, catalogue, cluster_report = cluster_all(pended, cfg.seed)
    pended["cluster_id"] = cluster_id

    enriched = claims.join(pended[["predicted_theme", "confidence", "cluster_id"]])
    enriched.to_csv(cfg.enriched_path, index=False)

    report = {
        "window": {"start": cfg.window_start.isoformat(), "end": cfg.window_end.isoformat(),
                   "as_of": cfg.as_of.isoformat(), "seed": cfg.seed},
        "classifier": classifier_report,
        "clustering": cluster_report,
        "clusters": catalogue,
        "build_seconds": round(time.perf_counter() - started, 1),
    }
    cfg.model_report_path.write_text(json.dumps(report, indent=2))
    log.info("pipeline finished in %.1fs", report["build_seconds"])
    return report


def main() -> None:
    import argparse
    from datetime import date

    parser = argparse.ArgumentParser(description="Build the synthetic claims data set.")
    parser.add_argument("--start", type=date.fromisoformat, default=settings.window_start,
                        help="first receipt date, YYYY-MM-DD")
    parser.add_argument("--end", type=date.fromisoformat, default=settings.window_end,
                        help="last receipt date, YYYY-MM-DD")
    parser.add_argument("--seed", type=int, default=None, help="random seed; change it for a different draw")
    args = parser.parse_args()
    try:
        cfg = settings.with_window(args.start, args.end, args.seed)
    except ValueError as exc:
        parser.error(str(exc))

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    result = run(cfg)
    c = result["classifier"]
    print(f"{cfg.window_start} to {cfg.window_end} | hold-out accuracy {c['holdout_accuracy']:.1%} | "
          f"needs review {c['needs_review_share']:.1%} | built in {result['build_seconds']}s")


if __name__ == "__main__":
    main()
