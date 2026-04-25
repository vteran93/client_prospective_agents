"""
tests/test_crew.py — Unit tests for EP-7 integration in ProspectingCrew (T036).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from config import AppSettings
from models import BusinessContext, BusinessSummary, RouteConfig, RoutePlan, SearchConfig


class TestProspectingCrewStepZero:
    @patch("crew.OutputAgent.process")
    @patch("crew.QueryGeneratorAgent.process")
    @patch("crew.ContextAgent.process")
    @patch("crew.get_llm")
    def test_business_context_runs_step_zero_even_with_manual_queries(
        self,
        mock_get_llm,
        mock_context,
        mock_query_generator,
        mock_output,
    ):
        from crew import ProspectingCrew

        mock_get_llm.return_value = MagicMock()
        mock_context.return_value = BusinessSummary(
            core_offering="Consultoría comercial",
            ideal_customers=["PYMEs de servicios"],
        )
        mock_query_generator.return_value = [
            "query manual",
            "query auto 1",
            "query auto 2",
        ]

        config = SearchConfig(
            campaign_name="Test",
            city="Bogotá",
            queries=["query manual"],
            business_context=BusinessContext(description="Consultoría comercial"),
        )
        crew = ProspectingCrew(config, AppSettings(openai_api_key="sk-test"))

        with patch.object(crew, "_run_discovery", return_value=([], [])):
            crew.run()

        mock_context.assert_called_once()
        mock_query_generator.assert_called_once()
        assert crew.config.queries == ["query manual", "query auto 1", "query auto 2"]

        output_kwargs = mock_output.call_args.kwargs
        assert output_kwargs["auto_generated_queries"] == ["query auto 1", "query auto 2"]
        assert output_kwargs["business_summary"].core_offering == "Consultoría comercial"

    @patch("crew.OutputAgent.process")
    @patch("crew.QueryGeneratorAgent.process")
    @patch("crew.ContextAgent.process")
    @patch("crew.get_llm")
    def test_without_business_context_keeps_previous_flow(
        self,
        mock_get_llm,
        mock_context,
        mock_query_generator,
        mock_output,
    ):
        from crew import ProspectingCrew

        mock_get_llm.return_value = MagicMock()

        config = SearchConfig(
            campaign_name="Test",
            city="Bogotá",
            queries=["query manual"],
        )
        crew = ProspectingCrew(config, AppSettings(openai_api_key="sk-test"))

        with patch.object(crew, "_run_discovery", return_value=([], [])):
            crew.run()

        mock_context.assert_not_called()
        mock_query_generator.assert_not_called()

        output_kwargs = mock_output.call_args.kwargs
        assert output_kwargs["auto_generated_queries"] == []
        assert output_kwargs["business_summary"] is None

    @patch("crew.OutputAgent.process")
    @patch("crew.RouteAgent.process")
    @patch("crew.get_llm")
    def test_route_plan_passes_to_output_when_enabled(
        self,
        mock_get_llm,
        mock_route_agent,
        mock_output,
    ):
        from crew import ProspectingCrew

        mock_get_llm.return_value = MagicMock()
        mock_route_agent.return_value = RoutePlan(origin="Oficina")

        config = SearchConfig(
            campaign_name="Test",
            city="Bogotá",
            queries=["query manual"],
            route_planning=RouteConfig(
                enabled=True,
                origin_address="Oficina",
                origin_lat=4.6,
                origin_lng=-74.0,
            ),
        )
        crew = ProspectingCrew(
            config,
            AppSettings(openai_api_key="sk-test", google_maps_api_key="gmaps"),
        )

        with patch.object(crew, "_run_discovery", return_value=([], [])):
            crew.run()

        mock_route_agent.assert_called_once()
        output_kwargs = mock_output.call_args.kwargs
        assert output_kwargs["route_plan"].origin == "Oficina"
