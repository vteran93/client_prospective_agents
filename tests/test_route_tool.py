"""
tests/test_route_tool.py — Unit tests for Google Routes helpers.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from tools.route_tool import RouteToolError, build_google_maps_url, compute_optimized_route


class _MockResponse:
    def __init__(self, status_code: int, payload: dict, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text or str(payload)

    def json(self) -> dict:
        return self._payload


class _MockClient:
    def __init__(self, response: _MockResponse | list[_MockResponse], capture: dict) -> None:
        self.responses = response if isinstance(response, list) else [response]
        self.capture = capture

    def __enter__(self) -> "_MockClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def post(self, url: str, json: dict, headers: dict) -> _MockResponse:
        self.capture["url"] = url
        self.capture.setdefault("json_calls", []).append(json)
        self.capture["json"] = json
        self.capture["headers"] = headers
        return self.responses.pop(0)


class TestComputeOptimizedRoute:
    def test_success_parses_route_and_sends_expected_payload(self, monkeypatch):
        capture: dict = {}
        response = _MockResponse(
            200,
            {
                "routes": [
                    {
                        "optimizedIntermediateWaypointIndex": [1, 0],
                        "distanceMeters": 4200,
                        "duration": "780s",
                        "legs": [
                            {"distanceMeters": 1000, "duration": "120s"},
                            {"distanceMeters": 1400, "duration": "240s"},
                            {"distanceMeters": 1800, "duration": "420s"},
                        ],
                    }
                ]
            },
        )
        monkeypatch.setattr(
            "tools.route_tool.httpx.Client",
            lambda timeout: _MockClient(response, capture),
        )

        result = compute_optimized_route(
            api_key="gmaps-key",
            origin={"lat": 4.65, "lng": -74.05},
            waypoints=[
                {"lat": 4.66, "lng": -74.06, "place_id": "place-1"},
                {"lat": 4.67, "lng": -74.07},
            ],
            departure_time="2026-03-24T08:00:00-05:00",
        )

        assert result["optimized_order"] == [1, 0]
        assert result["legs"][1]["duration_s"] == 240
        assert result["total_distance_m"] == 4200
        assert capture["url"].endswith(":computeRoutes")
        assert capture["json"]["optimizeWaypointOrder"] is True
        assert capture["json"]["intermediates"][0] == {"placeId": "place-1"}
        assert "optimizedIntermediateWaypointIndex" in capture["headers"]["X-Goog-FieldMask"]

    def test_403_returns_clear_error(self, monkeypatch):
        capture: dict = {}
        response = _MockResponse(403, {}, text="Forbidden")
        monkeypatch.setattr(
            "tools.route_tool.httpx.Client",
            lambda timeout: _MockClient(response, capture),
        )

        with pytest.raises(RouteToolError, match="Routes API no está habilitada"):
            compute_optimized_route(
                api_key="gmaps-key",
                origin={"lat": 4.65, "lng": -74.05},
                waypoints=[{"lat": 4.66, "lng": -74.06}],
            )

    def test_retries_with_lat_lng_when_place_id_is_not_found(self, monkeypatch):
        capture: dict = {}
        responses = [
            _MockResponse(404, {}, text='{"error":{"message":"Place ID not found"}}'),
            _MockResponse(
                200,
                {
                    "routes": [
                        {
                            "optimizedIntermediateWaypointIndex": [0],
                            "distanceMeters": 1000,
                            "duration": "300s",
                            "legs": [
                                {"distanceMeters": 450, "duration": "120s"},
                                {"distanceMeters": 550, "duration": "180s"},
                            ],
                        }
                    ]
                },
            ),
        ]
        monkeypatch.setattr(
            "tools.route_tool.httpx.Client",
            lambda timeout: _MockClient(responses, capture),
        )

        result = compute_optimized_route(
            api_key="gmaps-key",
            origin={"lat": 4.65, "lng": -74.05},
            waypoints=[{"lat": 4.66, "lng": -74.06, "place_id": "bad-place"}],
        )

        assert result["total_duration_s"] == 300
        assert capture["json_calls"][0]["intermediates"][0] == {"placeId": "bad-place"}
        assert "location" in capture["json_calls"][1]["intermediates"][0]


class TestBuildGoogleMapsUrl:
    def test_splits_long_itinerary_and_uses_navigation_params(self):
        urls = build_google_maps_url(
            origin={"lat": 4.65, "lng": -74.05},
            waypoints=[
                {"lat": 4.60 + (index * 0.01), "lng": -74.00, "place_id": f"pid-{index}"}
                for index in range(11)
            ],
            destination={"lat": 4.65, "lng": -74.05},
            travel_mode="driving",
        )

        assert len(urls) == 2

        first_query = parse_qs(urlparse(urls[0]).query)
        second_query = parse_qs(urlparse(urls[1]).query)

        assert first_query["dir_action"] == ["navigate"]
        assert first_query["travelmode"] == ["driving"]
        assert "waypoint_place_ids" in first_query
        assert first_query["waypoint_place_ids"][0].startswith("pid-0|pid-1")
        assert second_query["destination"] == ["4.650000,-74.050000"]

    def test_omits_waypoint_place_ids_when_segment_has_missing_ids(self):
        urls = build_google_maps_url(
            origin={"lat": 4.65, "lng": -74.05},
            waypoints=[
                {"lat": 4.61, "lng": -74.00, "place_id": "pid-1"},
                {"lat": 4.62, "lng": -74.01},
                {"lat": 4.63, "lng": -74.02, "place_id": "pid-3"},
            ],
            destination={"lat": 4.65, "lng": -74.05},
            travel_mode="driving",
        )

        query = parse_qs(urlparse(urls[0]).query)
        assert "waypoint_place_ids" not in query
