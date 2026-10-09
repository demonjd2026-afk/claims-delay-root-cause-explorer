"""Runtime settings, read once from the environment (and an optional .env)."""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


AS_OF_LAG_DAYS = 2
# Rising-theme detection compares 21 days with the 42 before, so 63 is the floor.
MIN_WINDOW_DAYS, MAX_WINDOW_DAYS = 63, 366


@dataclass(frozen=True)
class Settings:
    data_dir: Path = ROOT / "data"
    web_dir: Path = ROOT / "web"

    # Synthetic data window: every calendar day from start to end inclusive.
    # Change it with CDE_START / CDE_END, `python -m app.pipeline --start ... --end ...`,
    # or from the "How it works" tab in the dashboard.
    window_start: date = date.fromisoformat(os.getenv("CDE_START", "2026-07-01"))
    window_end: date = date.fromisoformat(os.getenv("CDE_END", "2026-09-28"))
    seed: int = int(os.getenv("CDE_SEED", "20261009"))

    # Turnaround target used for "over target" counts. 30 days is a common
    # clean-claim prompt-pay reference; set it to the contract or state rule.
    sla_days: int = int(os.getenv("CDE_SLA_DAYS", "30"))

    # Predictions below this probability go to a human instead of a theme.
    min_confidence: float = float(os.getenv("CDE_MIN_CONFIDENCE", "0.55"))
    labelled_seed_size: int = int(os.getenv("CDE_LABELLED_SEED", "1200"))

    # Optional LLM for the AI analyst: any OpenAI-compatible chat endpoint.
    llm_base_url: str = os.getenv("LLM_BASE_URL", "").rstrip("/")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "")
    llm_timeout_s: float = float(os.getenv("LLM_TIMEOUT_S", "45"))

    @property
    def as_of(self) -> date:
        """Status is reported two days after the last receipt date."""
        return self.window_end + timedelta(days=AS_OF_LAG_DAYS)

    def with_window(self, start: date, end: date, seed: int | None = None) -> "Settings":
        days = (end - start).days + 1
        if not MIN_WINDOW_DAYS <= days <= MAX_WINDOW_DAYS:
            raise ValueError(f"Choose between {MIN_WINDOW_DAYS} and {MAX_WINDOW_DAYS} days; this range has {days}.")
        return replace(self, window_start=start, window_end=end, seed=self.seed if seed is None else seed)

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_base_url and self.llm_model)

    @property
    def claims_path(self) -> Path:
        return self.data_dir / "claims.csv.gz"

    @property
    def enriched_path(self) -> Path:
        return self.data_dir / "claims_enriched.csv.gz"

    @property
    def model_report_path(self) -> Path:
        return self.data_dir / "model_report.json"


settings = Settings()
