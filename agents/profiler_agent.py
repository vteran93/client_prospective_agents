"""
agents/profiler_agent.py — LLM-powered commercial profiler.

Applies three sales frameworks to each EnrichedLead:
  1. Hormozi ($100M Leads) — market quality dimensions (0-3 each)
  2. Challenger Sale (SEC) — buyer type & insight
  3. Cardone (Vendes o Vendes) — commitment, objection, entry channel

Returns list[ProfiledLead] with CommercialProfile populated.
"""

from __future__ import annotations

import json
import re
from typing import Sequence

from langchain_core.language_models import BaseChatModel
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from models import CommercialProfile, EnrichedLead, ProfiledLead, ProfilerLLMOutput
from prompts.profiler_prompt import build_profiler_messages

console = Console()


class ProfilerAgent:
    """Generates commercial profiles for enriched leads via LLM."""

    @classmethod
    def process(
        cls,
        leads: Sequence[EnrichedLead],
        llm: BaseChatModel,
    ) -> list[ProfiledLead]:
        agent = cls(llm)
        return agent.run(list(leads))

    def __init__(self, llm: BaseChatModel) -> None:
        self.llm = llm

    # ──────────────────────────────────────────────────────────────

    def run(self, leads: list[EnrichedLead]) -> list[ProfiledLead]:
        profiled: list[ProfiledLead] = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            transient=True,
        ) as progress:
            task_id = progress.add_task("Perfilando leads...", total=len(leads))
            for lead in leads:
                pl = self._profile_one(lead)
                profiled.append(pl)
                progress.advance(task_id)

        console.print(f"[green]  ✓ ProfilerAgent: {len(profiled)} leads perfilados")
        return profiled

    # ──────────────────────────────────────────────────────────────

    def _profile_one(self, lead: EnrichedLead) -> ProfiledLead:
        """Build a ProfiledLead from an EnrichedLead using the LLM profiler."""
        lead_dict = {
            "name": lead.name,
            "address": lead.address,
            "phone": lead.phone,
            "email": lead.email,
            "has_whatsapp": lead.has_whatsapp,
            "website": lead.website,
            "rating": lead.rating,
            "reviews_count": lead.reviews_count,
            "technology_stack": lead.technology_stack,
            "social_links": list(lead.social_links.keys()),
            "estimated_size": lead.estimated_size,
            "main_sector": lead.main_sector,
            "digital_maturity": lead.digital_maturity,
            "lead_summary": lead.lead_summary,
            "sales_opportunity": lead.sales_opportunity,
        }

        messages = build_profiler_messages(json.dumps(lead_dict, ensure_ascii=False))

        profile = CommercialProfile()  # default fallback

        try:
            structured_llm = self.llm.with_structured_output(ProfilerLLMOutput)
            result: ProfilerLLMOutput = structured_llm.invoke(messages)
            profile = CommercialProfile(
                hormozi_urgency=result.hormozi_urgency,
                hormozi_buying_power=result.hormozi_buying_power,
                hormozi_accessibility=result.hormozi_accessibility,
                hormozi_market_fit=result.hormozi_market_fit,
                challenger_buyer_type=result.challenger_buyer_type,
                challenger_awareness=result.challenger_awareness,
                challenger_complexity=result.challenger_complexity,
                challenger_insight=result.challenger_insight,
                cardone_commitment=result.cardone_commitment,
                cardone_objection=result.cardone_objection,
                cardone_followup_est=result.cardone_followup_est,
                cardone_entry_channel=result.cardone_entry_channel,
                cardone_action_line=result.cardone_action_line,
                pitch_hook=result.pitch_hook,
            )
        except Exception:  # noqa: BLE001
            try:
                response = self.llm.invoke(messages)
                content = (
                    response.content if hasattr(response, "content") else str(response)
                )
                data = _extract_json(content)
                if data:
                    profile = _dict_to_profile(data)
            except Exception:  # noqa: BLE001
                pass

        # Promote EnrichedLead → ProfiledLead
        pl_data = lead.model_dump()
        pl_data["profile"] = profile
        return ProfiledLead(**pl_data)


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────


def _dict_to_profile(d: dict) -> CommercialProfile:
    """Build CommercialProfile from an arbitrary dict (LLM raw text fallback)."""

    def _int(key: str, default: int = 0) -> int:
        val = d.get(key, default)
        try:
            return max(0, min(3, int(val)))
        except (TypeError, ValueError):
            return default

    return CommercialProfile(
        hormozi_urgency=_int("hormozi_urgency"),
        hormozi_buying_power=_int("hormozi_buying_power"),
        hormozi_accessibility=_int("hormozi_accessibility"),
        hormozi_market_fit=_int("hormozi_market_fit"),
        challenger_buyer_type=str(d.get("challenger_buyer_type", "unknown")),
        challenger_awareness=str(d.get("challenger_awareness", "unaware")),
        challenger_complexity=str(d.get("challenger_complexity", "simple")),
        challenger_insight=str(d.get("challenger_insight", ""))[:400],
        cardone_commitment=str(d.get("cardone_commitment", "low")),
        cardone_objection=str(d.get("cardone_objection", "desconfianza")),
        cardone_followup_est=str(d.get("cardone_followup_est", "3-5")),
        cardone_entry_channel=str(d.get("cardone_entry_channel", "whatsapp")),
        cardone_action_line=str(d.get("cardone_action_line", ""))[:300],
        pitch_hook=str(d.get("pitch_hook", ""))[:400],
    )


def _extract_json(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None
