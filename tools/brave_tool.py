"""
tools/brave_tool.py — Brave Search API tool.

Docs: https://api.search.brave.com/app/documentation/web-search/get-started
Rate limits: 1 req/sec (free) / 20 req/sec (paid). We enforce 1.1 s gap to be safe.
Handles 429 with automatic exponential back-off (max 3 retries).
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
from crewai.tools import BaseTool
from pydantic import Field


_BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
_MIN_INTERVAL = 1.1  # seconds between requests
_MAX_RETRIES = 3


class BraveSearchTool(BaseTool):
    name: str = "brave_search"
    description: str = (
        "Search the web using Brave Search API. "
        "Input: a plain-text query string. "
        "Output: JSON array of {url, title, snippet} objects."
    )
    api_key: str = Field(default="", exclude=True)
    count: int = Field(default=10)
    country: str = Field(default="co")
    search_lang: str = Field(default="es")
    _last_call_ts: float = 0.0

    def _run(self, query: str) -> str:  # type: ignore[override]
        self._rate_limit()
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.api_key,
        }
        params: dict[str, Any] = {
            "q": query,
            "count": self.count,
            "country": self.country,
            "search_lang": self.search_lang,
            "result_filter": "web",
        }

        for attempt in range(_MAX_RETRIES):
            try:
                with httpx.Client(timeout=15) as client:
                    resp = client.get(_BRAVE_SEARCH_URL, headers=headers, params=params)

                if resp.status_code == 429:
                    wait = 2 ** (attempt + 1)
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                data = resp.json()
                break
            except httpx.HTTPError as exc:  # noqa: BLE001
                if attempt == _MAX_RETRIES - 1:
                    return json.dumps({"error": str(exc), "results": []})
                time.sleep(2 ** (attempt + 1))
        else:
            return json.dumps({"error": "Max retries exceeded", "results": []})

        results = [
            {
                "url": item.get("url", ""),
                "title": item.get("title", ""),
                "snippet": item.get("description", ""),
            }
            for item in data.get("web", {}).get("results", [])
        ]
        return json.dumps(results, ensure_ascii=False)

    def _rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_call_ts
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        self._last_call_ts = time.monotonic()
