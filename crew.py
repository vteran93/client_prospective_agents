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
from unidecode import unidecode

from agents.context_agent import ContextAgent
from agents.enrichment_agent import EnrichmentAgent
from agents.maps_agent import MapsAgent
from agents.output_agent import OutputAgent
from agents.profiler_agent import ProfilerAgent
from agents.qualifier_agent import QualifierAgent
from agents.query_generator_agent import QueryGeneratorAgent
from agents.route_agent import RouteAgent
from agents.scraper_agent import ScraperAgent
from agents.search_agent import SearchAgent
from agents.visit_timing_agent import VisitTimingAgent
from config import AppSettings
from llm_factory import get_llm
from models import (
    BusinessSummary,
    EnrichedLead,
    ProfiledLead,
    QualifiedLead,
    RawLead,
    RoutePlan,
    RunReport,
    SearchConfig,
    VisitTiming,
)

console = Console()


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
        auto_generated_queries: list[str] = []
        business_summary: BusinessSummary | None = None
        leads_per_iter: list[int] = []
        error_log: list[dict[str, str]] = []
        iterations = 0

        target = self.config.qualification.target_hot_warm
        max_leads = self.config.max_leads
        max_iters = self.config.max_iterations
        qualified: list[QualifiedLead] = []
        route_plan: RoutePlan | None = None

        # ── PASO 0: Auto-generación de queries (EP-7) ──────────
        if self.config.business_context:
            console.rule("[bold magenta]Paso 0 · Auto Query Generation")
            manual_queries = list(self.config.queries)
            business_summary = ContextAgent.process(
                self.config, self.settings, self.llm
            )
            self.config.queries = QueryGeneratorAgent.process(
                business_summary,
                self.config,
                self.llm,
            )
            manual_keys = {_normalize_query(q) for q in manual_queries}
            auto_generated_queries = [
                q for q in self.config.queries if _normalize_query(q) not in manual_keys
            ]
            console.print(
                f"[magenta]  🧠 Queries auto-generadas: {len(auto_generated_queries)}"
            )

        for iteration in range(1, max_iters + 1):
            iterations = iteration
            console.rule(f"[bold cyan]Iteración {iteration}/{max_iters}")

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

            # Cap to max_leads before expensive LLM steps
            if len(enriched) > max_leads:
                enriched = enriched[:max_leads]
                console.print(
                    f"[dim]  ✂ Leads recortados a {max_leads} antes de profiling"
                )

            # ── PASO 5+6: Timing + Profiler (parallel) ─────────────
            timing_map, profiled = self._run_timing_and_profiling(enriched)

            # Merge timing into profiled leads
            _apply_timing(profiled, timing_map)

            # ── PASO 7: Qualify ────────────────────────────────────
            qualified = self._run_qualifier(profiled)

            # ── Checkpoint: save intermediate results after each iteration
            self._save_checkpoint(qualified, iteration)

            total_unique = len(qualified)
            hot_warm = sum(1 for l in qualified if l.tier in ("HOT", "WARM"))
            console.print(
                f"  [bold]Leads: {total_unique}/{max_leads} · "
                f"HOT+WARM: {hot_warm}/{target}[/bold]"
            )

            if total_unique >= max_leads:
                console.print("[green]  ✓ max_leads alcanzado — saliendo del loop")
                break

            if hot_warm >= target:
                console.print(
                    "[green]  ✓ Target HOT+WARM alcanzado — saliendo del loop"
                )
                break

            if iteration < max_iters:
                console.print(
                    f"[yellow]  ↩ Leads {total_unique}/{max_leads}, "
                    f"HOT+WARM {hot_warm}/{target}. Próxima iteración..."
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

        if self.config.route_planning and self.config.route_planning.enabled:
            try:
                route_plan = RouteAgent.process(
                    qualified,
                    self.config,
                    self.settings,
                )
            except Exception as exc:  # noqa: BLE001
                error_log.append(
                    {
                        "step": "route_planning",
                        "message": str(exc),
                    }
                )
                console.print(f"[yellow]⚠ RouteAgent falló y será omitido: {exc}")

        excel_path = OutputAgent.process(
            qualified,
            report,
            self.config,
            self.settings,
            business_summary=business_summary,
            auto_generated_queries=auto_generated_queries,
            route_plan=route_plan,
        )

        self._persist_to_db(qualified, report, excel_path)

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
            profiler_f = executor.submit(
                ProfilerAgent.process,
                enriched,
                self.llm,
                self.config.business_context,
            )
            return timing_f.result(), profiler_f.result()

    def _run_qualifier(self, profiled: list[ProfiledLead]) -> list[QualifiedLead]:
        return QualifierAgent.process(profiled, self.config, self.llm)

    def _save_checkpoint(self, leads: list[QualifiedLead], iteration: int) -> None:
        """Persist a JSON checkpoint after each qualifying step."""
        import json
        from pathlib import Path

        checkpoint_path = Path("output") / f"checkpoint_iter{iteration}.json"
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        data = [
            {
                "name": l.name,
                "tier": l.tier,
                "final_score": l.final_score,
                "contact_priority": l.contact_priority,
                "phone": l.phone,
                "address": l.address,
                "source": l.source,
            }
            for l in leads
        ]
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        console.print(f"[dim]  💾 Checkpoint → {checkpoint_path}[/dim]")

    def _persist_to_db(
        self,
        leads: list[QualifiedLead],
        report: RunReport,
        excel_path: str,
    ) -> None:
        from tools.db_tool import save_campaign_leads

        try:
            campaign_id = save_campaign_leads(
                leads=leads,
                report=report,
                city=self.config.city,
                country=self.config.country,
                excel_path=excel_path,
                config_snapshot=self.config.model_dump(mode="json"),
            )
            console.print(
                f"[green]  💾 {len(leads)} leads guardados en DB "
                f"(campaign_id={campaign_id})"
            )
        except Exception as exc:  # noqa: BLE001
            console.print(f"[yellow]  ⚠ DB persist falló (no crítico): {exc}")


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


def _normalize_query(text: str) -> str:
    return " ".join(unidecode(text).lower().split())
