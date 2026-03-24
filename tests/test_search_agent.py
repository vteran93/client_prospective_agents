"""
tests/test_search_agent.py — Unit tests for SearchAgent query expansion behavior.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from config import AppSettings
from models import BusinessContext, SearchConfig


class TestSearchAgentExpandQueries:
    def test_business_context_uses_pregenerated_queries(self):
        from agents.search_agent import SearchAgent

        config = SearchConfig(
            campaign_name="Test",
            city="Bogotá",
            queries=["query manual", "query auto"],
            business_context=BusinessContext(description="Consultoría comercial"),
        )
        llm = MagicMock()

        agent = SearchAgent(config, AppSettings(), llm)
        result = agent._expand_queries()

        assert result == ["query manual", "query auto"]
        llm.invoke.assert_not_called()

    def test_without_business_context_keeps_expansion_flow(self):
        from agents.search_agent import SearchAgent

        config = SearchConfig(
            campaign_name="Test",
            city="Bogotá",
            queries=["query base"],
        )
        llm = MagicMock()
        response = MagicMock()
        response.content = '["query base", "query variada"]'
        llm.invoke.return_value = response

        agent = SearchAgent(config, AppSettings(), llm)
        result = agent._expand_queries()

        assert result == ["query base", "query variada"]
        llm.invoke.assert_called_once()
