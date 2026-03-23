"""
tests/test_context_agent.py — Unit tests for ContextAgent (T034).

Tests:
  - Returns empty BusinessSummary when no business_context
  - Uses ideal_customers from config directly (no LLM inference)
  - Falls back gracefully when LLM fails
  - Scrapes URLs and includes content in LLM prompt
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from models import BusinessContext, BusinessSummary, SearchConfig


# ── Helpers ───────────────────────────────────────────────────────


def _make_config(
    description: str = "Software de nómina",
    ideal_customers: list[str] | None = None,
    reference_urls: list[str] | None = None,
) -> SearchConfig:
    bc = BusinessContext(
        description=description,
        reference_urls=reference_urls or [],
        ideal_customers=ideal_customers or [],
    )
    return SearchConfig(
        campaign_name="Test",
        city="Bogotá",
        business_context=bc,
    )


def _make_config_no_bc() -> SearchConfig:
    return SearchConfig(
        campaign_name="Test",
        city="Bogotá",
        queries=["talleres bogotá"],
    )


def _mock_llm_returning(summary: BusinessSummary) -> MagicMock:
    """Create a mock LLM that returns a BusinessSummary via with_structured_output."""
    mock_llm = MagicMock()
    structured = MagicMock()
    structured.invoke.return_value = summary
    mock_llm.with_structured_output.return_value = structured
    return mock_llm


def _mock_settings() -> MagicMock:
    return MagicMock()


# ── Tests ─────────────────────────────────────────────────────────


class TestContextAgentNoBusinessContext:
    def test_returns_empty_summary(self):
        from agents.context_agent import ContextAgent

        config = _make_config_no_bc()
        settings = _mock_settings()
        llm = MagicMock()

        result = ContextAgent.process(config, settings, llm)
        assert isinstance(result, BusinessSummary)
        assert result.core_offering == ""
        assert result.target_sectors == []


class TestContextAgentWithIdealCustomers:
    def test_copies_ideal_customers_from_config(self):
        from agents.context_agent import ContextAgent

        customers = ["Constructoras", "Distribuidoras"]
        config = _make_config(ideal_customers=customers)
        settings = _mock_settings()

        llm_summary = BusinessSummary(
            core_offering="Software de nómina",
            target_sectors=["Construcción"],
            ideal_customers=["LLM generated customer"],
        )
        llm = _mock_llm_returning(llm_summary)

        result = ContextAgent.process(config, settings, llm)
        # Config ideal_customers override LLM-generated ones
        assert result.ideal_customers == customers
        assert result.core_offering == "Software de nómina"


class TestContextAgentLLMFallback:
    def test_fallback_on_llm_error(self):
        from agents.context_agent import ContextAgent

        config = _make_config(
            description="Mi empresa de nómina",
            ideal_customers=["PYMEs"],
        )
        settings = _mock_settings()

        mock_llm = MagicMock()
        structured = MagicMock()
        structured.invoke.side_effect = RuntimeError("LLM expired")
        mock_llm.with_structured_output.return_value = structured

        result = ContextAgent.process(config, settings, mock_llm)
        assert isinstance(result, BusinessSummary)
        # Fallback should still have core_offering from description
        assert "Mi empresa de nómina" in result.core_offering
        assert result.ideal_customers == ["PYMEs"]


class TestContextAgentScraping:
    @patch("agents.context_agent.ContextAgent._scrape_urls")
    def test_scrape_urls_called(self, mock_scrape):
        from agents.context_agent import ContextAgent

        mock_scrape.return_value = ["[https://example.com]: Contenido de ejemplo"]

        config = _make_config(reference_urls=["https://example.com"])
        settings = _mock_settings()

        llm_summary = BusinessSummary(core_offering="Software")
        llm = _mock_llm_returning(llm_summary)

        ContextAgent.process(config, settings, llm)
        mock_scrape.assert_called_once_with(["https://example.com"])

    @patch("agents.context_agent.ContextAgent._scrape_urls")
    def test_empty_scrape_doesnt_break(self, mock_scrape):
        from agents.context_agent import ContextAgent

        mock_scrape.return_value = []

        config = _make_config(reference_urls=["https://bad.example.com"])
        settings = _mock_settings()

        llm_summary = BusinessSummary(core_offering="Software")
        llm = _mock_llm_returning(llm_summary)

        result = ContextAgent.process(config, settings, llm)
        assert isinstance(result, BusinessSummary)


class TestContextAgentRawContext:
    @patch("agents.context_agent.ContextAgent._scrape_urls")
    def test_raw_context_populated(self, mock_scrape):
        from agents.context_agent import ContextAgent

        mock_scrape.return_value = ["[url]: Scraped text"]

        config = _make_config(description="Tech company")
        settings = _mock_settings()

        llm_summary = BusinessSummary(core_offering="Tech")
        llm = _mock_llm_returning(llm_summary)

        result = ContextAgent.process(config, settings, llm)
        assert "Tech company" in result.raw_context
