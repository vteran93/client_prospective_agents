"""
tests/test_route_agent.py — Unit tests for RouteAgent.
"""

from __future__ import annotations

from models import QualifiedLead, RouteConfig, SearchConfig
from agents.route_agent import RouteAgent
from config import AppSettings
from tools.route_tool import RouteToolError


def _lead(
    name: str,
    *,
    lat: float,
    lng: float,
    tier: str = "HOT",
    priority: int = 1,
    score: float = 8.0,
    place_id: str = "",
) -> QualifiedLead:
    return QualifiedLead(
        source="google_maps",
        name=name,
        address=f"Dirección {name}",
        lat=lat,
        lng=lng,
        tier=tier,
        final_score=score,
        contact_priority=priority,
        place_id=place_id,
        phone="3001234567",
    )


class TestRouteAgent:
    def test_returns_none_when_route_is_disabled(self):
        config = SearchConfig(campaign_name="Test", city="Bogotá", queries=["q1"])
        result = RouteAgent.process(
            [_lead("A", lat=4.66, lng=-74.05)],
            config,
            AppSettings(google_maps_api_key="gmaps"),
        )
        assert result is None

    def test_filters_invalid_coords_and_prefers_lower_effort_selection(
        self,
        monkeypatch,
    ):
        captured: dict = {}

        def fake_compute(api_key, origin, waypoints, travel_mode, departure_time):
            captured["waypoints"] = waypoints
            return {
                "optimized_order": [1, 0],
                "legs": [
                    {"distance_m": 1000, "duration_s": 600},
                    {"distance_m": 1500, "duration_s": 300},
                    {"distance_m": 900, "duration_s": 240},
                ],
                "total_distance_m": 3400,
                "total_duration_s": 1140,
            }

        monkeypatch.setattr("agents.route_agent.compute_optimized_route", fake_compute)
        monkeypatch.setattr(
            "agents.route_agent.build_google_maps_url",
            lambda **kwargs: ["https://www.google.com/maps/dir/?api=1"],
        )

        config = SearchConfig(
            campaign_name="Test",
            city="Bogotá",
            queries=["q1"],
            route_planning=RouteConfig(
                enabled=True,
                origin_address="Oficina",
                origin_lat=4.6533,
                origin_lng=-74.0553,
                max_waypoints_per_route=2,
            ),
        )
        leads = [
            _lead("Lejano", lat=4.80, lng=-74.20, priority=1, place_id="far"),
            _lead("Cercano", lat=4.66, lng=-74.05, priority=1, place_id="near"),
            _lead("Menor prioridad", lat=4.661, lng=-74.051, priority=2, place_id="p2"),
            _lead("Sin coords", lat=0.0, lng=0.0, priority=1),
        ]

        plan = RouteAgent.process(
            leads,
            config,
            AppSettings(google_maps_api_key="gmaps"),
        )

        assert plan is not None
        assert [waypoint["place_id"] for waypoint in captured["waypoints"]] == ["near", "far"]
        assert [waypoint.lead_name for waypoint in plan.waypoints] == ["Lejano", "Cercano"]
        assert plan.waypoints[0].visit_order == 1
        assert plan.waypoints[0].estimated_arrival_minutes == 10.0
        assert plan.waypoints[0].distance_to_next_km == 1.5
        assert plan.total_distance_km == 3.4
        assert plan.google_maps_urls == ["https://www.google.com/maps/dir/?api=1"]

    def test_returns_none_on_routes_api_error(self, monkeypatch):
        monkeypatch.setattr(
            "agents.route_agent.compute_optimized_route",
            lambda *args, **kwargs: (_ for _ in ()).throw(RouteToolError("boom")),
        )

        config = SearchConfig(
            campaign_name="Test",
            city="Bogotá",
            queries=["q1"],
            route_planning=RouteConfig(
                enabled=True,
                origin_address="Oficina",
                origin_lat=4.6533,
                origin_lng=-74.0553,
            ),
        )

        result = RouteAgent.process(
            [_lead("Lead", lat=4.66, lng=-74.05)],
            config,
            AppSettings(google_maps_api_key="gmaps"),
        )

        assert result is None
