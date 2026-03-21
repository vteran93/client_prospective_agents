"""
agents/search_agent.py — Searches the web via Tavily / Brave / DuckDuckGo.

Responsibilities:
  1. Use the LLM to expand the base queries from search_config.yaml into
     3-5 variations per query (synonyms, related terms).
  2. Run each query against the configured search source(s).
  3. Parse results into RawLead objects.
  4. Skip leads already in the existing_leads list (URL / name dedup).
"""

from __future__ import annotations

import json
import re
from typing import Sequence

from langchain_core.language_models import BaseChatModel
from rich.console import Console

from config import AppSettings
from models import RawLead, SearchConfig

console = Console()

_URL_RE = re.compile(r"https?://(?:www\.)?([^/\s]+)")


class SearchAgent:
    """Orchestrates multi-source web search and returns RawLead objects."""

    def __init__(
        self,
        config: SearchConfig,
        settings: AppSettings,
        llm: BaseChatModel,
    ) -> None:
        self.config = config
        self.settings = settings
        self.llm = llm

    # ──────────────────────────────────────────────────────────────
    # Class-level factory for use in crew.py
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def process(
        cls,
        config: SearchConfig,
        settings: AppSettings,
        llm: BaseChatModel,
        existing_leads: Sequence[RawLead] | None = None,
    ) -> list[RawLead]:
        agent = cls(config, settings, llm)
        return agent.run(existing_leads or [])

    # ──────────────────────────────────────────────────────────────
    # Main entry point
    # ──────────────────────────────────────────────────────────────

    def run(self, existing_leads: Sequence[RawLead]) -> list[RawLead]:
        existing_urls: set[str] = {
            _domain(l.website) for l in existing_leads if l.website
        }
        existing_names: set[str] = {_norm(l.name) for l in existing_leads if l.name}

        expanded = self._expand_queries()
        tools = self._build_tools()

        if not tools:
            console.print(
                "[yellow]⚠ SearchAgent: no hay fuentes de búsqueda configuradas"
            )
            return []

        all_leads: list[RawLead] = []
        for query in expanded:
            for tool in tools:
                console.print(f"[dim]  🔍 [{tool.name}] {query[:80]}")
                raw_json = tool._run(query)
                leads = _parse_results(raw_json, source=tool.name)
                for lead in leads:
                    if _domain(lead.website) in existing_urls:
                        continue
                    if lead.name and _norm(lead.name) in existing_names:
                        continue
                    existing_urls.add(_domain(lead.website))
                    existing_names.add(_norm(lead.name))
                    all_leads.append(lead)

        console.print(f"[green]  ✓ SearchAgent: {len(all_leads)} leads encontrados")
        return all_leads

    # ──────────────────────────────────────────────────────────────
    # Query expansion via LLM
    # ──────────────────────────────────────────────────────────────

    def _expand_queries(self) -> list[str]:
        city = self.config.city
        base = self.config.queries

        prompt = (
            f"Genera 3 variaciones de búsqueda para cada una de las siguientes consultas "
            f"orientadas a encontrar empresas en {city}, Colombia. "
            f"Incluye sinónimos y términos relacionados en español. "
            f"Devuelve SOLO un arreglo JSON de strings, sin texto extra.\n\n"
            f"Consultas base: {json.dumps(base, ensure_ascii=False)}"
        )

        try:
            response = self.llm.invoke(prompt)
            content = (
                response.content if hasattr(response, "content") else str(response)
            )
            # Extract the JSON array
            match = re.search(r"\[.*\]", content, re.DOTALL)
            if match:
                variations: list[str] = json.loads(match.group())
                # Prepend originals to ensure coverage, deduplicate
                all_queries = list(dict.fromkeys(base + variations))
                console.print(f"[dim]  📝 Queries expandidas: {len(all_queries)}")
                return all_queries
        except Exception as exc:  # noqa: BLE001
            console.print(f"[yellow]  ⚠ LLM query expansion fallback: {exc}")

        return list(base)

    # ──────────────────────────────────────────────────────────────
    # Tool instantiation based on config.sources
    # ──────────────────────────────────────────────────────────────

    def _build_tools(self) -> list:
        from tools.tavily_tool import TavilySearchTool
        from tools.brave_tool import BraveSearchTool
        from tools.duckduckgo_tool import DuckDuckGoSearchTool

        tools = []
        for source in self.config.sources:
            if source == "tavily" and self.settings.tavily_api_key:
                tools.append(TavilySearchTool(api_key=self.settings.tavily_api_key))
            elif source == "brave" and self.settings.brave_api_key:
                tools.append(BraveSearchTool(api_key=self.settings.brave_api_key))
            elif source == "duckduckgo":
                tools.append(DuckDuckGoSearchTool())
        return tools


# ──────────────────────────────────────────────────────────────────
# Parsing helpers
# ──────────────────────────────────────────────────────────────────


def _parse_results(raw_json: str, source: str) -> list[RawLead]:
    """Convert a tool's JSON output into RawLead objects."""
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return []

    if isinstance(data, dict) and "error" in data:
        return []

    results = data if isinstance(data, list) else data.get("results", [])
    leads: list[RawLead] = []

    for item in results:
        url = item.get("url", "")
        title = item.get("title", "")
        snippet = item.get("snippet", "")

        # Filter out obvious non-business results
        skip_domains = ("wikipedia", "facebook.com/events", "youtube", "maps.google")
        if any(d in url for d in skip_domains):
            continue

        leads.append(
            RawLead(
                source=source,
                name=title[:120],
                website=url,
                raw_snippet=snippet[:500],
            )
        )

    return leads


def _domain(url: str) -> str:
    m = _URL_RE.match(url)
    return m.group(1).lower() if m else ""


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())
