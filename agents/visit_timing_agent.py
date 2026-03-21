"""
agents/visit_timing_agent.py — LLM-powered visit/call timing recommender.

Responsibilities:
  1. For each EnrichedLead, fetch popular_times via PopularTimesTool
     (only if place_id exists and popular_times list is empty).
  2. Call LLM with the timing prompt to produce a VisitTiming object.
  3. Return a dict keyed by lead name/place_id → VisitTiming.

The resulting timing data is merged into ProfiledLeads by crew.py.
"""

from __future__ import annotations

import json
import re
from typing import Sequence

from langchain_core.language_models import BaseChatModel
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from config import AppSettings
from models import EnrichedLead, TimingLLMOutput, VisitTiming
from prompts.visit_timing_prompt import build_timing_messages

console = Console()


class VisitTimingAgent:
    """Recommends optimal visit/call times for each lead using LLM + popular_times data."""

    @classmethod
    def process(
        cls,
        leads: Sequence[EnrichedLead],
        llm: BaseChatModel,
        settings: AppSettings,
    ) -> dict[str, VisitTiming]:
        agent = cls(llm, settings)
        return agent.run(list(leads))

    def __init__(self, llm: BaseChatModel, settings: AppSettings) -> None:
        self.llm = llm
        self.settings = settings

    # ──────────────────────────────────────────────────────────────

    def run(self, leads: list[EnrichedLead]) -> dict[str, VisitTiming]:
        timing_map: dict[str, VisitTiming] = {}

        # Prefetch popular_times for Maps leads that don't already have it
        leads = self._prefetch_popular_times(leads)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            transient=True,
        ) as progress:
            task_id = progress.add_task("Calculando horarios...", total=len(leads))
            for lead in leads:
                timing = self._compute_timing(lead)
                timing_map[_key(lead)] = timing
                progress.advance(task_id)

        console.print(
            f"[green]  ✓ VisitTimingAgent: {len(timing_map)} ventanas calculadas"
        )
        return timing_map

    # ──────────────────────────────────────────────────────────────

    def _prefetch_popular_times(self, leads: list[EnrichedLead]) -> list[EnrichedLead]:
        """Fetch popular_times from Google Maps for leads that don't have it yet."""
        from tools.popular_times_tool import PopularTimesTool

        tool = PopularTimesTool()
        fetched = 0
        for lead in leads:
            if lead.popular_times or not lead.place_id:
                continue
            raw = tool._run(
                json.dumps(
                    {
                        "place_id": lead.place_id,
                        "name": lead.name,
                        "address": lead.address,
                    }
                )
            )
            try:
                data = json.loads(raw)
                if data.get("popular_times"):
                    lead.popular_times = data["popular_times"]
                    fetched += 1
            except (json.JSONDecodeError, KeyError):
                pass
        if fetched:
            console.print(
                f"[dim]    popular_times obtenidos para {fetched} leads via Playwright"
            )
        return leads

    def _compute_timing(self, lead: EnrichedLead) -> VisitTiming:
        """Call LLM to compute best visit/call windows."""
        messages = build_timing_messages(
            name=lead.name,
            sector=lead.main_sector or "",
            address=lead.address,
            opening_hours=lead.opening_hours,
            popular_times=lead.popular_times,
        )

        try:
            structured_llm = self.llm.with_structured_output(TimingLLMOutput)
            result: TimingLLMOutput = structured_llm.invoke(messages)
            return VisitTiming(**result.model_dump())
        except Exception:  # noqa: BLE001 — fallback
            try:
                response = self.llm.invoke(messages)
                content = (
                    response.content if hasattr(response, "content") else str(response)
                )
                data = _extract_json(content)
                if data:
                    return VisitTiming(
                        best_visit_windows=data.get("best_visit_windows", []),
                        best_call_time=data.get("best_call_time", {}),
                        worst_times=data.get("worst_times", []),
                        timing_confidence=data.get("timing_confidence", "inferred"),
                        timing_summary=data.get("timing_summary", ""),
                    )
            except Exception:  # noqa: BLE001
                pass

        return VisitTiming(timing_confidence="inferred")


def _key(lead: EnrichedLead) -> str:
    return lead.place_id or lead.name


def _extract_json(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None
