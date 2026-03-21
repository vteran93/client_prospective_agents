"""
tools/duckduckgo_tool.py — DuckDuckGo search tool (no API key required).

Uses the duckduckgo-search library (DDGS). Good for local development
and testing without spending API credits.
"""

from __future__ import annotations

import json
import time

from crewai.tools import BaseTool
from pydantic import Field


class DuckDuckGoSearchTool(BaseTool):
    name: str = "duckduckgo_search"
    description: str = (
        "Search the web using DuckDuckGo (no API key required). "
        "Input: a plain-text query string. "
        "Output: JSON array of {url, title, snippet} objects."
    )
    max_results: int = Field(default=10)
    region: str = Field(default="co-es")  # Colombia, Spanish
    _last_call_ts: float = 0.0
    _min_interval: float = 1.0

    def _run(self, query: str) -> str:  # type: ignore[override]
        self._rate_limit()
        try:
            from duckduckgo_search import DDGS  # lazy import

            results = []
            with DDGS() as ddgs:
                for item in ddgs.text(
                    query,
                    region=self.region,
                    max_results=self.max_results,
                ):
                    results.append(
                        {
                            "url": item.get("href", ""),
                            "title": item.get("title", ""),
                            "snippet": item.get("body", ""),
                        }
                    )
            return json.dumps(results, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc), "results": []})

    def _rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_call_ts
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call_ts = time.monotonic()
