"""
agents/enrichment_agent.py — LLM-powered lead enrichment + deduplication.

Responsibilities:
  1. Deduplicate the raw lead list using DedupTool.
  2. For each lead, call the LLM to generate interpretive enrichment fields:
       lead_summary, estimated_size, main_sector, digital_maturity, sales_opportunity.
  3. Extract and merge scraped data (stored in raw_snippet) into EnrichedLead fields.
  4. Return list[EnrichedLead].
"""

from __future__ import annotations

import json
import re
from typing import Sequence

from langchain_core.language_models import BaseChatModel
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from models import EnrichedLead, EnrichmentLLMOutput, RawLead
from prompts.enrichment_prompt import build_enrichment_messages
from tools.dedup_tool import deduplicate_leads

console = Console()

_SCRAPED_RE = re.compile(r"\[scraped\](.*?)\[/scraped\]", re.DOTALL)
_CO_MOBILE_RE = re.compile(r"(?:\+?57\s*)?3\d{2}[\s\-]?\d{3}[\s\-]?\d{4}")


class EnrichmentAgent:
    """Enriches a list of RawLeads into EnrichedLeads via LLM + dedup."""

    @classmethod
    def process(
        cls,
        leads: Sequence[RawLead],
        llm: BaseChatModel,
    ) -> list[EnrichedLead]:
        agent = cls(llm)
        return agent.run(list(leads))

    def __init__(self, llm: BaseChatModel) -> None:
        self.llm = llm

    # ──────────────────────────────────────────────────────────────

    def run(self, leads: list[RawLead]) -> list[EnrichedLead]:
        # Step 1: Dedup
        deduped = deduplicate_leads(leads)
        console.print(
            f"[cyan]  🧹 EnrichmentAgent: {len(leads)} → {len(deduped)} leads tras dedup"
        )

        enriched: list[EnrichedLead] = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            transient=True,
        ) as progress:
            task_id = progress.add_task("Enriqueciendo leads...", total=len(deduped))

            for raw_lead in deduped:
                el = _to_enriched_lead(raw_lead)
                el = self._llm_enrich(el)
                enriched.append(el)
                progress.advance(task_id)

        console.print(f"[green]  ✓ EnrichmentAgent: {len(enriched)} leads enriquecidos")
        return enriched

    # ──────────────────────────────────────────────────────────────

    def _llm_enrich(self, lead: EnrichedLead) -> EnrichedLead:
        """Call LLM to fill interpretive fields on the lead."""
        lead_dict = {
            "name": lead.name,
            "address": lead.address,
            "website": lead.website,
            "phone": lead.phone,
            "email": lead.email,
            "rating": lead.rating,
            "reviews_count": lead.reviews_count,
            "has_whatsapp": lead.has_whatsapp,
            "technology_stack": lead.technology_stack,
            "social_links": lead.social_links,
            "description_from_scrape": lead.lead_summary,  # pre-filled from raw
            "snippet": lead.raw_snippet[:600] if lead.raw_snippet else "",
        }

        messages = build_enrichment_messages(json.dumps(lead_dict, ensure_ascii=False))

        try:
            structured_llm = self.llm.with_structured_output(EnrichmentLLMOutput)
            result: EnrichmentLLMOutput = structured_llm.invoke(messages)
            lead.lead_summary = result.lead_summary
            lead.estimated_size = result.estimated_size
            lead.main_sector = result.main_sector
            lead.digital_maturity = result.digital_maturity
            lead.sales_opportunity = result.sales_opportunity
        except Exception:  # noqa: BLE001 — fallback: parse raw JSON from text
            try:
                response = self.llm.invoke(messages)
                content = (
                    response.content if hasattr(response, "content") else str(response)
                )
                data = _extract_json(content)
                if data:
                    lead.lead_summary = data.get("lead_summary", "")
                    lead.estimated_size = data.get("estimated_size", "")
                    lead.main_sector = data.get("main_sector", "")
                    lead.digital_maturity = data.get("digital_maturity", "")
                    lead.sales_opportunity = data.get("sales_opportunity", "")
            except Exception:  # noqa: BLE001
                pass  # Leave fields empty — better than crashing

        return lead


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────


def _to_enriched_lead(raw: RawLead) -> EnrichedLead:
    """Promote a RawLead to EnrichedLead, extracting [scraped] blob if present."""
    data = raw.model_dump()

    # Extract scraped blob from raw_snippet
    scraped_data: dict = {}
    match = _SCRAPED_RE.search(raw.raw_snippet or "")
    if match:
        try:
            scraped_data = json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
        # Clean the blob from raw_snippet
        data["raw_snippet"] = _SCRAPED_RE.sub("", raw.raw_snippet or "").strip()

    el = EnrichedLead(**data)
    if scraped_data:
        el.emails_scraped = scraped_data.get("emails", [])
        el.phones_scraped = scraped_data.get("phones", [])
        el.has_whatsapp = scraped_data.get("has_whatsapp", False)
        el.whatsapp_number = scraped_data.get("whatsapp_number", "")
        el.technology_stack = scraped_data.get("technology_stack", [])
        el.social_links = {**el.social_links, **scraped_data.get("social_links", {})}
        # Use scrape description as initial summary
        if not el.lead_summary:
            el.lead_summary = scraped_data.get("description", "")[:300]

    el.merge_sources = [raw.source]
    _derive_whatsapp(el)
    return el


def _derive_whatsapp(lead: EnrichedLead) -> None:
    if lead.has_whatsapp and lead.whatsapp_number:
        return
    phones = [lead.phone] + list(lead.phones_scraped or [])
    for phone in phones:
        if not phone:
            continue
        if _CO_MOBILE_RE.search(phone):
            digits = re.sub(r"\D", "", phone)
            if digits.startswith("57") and len(digits) >= 12:
                lead.whatsapp_number = f"+{digits}"
            elif digits.startswith("3") and len(digits) == 10:
                lead.whatsapp_number = f"+57{digits}"
            else:
                continue
            lead.has_whatsapp = True
            return


def _extract_json(text: str) -> dict | None:
    """Extract first JSON object from an LLM text response."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None
