"""
agents/maps_agent.py — Google Maps Places API agent.

Responsibilities:
  1. Run each query from search_config against Google Places textsearch.
  2. Optionally fetch Place Details for richer data.
  3. Return list[RawLead] ready for dedup + enrichment.
"""

from __future__ import annotations

import json
from typing import Sequence

from rich.console import Console

from config import AppSettings
from models import RawLead, SearchConfig

console = Console()


class MapsAgent:
    """Fetches leads from Google Maps Places API."""

    def __init__(self, config: SearchConfig, settings: AppSettings) -> None:
        self.config = config
        self.settings = settings

    @classmethod
    def process(
        cls,
        config: SearchConfig,
        settings: AppSettings,
    ) -> list[RawLead]:
        if "google_maps" not in config.sources:
            return []
        if not settings.google_maps_api_key:
            console.print(
                "[yellow]⚠ MapsAgent: GOOGLE_MAPS_API_KEY no configurada — omitiendo"
            )
            return []
        agent = cls(config, settings)
        return agent.run()

    # ──────────────────────────────────────────────────────────────

    def run(self) -> list[RawLead]:
        from tools.maps_tool import GoogleMapsSearchTool, GoogleMapsDetailsTool

        search_tool = GoogleMapsSearchTool(api_key=self.settings.google_maps_api_key)
        details_tool = GoogleMapsDetailsTool(api_key=self.settings.google_maps_api_key)

        all_leads: list[RawLead] = []
        seen_ids: set[str] = set()

        for query in self.config.queries:
            full_query = f"{query} {self.config.city} {self.config.country}"
            console.print(f"[dim]  🗺  [google_maps] {full_query[:80]}")

            raw = search_tool._run(full_query)
            results = _parse_textsearch(raw)

            for place in results:
                place_id = place.get("place_id", "")
                if place_id in seen_ids:
                    continue
                seen_ids.add(place_id)

                # Enrich with Place Details if place_id present
                if place_id:
                    detail_raw = details_tool._run(place_id)
                    detail = _parse_details(detail_raw)
                    place.update({k: v for k, v in detail.items() if v})

                lead = _dict_to_raw_lead(place)
                all_leads.append(lead)

        console.print(f"[green]  ✓ MapsAgent: {len(all_leads)} lugares encontrados")
        return all_leads


# ──────────────────────────────────────────────────────────────────
# Parsing helpers
# ──────────────────────────────────────────────────────────────────


def _parse_textsearch(raw_json: str) -> list[dict]:
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict) and "error" in data:
        return []
    return data if isinstance(data, list) else data.get("results", [])


def _parse_details(raw_json: str) -> dict:
    try:
        return json.loads(raw_json)
    except json.JSONDecodeError:
        return {}


def _dict_to_raw_lead(d: dict) -> RawLead:
    return RawLead(
        source="google_maps",
        place_id=d.get("place_id", ""),
        name=d.get("name", ""),
        address=d.get("address", ""),
        phone=d.get("phone", "") or d.get("international_phone", ""),
        website=d.get("website", ""),
        rating=float(d.get("rating", 0) or 0),
        reviews_count=int(d.get("reviews_count", 0) or 0),
        lat=float(d.get("lat", 0) or 0),
        lng=float(d.get("lng", 0) or 0),
        opening_hours=d.get("opening_hours", {}),
        popular_times=d.get("popular_times", []),
        raw_snippet=d.get("summary", "")[:500],
    )
