"""
tests/test_dedup.py — Unit tests for dedup_tool.py
"""

from __future__ import annotations

import pytest

from models import RawLead
from tools.dedup_tool import _norm_text, _same_area, deduplicate_leads


def _lead(
    name: str,
    phone: str = "",
    place_id: str = "",
    address: str = "",
    source: str = "test",
) -> RawLead:
    return RawLead(
        source=source, name=name, phone=phone, place_id=place_id, address=address
    )


class TestDeduplicateLeads:
    def test_exact_place_id_dedup(self):
        leads = [
            _lead("Taller A", place_id="abc123"),
            _lead("Taller A variant", place_id="abc123"),
        ]
        result = deduplicate_leads(leads)
        assert len(result) == 1

    def test_exact_phone_prefix_dedup(self):
        leads = [
            _lead("Shop1", phone="3001234567"),
            _lead("Shop 1 Ltda", phone="300-123-4567"),  # same number formatted
        ]
        result = deduplicate_leads(leads)
        assert len(result) == 1

    def test_fuzzy_name_dedup(self):
        leads = [
            _lead("Taller El Chino", address="Calle 10 Bogotá"),
            _lead("Talleres El Chino", address="Cl 10 Bogotá"),
        ]
        result = deduplicate_leads(leads)
        assert len(result) == 1

    def test_different_businesses_kept(self):
        leads = [
            _lead("Taller El Chino", address="Calle 10 Bogotá"),
            _lead("Moto Express", address="Carrera 50 Medellín"),
            _lead("Auto Parts Colombia", address="Zona Industrial"),
        ]
        result = deduplicate_leads(leads)
        assert len(result) == 3

    def test_empty_list(self):
        assert deduplicate_leads([]) == []

    def test_single_lead_unchanged(self):
        lead = _lead("Taller X", phone="3109876543")
        result = deduplicate_leads([lead])
        assert len(result) == 1
        assert result[0].name == "Taller X"

    def test_best_data_kept_after_merge(self):
        leads = [
            _lead("Taller Y", place_id="xyz", phone=""),
            _lead("Taller Y", place_id="xyz", phone="3001234567"),
        ]
        result = deduplicate_leads(leads)
        assert len(result) == 1
        assert result[0].phone == "3001234567"


class TestNormText:
    def test_lowercase_and_strip(self):
        assert _norm_text("  TALLER EL CHINO  ") == "taller el chino"

    def test_punctuation_removed(self):
        # punctuation replaced by spaces, then whitespace collapsed and stripped
        assert _norm_text("Taller, El-Chino.") == "taller el chino"

    def test_accents_removed_if_unidecode_available(self):
        result = _norm_text("Mecánica Ángel")
        # With unidecode installed, accents are removed
        assert "ngel" in result or "Ángel".lower() in result


class TestSameArea:
    def test_shared_significant_word(self):
        assert _same_area("Calle 10 Chapinero Bogotá", "Cr 15 Chapinero Bogotá") is True

    def test_different_street_numbers_not_same(self):
        # Street numbers 10 and 20 are distinct significant words—correctly returns False
        assert _same_area("Calle 10 Bogot\u00e1", "Carrera 20 Bogot\u00e1") is False

    def test_shared_neighbourhood_is_same(self):
        # Both addresses mention Chapinero (non-stopword) → True
        assert (
            _same_area("Calle 72 Chapinero Bogot\u00e1", "Carrera 15 Chapinero") is True
        )

    def test_empty_address_returns_true(self):
        assert _same_area("", "Calle 10") is True
        assert _same_area("Calle 10", "") is True
