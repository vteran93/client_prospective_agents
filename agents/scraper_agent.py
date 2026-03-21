"""
agents/scraper_agent.py — Concurrent website scraper for lead enrichment.

Responsibilities:
  1. For each RawLead with a website URL, scrape the site.
  2. Merge scraped data (emails, phones, social links, description) back into the lead.
  3. Run concurrently using ThreadPoolExecutor.
  4. Mark leads as scrape_failed when the site is unreachable.

Returns the same list of RawLeads, mutated in-place with scraped data copied into
the relevant fields (emails_scraped, phones_scraped, etc. are on EnrichedLead;
here we store them in extra fields via model_extra until enrichment).
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Sequence

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from config import AppSettings
from models import RawLead

console = Console()


class ScraperAgent:
    """Concurrent website scraper that enriches RawLead objects."""

    @classmethod
    def process(
        cls,
        leads: Sequence[RawLead],
        concurrency: int,
        settings: AppSettings,  # noqa: ARG003 — reserved for future proxy config
    ) -> list[RawLead]:
        to_scrape = [l for l in leads if l.website]
        no_website = [l for l in leads if not l.website]

        if not to_scrape:
            return list(leads)

        console.print(
            f"[cyan]  🕷  ScraperAgent: scrapeando {len(to_scrape)} sitios (workers={concurrency})"
        )

        results: list[RawLead] = list(no_website)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            task_id = progress.add_task("Scraping...", total=len(to_scrape))

            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = {
                    executor.submit(_scrape_one, lead): lead for lead in to_scrape
                }
                for future in as_completed(futures):
                    lead = futures[future]
                    try:
                        enriched_lead = future.result()
                        results.append(enriched_lead)
                    except Exception as exc:  # noqa: BLE001
                        lead.raw_snippet += f" [scrape_error: {exc}]"
                        results.append(lead)
                    progress.advance(task_id)

        console.print(f"[green]  ✓ ScraperAgent: {len(results)} leads procesados")
        return results


# ──────────────────────────────────────────────────────────────────
# Per-lead scrape
# ──────────────────────────────────────────────────────────────────


def _scrape_one(lead: RawLead) -> RawLead:
    """Scrape lead.website and merge data into the lead."""
    from tools.scraper_tool import WebScraperTool

    tool = WebScraperTool()
    raw = tool._run(lead.website)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        lead.raw_snippet += " [scrape:parse_error]"
        return lead

    if "error" in data:
        lead.raw_snippet += f" [scrape_failed: {data['error'][:60]}]"
        return lead

    # Store scraped data in raw_snippet as JSON annotation for EnrichmentAgent to consume.
    # (RawLead intentionally doesn't have scraped fields — that's EnrichedLead's domain)
    scraped_summary = {
        "emails": data.get("emails", []),
        "phones": data.get("phones", []),
        "has_whatsapp": data.get("has_whatsapp", False),
        "whatsapp_number": data.get("whatsapp_number", ""),
        "social_links": data.get("social_links", {}),
        "description": data.get("description", "")[:300],
        "technology_stack": data.get("technology_stack", []),
    }

    # Prefer scraped phone if lead has none
    if not lead.phone and scraped_summary["phones"]:
        lead.phone = scraped_summary["phones"][0]

    # Prefer scraped email
    if not lead.email and scraped_summary["emails"]:
        lead.email = scraped_summary["emails"][0]

    # Append scraped data as tagged JSON blob in raw_snippet for downstream agents
    lead.raw_snippet = (
        lead.raw_snippet or ""
    ).rstrip() + f"\n[scraped]{json.dumps(scraped_summary, ensure_ascii=False)}[/scraped]"

    return lead
