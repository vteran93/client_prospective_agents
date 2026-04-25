"""
tests/test_excel_tool.py — Route sheet coverage for Excel export.
"""

from __future__ import annotations

import pytest

openpyxl = pytest.importorskip("openpyxl")

from models import QualifiedLead, RoutePlan, RouteWaypoint, RunReport
from tools.excel_tool import export_to_excel


def _lead() -> QualifiedLead:
    return QualifiedLead(
        source="google_maps",
        name="Clínica Dental Norte",
        address="Calle 100 #10-20",
        phone="3001234567",
        tier="HOT",
        final_score=8.4,
        contact_priority=1,
    )


def _route_plan() -> RoutePlan:
    return RoutePlan(
        origin="Oficina",
        total_distance_km=12.5,
        total_duration_minutes=48.0,
        waypoints=[
            RouteWaypoint(
                lead_name="Clínica Dental Norte",
                address="Calle 100 #10-20",
                lat=4.68,
                lng=-74.04,
                tier="HOT",
                contact_priority=1,
                final_score=8.4,
                phone="3001234567",
                visit_order=1,
                estimated_arrival_minutes=12.0,
                distance_to_next_km=3.2,
                duration_to_next_minutes=9.0,
                google_maps_url="https://www.google.com/maps/search/?api=1",
            )
        ],
    )


class TestExportToExcelRouteSheet:
    def test_includes_route_sheet_when_route_plan_exists(self, tmp_path):
        out_path = export_to_excel(
            leads=[_lead()],
            report=RunReport(campaign_name="Test"),
            output_dir=str(tmp_path),
            filename_prefix="test_route",
            route_plan=_route_plan(),
        )

        workbook = openpyxl.load_workbook(out_path)
        assert "RUTA" in workbook.sheetnames

        sheet = workbook["RUTA"]
        assert sheet["A1"].value == "Orden de Visita"
        assert sheet["J2"].hyperlink.target == "https://www.google.com/maps/search/?api=1"
        assert sheet["E2"].fill.fgColor.rgb.endswith("C6EFCE")
        assert sheet["G3"].value == "12.50 km"

    def test_skips_route_sheet_when_route_plan_is_none(self, tmp_path):
        out_path = export_to_excel(
            leads=[_lead()],
            report=RunReport(campaign_name="Test"),
            output_dir=str(tmp_path),
            filename_prefix="test_no_route",
        )

        workbook = openpyxl.load_workbook(out_path)
        assert "RUTA" not in workbook.sheetnames
