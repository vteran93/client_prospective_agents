"""
crew.py — ProspectingCrew: the main pipeline orchestrator.

Flow (each numbered step = an agent or tool execution):
  1. SearchAgent     — web search via Tavily / Brave / DuckDuckGo
  2. MapsAgent       — Google Places API
  3. ScraperAgent    — concurrent website scraping
  4. EnrichmentAgent — LLM enrichment + deduplication
  5. VisitTimingAgent — LLM timing analysis (+ Playwright for popular_times)
  6. ProfilerAgent   — LLM commercial profiling (Hormozi / Challenger / Cardone)
  7. QualifierAgent  — LLM final scoring + tiering
  8. OutputAgent     — Excel export

Steps 1+2 run in parallel via ThreadPoolExecutor.
Steps 5+6 run in parallel (both read from enriched leads, produce separate outputs).
The loop retries up to 3 times until target_hot_warm leads are achieved.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Sequence

from langchain_core.language_models import BaseChatModel
from rich.console import Console

from agents.enrichment_agent import EnrichmentAgent
from agents.maps_agent import MapsAgent
from agents.output_agent import OutputAgent
from agents.profiler_agent import ProfilerAgent
from agents.qualifier_agent import QualifierAgent
from agents.scraper_agent import ScraperAgent
from agents.search_agent import SearchAgent
from agents.visit_timing_agent import VisitTimingAgent
from config import AppSettings
from llm_factory import get_llm
from models import (
    EnrichedLead,
    ProfiledLead,
    QualifiedLead,
    RawLead,
    RunReport,
    SearchConfig,
    VisitTiming,
)

console = Console()

_MAX_ITERATIONS = 3


class ProspectingCrew:
    """
    Main pipeline that takes a SearchConfig and produces a list of QualifiedLeads
    plus a RunReport, then exports to Excel.
    """

    def __init__(self, config: SearchConfig, settings: AppSettings) -> None:
        self.config = config
        self.settings = settings
        self.llm: BaseChatModel = get_llm(settings, provider=config.llm_provider)

    # ──────────────────────────────────────────────────────────────
    # Entry point
    # ──────────────────────────────────────────────────────────────

    def run(self) -> tuple[list[QualifiedLead], RunReport]:
        start_time = time.monotonic()

        all_raw: list[RawLead] = []
        leads_per_iter: list[int] = []
        error_log: list[dict[str, str]] = []
        iterations = 0

        target = self.config.qualification.target_hot_warm
        qualified: list[QualifiedLead] = []

        for iteration in range(1, _MAX_ITERATIONS + 1):
            iterations = iteration
            console.rule(f"[bold cyan]Iteración {iteration}/{_MAX_ITERATIONS}")

            # ── PASO 1+2: Search + Maps (parallel) ─────────────────
            new_search, new_maps = self._run_discovery(all_raw)
            batch = new_search + new_maps
            all_raw.extend(batch)
            leads_per_iter.append(len(batch))
            console.print(f"  Nuevos leads esta iteración: {len(batch)}")

            if not all_raw:
                console.print(
                    "[yellow]  ⚠ No se encontraron leads. Verifica las queries y fuentes."
                )
                break

            # ── PASO 3: Scrape ─────────────────────────────────────
            if self.config.scrape_websites:
                all_raw = self._run_scraper(all_raw)

            # ── PASO 4: Enrich + Dedup ─────────────────────────────
            enriched = self._run_enrichment(all_raw)

            # ── PASO 5+6: Timing + Profiler (parallel) ─────────────
            timing_map, profiled = self._run_timing_and_profiling(enriched)

            # Merge timing into profiled leads
            _apply_timing(profiled, timing_map)

            # ── PASO 7: Qualify ────────────────────────────────────
            qualified = self._run_qualifier(profiled)

            hot_warm = sum(1 for l in qualified if l.tier in ("HOT", "WARM"))
            console.print(f"  [bold]HOT+WARM: {hot_warm} / target: {target}[/bold]")

            if hot_warm >= target:
                console.print("[green]  ✓ Target alcanzado — saliendo del loop")
                break

            if iteration < _MAX_ITERATIONS:
                console.print(
                    f"[yellow]  ↩ No se alcanzó el target ({hot_warm}/{target}). "
                    "Generando nuevas queries en la próxima iteración..."
                )

        # ── PASO 8: Output ──────────────────────────────────────────
        enriched_count = len(qualified)  # after dedup
        report = RunReport(
            campaign_name=self.config.campaign_name,
            total_raw=len(all_raw),
            total_after_dedup=enriched_count,
            hot_count=sum(1 for l in qualified if l.tier == "HOT"),
            warm_count=sum(1 for l in qualified if l.tier == "WARM"),
            cold_count=sum(1 for l in qualified if l.tier == "COLD"),
            sources_breakdown=_count_sources(all_raw),
            duration_seconds=round(time.monotonic() - start_time, 2),
            iterations=iterations,
            leads_per_iteration=leads_per_iter,
            error_log=error_log,
        )

        OutputAgent.process(qualified, report, self.config, self.settings)
        return qualified, report

    # ──────────────────────────────────────────────────────────────
    # Pipeline steps
    # ──────────────────────────────────────────────────────────────

    def _run_discovery(
        self,
        existing: list[RawLead],
    ) -> tuple[list[RawLead], list[RawLead]]:
        with ThreadPoolExecutor(max_workers=2) as executor:
            search_f = executor.submit(
                SearchAgent.process, self.config, self.settings, self.llm, existing
            )
            maps_f = executor.submit(MapsAgent.process, self.config, self.settings)
            return search_f.result(), maps_f.result()

    def _run_scraper(self, leads: list[RawLead]) -> list[RawLead]:
        return ScraperAgent.process(
            leads, self.config.scraper_concurrency, self.settings
        )

    def _run_enrichment(self, leads: list[RawLead]) -> list[EnrichedLead]:
        return EnrichmentAgent.process(leads, self.llm)

    def _run_timing_and_profiling(
        self,
        enriched: list[EnrichedLead],
    ) -> tuple[dict[str, VisitTiming], list[ProfiledLead]]:
        with ThreadPoolExecutor(max_workers=2) as executor:
            timing_f = executor.submit(
                VisitTimingAgent.process, enriched, self.llm, self.settings
            )
            profiler_f = executor.submit(ProfilerAgent.process, enriched, self.llm)
            return timing_f.result(), profiler_f.result()

    def _run_qualifier(self, profiled: list[ProfiledLead]) -> list[QualifiedLead]:
        return QualifierAgent.process(profiled, self.config, self.llm)


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────


def _apply_timing(
    leads: list[ProfiledLead],
    timing_map: dict[str, VisitTiming],
) -> None:
    """Merge timing data into each ProfiledLead in-place."""
    for lead in leads:
        key = lead.place_id or lead.name
        if key in timing_map:
            lead.visit_timing = timing_map[key]


def _count_sources(leads: Sequence[RawLead]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for lead in leads:
        counts[lead.source] = counts.get(lead.source, 0) + 1
    return counts
