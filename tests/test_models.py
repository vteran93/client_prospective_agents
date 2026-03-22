"""
tests/test_models.py — Unit tests for Pydantic models.

Tests:
  - CommercialProfile: Hormozi score computed correctly from dimensions
  - CommercialProfile: correct label assignment for all tier boundaries
  - QualifiedLead: inherits ProfiledLead fields correctly
  - RunReport: defaults and timestamp present
  - SearchConfig: qualification defaults
"""

from __future__ import annotations

import pytest

from models import (
    BusinessContext,
    CommercialProfile,
    EnrichedLead,
    ProfiledLead,
    QualificationConfig,
    QualifiedLead,
    RawLead,
    RunReport,
    SearchConfig,
    VisitTiming,
)


# ──────────────────────────────────────────────────────────────────
# CommercialProfile — Hormozi score
# ──────────────────────────────────────────────────────────────────


class TestCommercialProfileHormoziScore:
    def test_max_score(self):
        """All 3s → score = 10.0, label = STARVING_CROWD."""
        profile = CommercialProfile(
            hormozi_urgency=3,
            hormozi_buying_power=3,
            hormozi_accessibility=3,
            hormozi_market_fit=3,
        )
        assert profile.hormozi_score == 10.0
        assert profile.hormozi_label == "STARVING_CROWD"

    def test_zero_score(self):
        """All 0s → score = 0.0, label = COLD_MARKET."""
        profile = CommercialProfile()
        assert profile.hormozi_score == 0.0
        assert profile.hormozi_label == "COLD_MARKET"

    def test_warm_market_boundary(self):
        """Score exactly at warm boundary (6/12 = 5.0)."""
        profile = CommercialProfile(
            hormozi_urgency=1,
            hormozi_buying_power=2,
            hormozi_accessibility=2,
            hormozi_market_fit=1,
        )
        # raw=6, score=6*10/12=5.0
        assert profile.hormozi_score == 5.0
        assert profile.hormozi_label == "WARM_MARKET"

    def test_score_formula(self):
        """Verify the formula: score = raw * 10/12 rounded to 2dp."""
        profile = CommercialProfile(
            hormozi_urgency=2,
            hormozi_buying_power=1,
            hormozi_accessibility=1,
            hormozi_market_fit=2,
        )
        expected = round((2 + 1 + 1 + 2) * 10 / 12, 2)
        assert profile.hormozi_score == expected

    def test_starving_crowd_boundary(self):
        """Score at exactly 8.0 should be STARVING_CROWD."""
        # raw=9.6 → cap? No, need score>=8. 12*8/10=9.6 raw.
        # raw=10: score=10*10/12=8.33 → STARVING_CROWD
        profile = CommercialProfile(
            hormozi_urgency=3,
            hormozi_buying_power=3,
            hormozi_accessibility=2,
            hormozi_market_fit=2,
        )
        # raw=10, score=8.33
        assert profile.hormozi_score >= 8.0
        assert profile.hormozi_label == "STARVING_CROWD"

    def test_cold_market_boundary(self):
        """Score below 5 should be COLD_MARKET."""
        profile = CommercialProfile(
            hormozi_urgency=1,
            hormozi_buying_power=1,
            hormozi_accessibility=1,
            hormozi_market_fit=0,
        )
        # raw=3, score=2.5
        assert profile.hormozi_score < 5.0
        assert profile.hormozi_label == "COLD_MARKET"

    def test_computed_overrides_manual_score(self):
        """If hormozi_score is manually set, validator overwrites it with computed value."""
        profile = CommercialProfile(
            hormozi_urgency=0,
            hormozi_buying_power=0,
            hormozi_accessibility=0,
            hormozi_market_fit=0,
            hormozi_score=9.9,  # should be overwritten to 0.0
        )
        assert profile.hormozi_score == 0.0


# ──────────────────────────────────────────────────────────────────
# RawLead
# ──────────────────────────────────────────────────────────────────


class TestRawLead:
    def test_minimal_construction(self):
        lead = RawLead(source="tavily")
        assert lead.name == ""
        assert lead.rating == 0.0
        assert lead.popular_times == []

    def test_all_fields(self):
        lead = RawLead(
            source="google_maps",
            name="Taller El Chino",
            address="Calle 10 # 5-20, Bogotá",
            phone="3001234567",
            rating=4.5,
            reviews_count=120,
            place_id="ChIJxxx",
        )
        assert lead.place_id == "ChIJxxx"
        assert lead.reviews_count == 120


# ──────────────────────────────────────────────────────────────────
# EnrichedLead
# ──────────────────────────────────────────────────────────────────


class TestEnrichedLead:
    def test_inherits_raw_fields(self):
        el = EnrichedLead(source="tavily", name="Test Biz")
        assert el.source == "tavily"
        assert el.emails_scraped == []
        assert el.technology_stack == []

    def test_merge_sources(self):
        el = EnrichedLead(source="google_maps", merge_sources=["google_maps", "brave"])
        assert "google_maps" in el.merge_sources
        assert "brave" in el.merge_sources


# ──────────────────────────────────────────────────────────────────
# ProfiledLead
# ──────────────────────────────────────────────────────────────────


class TestProfiledLead:
    def test_default_profile(self):
        pl = ProfiledLead(source="tavily", name="Test")
        assert pl.profile.hormozi_score == 0.0
        assert pl.visit_timing.timing_confidence == "inferred"

    def test_custom_profile(self):
        profile = CommercialProfile(
            hormozi_urgency=3,
            hormozi_buying_power=3,
            hormozi_accessibility=3,
            hormozi_market_fit=3,
        )
        pl = ProfiledLead(source="google_maps", name="High Value", profile=profile)
        assert pl.profile.hormozi_label == "STARVING_CROWD"


# ──────────────────────────────────────────────────────────────────
# QualifiedLead
# ──────────────────────────────────────────────────────────────────


class TestQualifiedLead:
    def test_defaults(self):
        ql = QualifiedLead(source="tavily", name="Test")
        assert ql.tier == "COLD"
        assert ql.final_score == 0.0
        assert ql.discard_reason is None

    def test_hot_tier(self):
        ql = QualifiedLead(
            source="google_maps", name="Hot Lead", tier="HOT", final_score=8.5
        )
        assert ql.tier == "HOT"
        assert ql.final_score == 8.5


# ──────────────────────────────────────────────────────────────────
# SearchConfig + QualificationConfig + BusinessContext
# ──────────────────────────────────────────────────────────────────


class TestBusinessContext:
    def test_minimal(self):
        bc = BusinessContext(description="Consultoría de ventas")
        assert bc.description == "Consultoría de ventas"
        assert bc.reference_urls == []
        assert bc.target_audience == ""
        assert bc.ideal_customers == []

    def test_full_context(self):
        bc = BusinessContext(
            description="Empresa de consultoría",
            reference_urls=["https://example.com"],
            target_audience="PYMEs en Bogotá",
            ideal_customers=["Talleres mecánicos", "Clínicas veterinarias"],
        )
        assert len(bc.reference_urls) == 1
        assert len(bc.ideal_customers) == 2
        assert bc.target_audience == "PYMEs en Bogotá"

    def test_description_required(self):
        with pytest.raises(Exception):
            BusinessContext()


class TestSearchConfig:
    def test_defaults(self):
        cfg = SearchConfig(campaign_name="Test", queries=["q1"], city="Bogotá")
        assert cfg.max_leads == 150
        assert cfg.scrape_websites is True
        assert cfg.qualification.min_score_hot == 8.0
        assert cfg.qualification.min_score_warm == 5.0
        assert cfg.qualification.target_hot_warm == 80

    def test_custom_qualification(self):
        cfg = SearchConfig(
            campaign_name="Custom",
            queries=["q1"],
            city="Medellín",
            qualification=QualificationConfig(
                min_score_hot=7.5,
                min_score_warm=4.0,
                target_hot_warm=50,
            ),
        )
        assert cfg.qualification.min_score_hot == 7.5
        assert cfg.qualification.target_hot_warm == 50

    def test_business_context_only(self):
        """Queries vacías + business_context presente → válido."""
        bc = BusinessContext(description="Consultoría de ventas")
        cfg = SearchConfig(
            campaign_name="BC Only",
            city="Bogotá",
            business_context=bc,
        )
        assert cfg.queries == []
        assert cfg.business_context is not None
        assert cfg.business_context.description == "Consultoría de ventas"

    def test_queries_and_business_context(self):
        """Ambos presentes → válido."""
        bc = BusinessContext(description="Empresa de ventas")
        cfg = SearchConfig(
            campaign_name="Both",
            queries=["talleres bogotá"],
            city="Bogotá",
            business_context=bc,
        )
        assert len(cfg.queries) == 1
        assert cfg.business_context is not None

    def test_no_queries_no_context_raises(self):
        """Sin queries ni business_context → ValidationError."""
        with pytest.raises(Exception, match="queries.*business_context"):
            SearchConfig(campaign_name="Empty", city="Bogotá")


# ──────────────────────────────────────────────────────────────────
# RunReport
# ──────────────────────────────────────────────────────────────────


class TestRunReport:
    def test_timestamp_auto_set(self):
        report = RunReport(campaign_name="Test")
        assert report.timestamp  # not empty

    def test_counters(self):
        report = RunReport(
            campaign_name="Test",
            total_raw=100,
            hot_count=10,
            warm_count=30,
            cold_count=60,
        )
        assert report.hot_count + report.warm_count + report.cold_count == 100


# ──────────────────────────────────────────────────────────────────
# VisitTiming
# ──────────────────────────────────────────────────────────────────


class TestVisitTiming:
    def test_default_confidence(self):
        vt = VisitTiming()
        assert vt.timing_confidence == "inferred"
        assert vt.best_visit_windows == []

    def test_high_confidence(self):
        vt = VisitTiming(
            timing_confidence="high",
            timing_summary="Visitar martes 10am",
            best_visit_windows=[{"day": "martes", "start_hour": 9, "end_hour": 11}],
        )
        assert vt.timing_confidence == "high"
        assert len(vt.best_visit_windows) == 1
