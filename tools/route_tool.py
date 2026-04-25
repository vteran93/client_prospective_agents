"""
tools/route_tool.py — Route optimization helpers using Google Routes API.

This module is intentionally independent from crewai so it can be tested in
isolation like dedup_tool.py and excel_tool.py.
"""

from __future__ import annotations

import math
import time
from urllib.parse import urlencode

import httpx


_ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
_MIN_INTERVAL = 0.1
_LAST_CALL_TS = 0.0


class RouteToolError(Exception):
    """Raised when the Google Routes API request fails."""


def compute_optimized_route(
    api_key: str,
    origin: dict,
    waypoints: list[dict],
    travel_mode: str = "DRIVE",
    departure_time: str | None = None,
) -> dict:
    """
    Call Google Routes API with optimizeWaypointOrder=true.

    The request uses the seller's origin as both start and final destination so
    the optimized order minimizes the full travel circuit for the field visit.
    """
    if not api_key:
        raise RouteToolError("GOOGLE_MAPS_API_KEY requerida para calcular rutas")
    if not waypoints:
        return {
            "optimized_order": [],
            "legs": [],
            "total_distance_m": 0,
            "total_duration_s": 0,
        }

    _rate_limit()
    payload = _build_compute_routes_payload(
        origin=origin,
        waypoints=waypoints,
        travel_mode=travel_mode,
        departure_time=departure_time,
        prefer_place_ids=True,
    )
    response = _post_compute_routes(api_key=api_key, payload=payload)

    # Place IDs coming from scraped/legacy sources may be stale; fall back to
    # coordinate-based routing so the itinerary is still generated.
    if response.status_code == 404 and any(waypoint.get("place_id") for waypoint in waypoints):
        payload = _build_compute_routes_payload(
            origin=origin,
            waypoints=waypoints,
            travel_mode=travel_mode,
            departure_time=departure_time,
            prefer_place_ids=False,
        )
        response = _post_compute_routes(api_key=api_key, payload=payload)

    if response.status_code == 403:
        raise RouteToolError(
            "Routes API no está habilitada para esta GOOGLE_MAPS_API_KEY. "
            "Activa 'Routes API' en Google Cloud Console."
        )
    if response.status_code >= 400:
        raise RouteToolError(
            f"Routes API respondió {response.status_code}: {response.text[:300]}"
        )

    data = response.json()
    routes = data.get("routes", [])
    if not routes:
        raise RouteToolError("Routes API no retornó ninguna ruta optimizada")

    route = routes[0]
    legs = [
        {
            "distance_m": int(leg.get("distanceMeters", 0) or 0),
            "duration_s": _parse_duration_seconds(leg.get("duration", "0s")),
        }
        for leg in route.get("legs", [])
    ]
    return {
        "optimized_order": list(route.get("optimizedIntermediateWaypointIndex", [])),
        "legs": legs,
        "total_distance_m": int(route.get("distanceMeters", 0) or sum(leg["distance_m"] for leg in legs)),
        "total_duration_s": _parse_duration_seconds(route.get("duration", "0s"))
        or sum(leg["duration_s"] for leg in legs),
    }


def build_google_maps_url(
    origin: dict,
    waypoints: list[dict],
    destination: dict | None = None,
    travel_mode: str = "driving",
) -> list[str]:
    """
    Build Google Maps navigation URLs.

    Google Maps URLs support a limited number of stopovers in mobile flows, so
    long itineraries are split into multiple links with continuity between them.
    """
    if not waypoints:
        return []

    urls: list[str] = []
    chunk_size = 9
    remaining = list(waypoints)
    current_origin = origin

    while remaining:
        chunk = remaining[:chunk_size]
        remaining = remaining[chunk_size:]

        if remaining:
            current_destination = chunk[-1]
            intermediate_stops = chunk[:-1]
        else:
            current_destination = destination or chunk[-1]
            intermediate_stops = chunk if destination else chunk[:-1]

        params = {
            "api": 1,
            "origin": _coord_text(current_origin),
            "destination": _coord_text(current_destination),
            "travelmode": travel_mode,
            "dir_action": "navigate",
        }
        if current_origin.get("place_id"):
            params["origin_place_id"] = current_origin["place_id"]
        if current_destination.get("place_id"):
            params["destination_place_id"] = current_destination["place_id"]
        if intermediate_stops:
            params["waypoints"] = "|".join(_coord_text(stop) for stop in intermediate_stops)
            place_ids = [stop.get("place_id", "") for stop in intermediate_stops]
            if place_ids and all(place_ids):
                params["waypoint_place_ids"] = "|".join(place_ids)

        urls.append("https://www.google.com/maps/dir/?" + urlencode(params, safe="|,"))
        current_origin = current_destination

    return urls


def build_google_maps_place_url(waypoint: dict) -> str:
    params = {
        "api": 1,
        "query": _coord_text(waypoint),
    }
    if waypoint.get("place_id"):
        params["query_place_id"] = waypoint["place_id"]
    return "https://www.google.com/maps/search/?" + urlencode(params, safe=",")


def _build_compute_routes_payload(
    origin: dict,
    waypoints: list[dict],
    travel_mode: str,
    departure_time: str | None,
    prefer_place_ids: bool,
) -> dict:
    payload = {
        "origin": _build_waypoint(origin, prefer_place_id=False),
        "destination": _build_waypoint(origin, prefer_place_id=False),
        "intermediates": [
            _build_waypoint(waypoint, prefer_place_id=prefer_place_ids)
            for waypoint in waypoints
        ],
        "travelMode": travel_mode,
        "optimizeWaypointOrder": True,
        "languageCode": "es-CO",
    }
    if departure_time:
        payload["departureTime"] = departure_time
    if travel_mode in {"DRIVE", "TWO_WHEELER"}:
        payload["routingPreference"] = "TRAFFIC_AWARE"
    return payload


def _post_compute_routes(api_key: str, payload: dict) -> httpx.Response:
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "routes.distanceMeters,routes.duration,"
            "routes.legs.distanceMeters,routes.legs.duration,"
            "routes.optimizedIntermediateWaypointIndex"
        ),
        "X-Server-Timeout": "10",
    }
    try:
        with httpx.Client(timeout=20) as client:
            return client.post(_ROUTES_URL, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise RouteToolError(f"Error conectando con Routes API: {exc}") from exc


def _build_waypoint(point: dict, prefer_place_id: bool = True) -> dict:
    if prefer_place_id and point.get("place_id"):
        return {"placeId": point["place_id"]}
    return {
        "location": {
            "latLng": {
                "latitude": float(point.get("lat", 0.0) or 0.0),
                "longitude": float(point.get("lng", 0.0) or 0.0),
            }
        }
    }


def _coord_text(point: dict) -> str:
    return f"{float(point.get('lat', 0.0) or 0.0):.6f},{float(point.get('lng', 0.0) or 0.0):.6f}"


def _parse_duration_seconds(raw: str) -> int:
    if not raw:
        return 0
    if raw.endswith("s"):
        raw = raw[:-1]
    try:
        return int(round(float(raw)))
    except ValueError:
        return 0


def _rate_limit() -> None:
    global _LAST_CALL_TS
    elapsed = time.monotonic() - _LAST_CALL_TS
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _LAST_CALL_TS = time.monotonic()


def straight_line_distance_km(origin: dict, destination: dict) -> float:
    """Approximate distance in km using Haversine."""
    lat1 = math.radians(float(origin.get("lat", 0.0) or 0.0))
    lng1 = math.radians(float(origin.get("lng", 0.0) or 0.0))
    lat2 = math.radians(float(destination.get("lat", 0.0) or 0.0))
    lng2 = math.radians(float(destination.get("lng", 0.0) or 0.0))

    d_lat = lat2 - lat1
    d_lng = lng2 - lng1
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(d_lng / 2) ** 2
    )
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def travel_mode_for_google_maps(travel_mode: str) -> str:
    return {
        "DRIVE": "driving",
        "TWO_WHEELER": "two-wheeler",
        "WALK": "walking",
    }.get(travel_mode, "driving")
