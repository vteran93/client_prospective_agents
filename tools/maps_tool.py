"""
tools/maps_tool.py — Google Places API (New) tools.

GoogleMapsSearchTool  — Text search (textsearch) returning a list of places.
GoogleMapsDetailsTool — Place details for a single place_id.

API docs:
  https://developers.google.com/maps/documentation/places/web-service/text-search
  https://developers.google.com/maps/documentation/places/web-service/place-details
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
from crewai.tools import BaseTool
from pydantic import Field


_TEXTSEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"
_MIN_INTERVAL = 0.1  # 10 req/sec safety margin


# ╔══════════════════════════════════════════════════════════════════╗
# ║  Text Search                                                     ║
# ╚══════════════════════════════════════════════════════════════════╝


class GoogleMapsSearchTool(BaseTool):
    name: str = "google_maps_search"
    description: str = (
        "Search businesses on Google Maps using the Places API (New). "
        "Input: a plain-text query string (e.g. 'talleres mecánicos Bogotá'). "
        "Output: JSON array of raw place objects with name, address, phone, rating, "
        "reviews_count, lat, lng, place_id, website."
    )
    api_key: str = Field(default="", exclude=True)
    max_results: int = Field(default=20)
    language_code: str = Field(default="es")
    _last_call_ts: float = 0.0

    def _run(self, query: str) -> str:  # type: ignore[override]
        self._rate_limit()
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": (
                "places.id,places.displayName,places.formattedAddress,"
                "places.nationalPhoneNumber,places.rating,places.userRatingCount,"
                "places.websiteUri,places.location,places.businessStatus,"
                "places.currentOpeningHours,places.regularOpeningHours"
            ),
        }
        payload = {
            "textQuery": query,
            "maxResultCount": min(self.max_results, 20),
            "languageCode": self.language_code,
        }

        try:
            with httpx.Client(timeout=15) as client:
                resp = client.post(_TEXTSEARCH_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc), "results": []})

        results = []
        for place in data.get("places", []):
            loc = place.get("location", {})
            hours_raw = place.get("regularOpeningHours", {})
            results.append(
                {
                    "place_id": place.get("id", ""),
                    "name": place.get("displayName", {}).get("text", ""),
                    "address": place.get("formattedAddress", ""),
                    "phone": place.get("nationalPhoneNumber", ""),
                    "website": place.get("websiteUri", ""),
                    "rating": place.get("rating", 0.0),
                    "reviews_count": place.get("userRatingCount", 0),
                    "lat": loc.get("latitude", 0.0),
                    "lng": loc.get("longitude", 0.0),
                    "opening_hours": _parse_opening_hours(hours_raw),
                    "source": "google_maps",
                }
            )
        return json.dumps(results, ensure_ascii=False)

    def _rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_call_ts
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        self._last_call_ts = time.monotonic()


# ╔══════════════════════════════════════════════════════════════════╗
# ║  Place Details                                                   ║
# ╚══════════════════════════════════════════════════════════════════╝


class GoogleMapsDetailsTool(BaseTool):
    name: str = "google_maps_details"
    description: str = (
        "Fetch detailed information for a single Google Maps place. "
        "Input: a Google Maps place_id string. "
        "Output: JSON object with full place details."
    )
    api_key: str = Field(default="", exclude=True)
    language_code: str = Field(default="es")
    _last_call_ts: float = 0.0

    def _run(self, place_id: str) -> str:  # type: ignore[override]
        self._rate_limit()
        url = _DETAILS_URL.format(place_id=place_id)
        headers = {
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": (
                "id,displayName,formattedAddress,nationalPhoneNumber,"
                "internationalPhoneNumber,rating,userRatingCount,websiteUri,"
                "location,regularOpeningHours,currentOpeningHours,"
                "editorialSummary,types,businessStatus"
            ),
            "Accept-Language": self.language_code,
        }

        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})

        loc = data.get("location", {})
        hours_raw = data.get("regularOpeningHours", {})
        return json.dumps(
            {
                "place_id": data.get("id", ""),
                "name": data.get("displayName", {}).get("text", ""),
                "address": data.get("formattedAddress", ""),
                "phone": data.get("nationalPhoneNumber", ""),
                "international_phone": data.get("internationalPhoneNumber", ""),
                "website": data.get("websiteUri", ""),
                "rating": data.get("rating", 0.0),
                "reviews_count": data.get("userRatingCount", 0),
                "lat": loc.get("latitude", 0.0),
                "lng": loc.get("longitude", 0.0),
                "opening_hours": _parse_opening_hours(hours_raw),
                "summary": data.get("editorialSummary", {}).get("text", ""),
                "types": data.get("types", []),
            },
            ensure_ascii=False,
        )

    def _rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_call_ts
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        self._last_call_ts = time.monotonic()


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────


def _parse_opening_hours(hours_raw: dict[str, Any]) -> dict[str, list[str]]:
    """Convert Places API weekday_descriptions into {day_name: [periods]} dict."""
    result: dict[str, list[str]] = {}
    for line in hours_raw.get("weekdayDescriptions", []):
        if ": " in line:
            day, periods = line.split(": ", 1)
            result[day.strip()] = [p.strip() for p in periods.split(",")]
    return result
