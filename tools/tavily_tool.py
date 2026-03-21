"""
tools/tavily_tool.py — Tavily AI-optimised search tool.

Rate limit: 5 requests/second (enforced via internal sleep).
Filters results with Tavily relevance score < 0.5.
"""

from __future__ import annotations

import json
import time
from typing import Any

from crewai.tools import BaseTool
from pydantic import Field


class TavilySearchTool(BaseTool):
    name: str = "tavily_search"
    description: str = (
        "Search the web using Tavily AI-optimised search API. "
        "Input: a plain-text query string. "
        "Output: JSON array of {url, title, snippet, score} objects sorted by relevance."
    )
    api_key: str = Field(default="", exclude=True)
    max_results: int = Field(default=10)
    min_score: float = Field(default=0.5)
    _last_call_ts: float = 0.0
    _min_interval: float = 0.2  # 5 req/sec

    def _run(self, query: str) -> str:  # type: ignore[override]
        self._rate_limit()
        try:
            from tavily import TavilyClient  # lazy import

            client = TavilyClient(api_key=self.api_key)
            response: dict[str, Any] = client.search(
                query,
                max_results=self.max_results,
                search_depth="advanced",
            )
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc), "results": []})

        results = [
            {
                "url": r.get("url", ""),
                "title": r.get("title", ""),
                "snippet": r.get("content", ""),
                "score": r.get("score", 0),
            }
            for r in response.get("results", [])
            if r.get("score", 0) >= self.min_score
        ]
        return json.dumps(results, ensure_ascii=False)

    # ------------------------------------------------------------------
    def _rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_call_ts
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call_ts = time.monotonic()
