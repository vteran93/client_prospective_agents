"""
tests/test_query_generator.py — Unit tests for QueryGeneratorAgent (T035).

Tests:
  - Generates queries from LLM response
  - Falls back to ideal_customers when LLM fails
  - Deduplicates queries case-insensitively
  - Combines manual + generated queries
  - Caps generated queries to MAX_GENERATED
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from models import BusinessSummary, SearchConfig


# ── Helpers ───────────────────────────────────────────────────────


def _make_summary(
    core_offering: str = "Software de nómina",
    ideal_customers: list[str] | None = None,
    target_sectors: list[str] | None = None,
) -> BusinessSummary:
    return BusinessSummary(
        core_offering=core_offering,
        ideal_customers=ideal_customers or ["Constructoras", "Distribuidoras"],
        target_sectors=target_sectors or ["Construcción", "Distribución"],
        geographic_focus="Bogotá, Colombia",
    )


def _make_config(queries: list[str] | None = None) -> SearchConfig:
    from models import BusinessContext

    return SearchConfig(
        campaign_name="Test",
        city="Bogotá",
        business_context=BusinessContext(description="Software de nómina"),
        queries=queries or [],
    )


def _mock_llm_returning_json(queries: list[str]) -> MagicMock:
    """Create a mock LLM that returns a JSON array of query strings."""
    import json

    mock_llm = MagicMock()
    response = MagicMock()
    response.content = json.dumps(queries, ensure_ascii=False)
    mock_llm.invoke.return_value = response
    return mock_llm


def _mock_llm_failing() -> MagicMock:
    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = RuntimeError("LLM error")
    return mock_llm


# ── Tests ─────────────────────────────────────────────────────────


class TestQueryGeneratorBasic:
    def test_generates_queries_from_llm(self):
        from agents.query_generator_agent import QueryGeneratorAgent

        llm_queries = [
            "distribuidora consumo masivo Bogotá",
            "constructora obras civiles Bogotá",
        ]
        llm = _mock_llm_returning_json(llm_queries)
        summary = _make_summary()
        config = _make_config()

        result = QueryGeneratorAgent.process(summary, config, llm)
        assert len(result) == 2
        assert "distribuidora consumo masivo Bogotá" in result
        assert "constructora obras civiles Bogotá" in result


class TestQueryGeneratorFallback:
    def test_fallback_to_ideal_customers(self):
        from agents.query_generator_agent import QueryGeneratorAgent

        llm = _mock_llm_failing()
        summary = _make_summary(ideal_customers=["Constructoras", "PYMEs"])
        config = _make_config()

        result = QueryGeneratorAgent.process(summary, config, llm)
        assert len(result) == 2
        assert "Constructoras Bogotá" in result
        assert "PYMEs Bogotá" in result


class TestQueryGeneratorDedup:
    def test_deduplicates_case_insensitive(self):
        from agents.query_generator_agent import _deduplicate

        queries = [
            "talleres Bogotá",
            "Talleres Bogotá",
            "TALLERES BOGOTÁ",
            "distribuidora Bogotá",
        ]
        result = _deduplicate(queries)
        assert len(result) == 2
        # First occurrence is preserved
        assert result[0] == "talleres Bogotá"
        assert result[1] == "distribuidora Bogotá"

    def test_dedup_strips_whitespace(self):
        from agents.query_generator_agent import _deduplicate

        queries = ["  talleres Bogotá  ", "talleres Bogotá"]
        result = _deduplicate(queries)
        assert len(result) == 1
        assert result[0] == "talleres Bogotá"

    def test_dedup_removes_empty(self):
        from agents.query_generator_agent import _deduplicate

        queries = ["", "  ", "talleres"]
        result = _deduplicate(queries)
        assert len(result) == 1
        assert result[0] == "talleres"


class TestQueryGeneratorManualCombine:
    def test_manual_queries_come_first(self):
        from agents.query_generator_agent import QueryGeneratorAgent

        llm_queries = ["distribuidora Bogotá", "constructora Bogotá"]
        llm = _mock_llm_returning_json(llm_queries)
        summary = _make_summary()
        config = _make_config(queries=["mi query manual"])

        result = QueryGeneratorAgent.process(summary, config, llm)
        assert result[0] == "mi query manual"
        assert len(result) == 3

    def test_manual_and_generated_deduplicated(self):
        from agents.query_generator_agent import QueryGeneratorAgent

        llm_queries = ["distribuidora Bogotá", "mi query manual"]
        llm = _mock_llm_returning_json(llm_queries)
        summary = _make_summary()
        config = _make_config(queries=["mi query manual"])

        result = QueryGeneratorAgent.process(summary, config, llm)
        # "mi query manual" appears in both manual and generated
        assert result.count("mi query manual") == 1
        assert len(result) == 2


class TestQueryGeneratorCap:
    def test_caps_generated_to_max(self):
        from agents.query_generator_agent import QueryGeneratorAgent

        # Generate more than MAX_GENERATED (15) queries
        llm_queries = [f"query_{i} Bogotá" for i in range(30)]
        llm = _mock_llm_returning_json(llm_queries)
        summary = _make_summary()
        config = _make_config()

        result = QueryGeneratorAgent.process(summary, config, llm)
        assert len(result) <= 15


class TestQueryGeneratorLLMResponseParsing:
    def test_extracts_json_from_markdown(self):
        from agents.query_generator_agent import QueryGeneratorAgent

        mock_llm = MagicMock()
        response = MagicMock()
        response.content = 'Aquí van las queries:\n```json\n["query1", "query2"]\n```'
        mock_llm.invoke.return_value = response

        summary = _make_summary()
        config = _make_config()

        result = QueryGeneratorAgent.process(summary, config, mock_llm)
        assert "query1" in result
        assert "query2" in result
