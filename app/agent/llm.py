"""Minimal client for an OpenAI-compatible chat completions endpoint."""
from __future__ import annotations

import httpx

from app.config import Settings


class LLMError(RuntimeError):
    pass


class ChatClient:
    def __init__(self, cfg: Settings):
        self._url = f"{cfg.llm_base_url}/chat/completions"
        self._model = cfg.llm_model
        self._headers = {"Authorization": f"Bearer {cfg.llm_api_key}"} if cfg.llm_api_key else {}
        self._timeout = cfg.llm_timeout_s

    def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        """Returns the assistant message (which may contain tool calls)."""
        payload = {"model": self._model, "messages": messages, "tools": tools,
                   "tool_choice": "auto", "temperature": 0.1}
        try:
            response = httpx.post(self._url, json=payload, headers=self._headers, timeout=self._timeout)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"{type(exc).__name__}: {exc}") from exc
