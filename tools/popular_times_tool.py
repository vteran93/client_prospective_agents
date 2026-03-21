"""
tools/popular_times_tool.py — Scrape Google Maps popular hours via Playwright.

Popular times are NOT available via the Places API (New); they are rendered
in the Google Maps web UI.  This tool opens the Maps URL in a headless browser,
waits for the busyness chart to render, and extracts aria-label data from the bars.

Confidence:
  "high"     — actual bars found and parsed
  "inferred" — page loaded but no bars found (closed / no data / changed DOM)

Rate limit: 3 s between requests to avoid bot detection.
"""

from __future__ import annotations

import json
import re
import time

from crewai.tools import BaseTool

_MIN_INTERVAL = 3.0  # seconds between Playwright requests
_MAPS_SEARCH_URL = (
    "https://www.google.com/maps/search/?api=1&query={name}&query_place_id={place_id}"
)
_ARIA_PATTERN = re.compile(
    r"(\d+)%?\s*(?:de ocupación|busy|ocupado)[^.]*"
    r"(?:lunes|martes|miércoles|jueves|viernes|sábado|domingo|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    r"[^.]*?(\d{1,2}):?00",
    re.IGNORECASE,
)

_DAYS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_DAYS_EN = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


class PopularTimesTool(BaseTool):
    name: str = "popular_times"
    description: str = (
        "Scrape Google Maps popular hours data for a business using Playwright. "
        "Input: JSON string with {place_id, name, address}. "
        "Output: JSON with {popular_times: [...], confidence: 'high'|'inferred'}."
    )
    _last_call_ts: float = 0.0

    def _run(self, input_json: str) -> str:  # type: ignore[override]
        try:
            data = json.loads(input_json)
        except json.JSONDecodeError:
            return json.dumps(
                {"popular_times": [], "confidence": "inferred", "error": "invalid json"}
            )

        place_id = data.get("place_id", "")
        name = data.get("name", "")

        self._rate_limit()
        result = _scrape_popular_times(place_id=place_id, name=name)
        return json.dumps(result, ensure_ascii=False)

    def _rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_call_ts
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        self._last_call_ts = time.monotonic()


# ──────────────────────────────────────────────────────────────────
# Core scraping logic
# ──────────────────────────────────────────────────────────────────


def _scrape_popular_times(place_id: str, name: str) -> dict:
    """Open Google Maps and extract popular times bars."""
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        return {
            "popular_times": [],
            "confidence": "inferred",
            "error": "playwright not installed",
        }

    url = _MAPS_SEARCH_URL.format(
        name=name.replace(" ", "+"),
        place_id=place_id,
    )

    popular_times: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(
                locale="es-CO",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=20_000)

            # Wait for place panel to appear
            try:
                page.wait_for_selector(
                    "[data-section-id='popular-times']", timeout=8_000
                )
            except PWTimeout:
                pass  # section might not exist

            # Try multiple selectors used by Google across versions
            for selector in (
                "div[aria-label*='%']",
                "div[aria-label*='busy']",
                "div[aria-label*='ocupaci']",
                "[jsaction*='mouseover'][aria-label]",
            ):
                handles = page.query_selector_all(selector)
                for handle in handles:
                    label = handle.get_attribute("aria-label") or ""
                    parsed = _parse_aria_label(label)
                    if parsed:
                        popular_times.append(parsed)

        except Exception as exc:  # noqa: BLE001
            return {"popular_times": [], "confidence": "inferred", "error": str(exc)}
        finally:
            browser.close()

    # Deduplicate by (day, hour)
    seen: set[tuple] = set()
    unique: list[dict] = []
    for entry in popular_times:
        key = (entry.get("day"), entry.get("hour"))
        if key not in seen:
            seen.add(key)
            unique.append(entry)

    confidence = "high" if unique else "inferred"
    return {"popular_times": unique, "confidence": confidence}


def _parse_aria_label(label: str) -> dict | None:
    """
    Try to extract {day, hour, occupancy_pct} from an aria-label string like:
    "12% de ocupación usual para el lunes a las 10:00."
    """
    label_lower = label.lower()

    # Detect day
    day = None
    for day_name in _DAYS_ES + _DAYS_EN:
        if day_name in label_lower:
            # Normalise to English short form
            if day_name in _DAYS_ES:
                day = _DAYS_EN[_DAYS_ES.index(day_name)]
            else:
                day = day_name
            break

    if day is None:
        return None

    # Detect hour
    hour_match = re.search(r"\b(\d{1,2})(?::00)?\s*(?:a\.?m|p\.?m|h)?\.?", label_lower)
    if not hour_match:
        return None
    hour = int(hour_match.group(1))

    # Detect occupancy %
    pct_match = re.search(r"(\d{1,3})\s*%", label)
    occupancy = int(pct_match.group(1)) if pct_match else None

    if occupancy is None:
        return None

    return {"day": day, "hour": hour, "occupancy_pct": occupancy}
