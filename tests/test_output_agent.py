"""
tests/test_output_agent.py — Unit tests for OutputAgent run log metadata.
"""

from __future__ import annotations

import json

from agents.output_agent import OutputAgent
from models import (
    BusinessContext,
    BusinessSummary,
    QualifiedLead,
    RoutePlan,
    RouteWaypoint,
    RunReport,
    SearchConfig,
)


class TestOutputAgentRunLog:
    def test_run_log_includes_ep7_metadata(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        config = SearchConfig(
            campaign_name="Test",
            city="Bogotá",
            queries=["query manual", "query auto"],
            business_context=BusinessContext(description="Consultoría comercial"),
        )
        agent = OutputAgent(config)
        report = RunReport(campaign_name="Test")
        leads = [
            QualifiedLead(
                source="duckduckgo",
                name="Lead 1",
                tier="HOT",
                final_score=8.2,
                contact_priority=1,
            )
        ]
        summary = BusinessSummary(
            core_offering="Consultoría comercial",
            ideal_customers=["PYMEs de servicios"],
            raw_context="Texto consolidado",
        )
        route_plan = RoutePlan(
            origin="Oficina",
            total_distance_km=12.4,
            total_duration_minutes=35.0,
            google_maps_urls=["https://www.google.com/maps/dir/?api=1"],
            waypoints=[
                RouteWaypoint(
                    lead_name="Lead 1",
                    address="Cra 7 #10-20",
                    lat=4.6,
                    lng=-74.0,
                    tier="HOT",
                    contact_priority=1,
                    final_score=8.2,
                )
            ],
        )

        log_path = agent._write_run_log(
            leads,
            report,
            excel_path="output/test.xlsx",
            business_summary=summary,
            auto_generated_queries=["query auto"],
            route_plan=route_plan,
        )

        with open(log_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["auto_generated_queries"] == ["query auto"]
        assert data["business_summary"]["core_offering"] == "Consultoría comercial"
        assert data["business_summary"]["ideal_customers"] == ["PYMEs de servicios"]
        assert data["route_plan_summary"]["num_stops"] == 1
        assert data["route_plan_summary"]["total_distance_km"] == 12.4
