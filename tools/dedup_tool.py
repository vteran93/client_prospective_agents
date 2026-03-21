"""
tools/dedup_tool.py — Lead deduplication using fuzzy name matching + phone/place-id keys.

Algorithm:
  1. Exact match on place_id (strongest signal).
  2. Exact match on normalised phone prefix (first 7 digits).
  3. Fuzzy name match (token_sort_ratio >= 85) combined with same city (address check).

Returns the deduplicated list, merging source lists and preferring the most complete record.
"""

from __future__ import annotations

import re
from typing import Sequence

from models import RawLead


_NORM_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")


# ──────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────


def deduplicate_leads(leads: Sequence[RawLead], threshold: int = 85) -> list[RawLead]:
    """
    Remove duplicate leads, merging metadata from duplicates into the best record.

    Args:
        leads:     Sequence of RawLead objects (possibly with duplicates).
        threshold: rapidfuzz token_sort_ratio threshold (0-100).

    Returns:
        Deduplicated list of RawLead objects.
    """
    try:
        from rapidfuzz import fuzz  # lazy import
    except ImportError:
        # Graceful degradation: return as-is without fuzzy dedup
        return list(leads)

    buckets: list[RawLead] = []

    for lead in leads:
        matched = False

        # --- exact place_id match ---
        if lead.place_id:
            for existing in buckets:
                if existing.place_id and existing.place_id == lead.place_id:
                    _merge_into(existing, lead)
                    matched = True
                    break
            if matched:
                continue

        # --- exact phone prefix match ---
        if lead.phone:
            norm_phone = _norm_phone(lead.phone)
            if norm_phone:
                for existing in buckets:
                    if (
                        existing.phone
                        and _norm_phone(existing.phone)[:7] == norm_phone[:7]
                    ):
                        _merge_into(existing, lead)
                        matched = True
                        break
                if matched:
                    continue

        # --- fuzzy name + address match ---
        norm_name = _norm_text(lead.name)
        for existing in buckets:
            if not lead.name or not existing.name:
                continue
            score = fuzz.token_sort_ratio(norm_name, _norm_text(existing.name))
            if score >= threshold:
                # Extra guard: same rough address area (shared first word)
                if _same_area(lead.address, existing.address):
                    _merge_into(existing, lead)
                    matched = True
                    break

        if not matched:
            buckets.append(lead.model_copy(deep=True))

    return buckets


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────


def _merge_into(base: RawLead, duplicate: RawLead) -> None:
    """Update *base* in-place with any non-empty fields from *duplicate*."""
    # Prefer the record with more information
    if not base.phone and duplicate.phone:
        base.phone = duplicate.phone
    if not base.email and duplicate.email:
        base.email = duplicate.email
    if not base.website and duplicate.website:
        base.website = duplicate.website
    if not base.place_id and duplicate.place_id:
        base.place_id = duplicate.place_id
    if duplicate.rating > base.rating:
        base.rating = duplicate.rating
        base.reviews_count = duplicate.reviews_count
    if not base.popular_times and duplicate.popular_times:
        base.popular_times = duplicate.popular_times
    if not base.opening_hours and duplicate.opening_hours:
        base.opening_hours = duplicate.opening_hours

    # Record that this lead came from multiple sources
    dupe_sources = (
        duplicate.merge_sources
        if hasattr(duplicate, "merge_sources")
        else [duplicate.source]
    )
    base_sources = (
        base.merge_sources if hasattr(base, "merge_sources") else [base.source]
    )
    merged = list(
        dict.fromkeys(base_sources + dupe_sources)
    )  # deduplicated order-preserving
    # RawLead doesn't have merge_sources; EnrichedLead does.
    # We store it as a note in raw_snippet to avoid schema violation on RawLead.
    if len(merged) > 1:
        base.raw_snippet = (
            base.raw_snippet + f" [merged: {', '.join(merged)}]"
        ).strip()


def _norm_text(text: str) -> str:
    """Lowercase, remove punctuation, collapse whitespace."""
    try:
        from unidecode import unidecode

        text = unidecode(text)
    except ImportError:
        pass
    text = text.lower()
    text = _NORM_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


def _norm_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone)


def _same_area(addr1: str, addr2: str) -> bool:
    """Rough check: do both addresses share a common significant word?"""
    if not addr1 or not addr2:
        return True  # no address means we can't rule it out
    words1 = set(_norm_text(addr1).split()) - _STOPWORDS
    words2 = set(_norm_text(addr2).split()) - _STOPWORDS
    return bool(words1 & words2)


_STOPWORDS = {
    "calle",
    "carrera",
    "avenida",
    "av",
    "cl",
    "cr",
    "cra",
    "no",
    "de",
    "del",
    "la",
    "el",
    "los",
    "las",
    "bogota",
    "bogotá",
    "colombia",
    "street",
    "st",
    "ave",
    "blvd",
}
