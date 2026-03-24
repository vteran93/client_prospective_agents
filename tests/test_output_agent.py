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

        log_path = agent._write_run_log(
            leads,
            report,
            excel_path="output/test.xlsx",
            business_summary=summary,
            auto_generated_queries=["query auto"],
        )

        with open(log_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["auto_generated_queries"] == ["query auto"]
        assert data["business_summary"]["core_offering"] == "Consultoría comercial"
        assert data["business_summary"]["ideal_customers"] == ["PYMEs de servicios"]
