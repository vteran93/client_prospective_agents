"""
agents/route_agent.py — Generate optimized visit routes for qualified leads.
"""

from __future__ import annotations

from rich.console import Console

from config import AppSettings
from models import QualifiedLead, RoutePlan, RouteWaypoint, SearchConfig
from tools.route_tool import (
    RouteToolError,
    build_google_maps_place_url,
    build_google_maps_url,
    compute_optimized_route,
    straight_line_distance_km,
    travel_mode_for_google_maps,
)

console = Console()


class RouteAgent:
    """Builds an optimized RoutePlan from qualified leads."""

    def __init__(self, config: SearchConfig, settings: AppSettings) -> None:
        self.config = config
        self.settings = settings

    @classmethod
    def process(
        cls,
        leads: list[QualifiedLead],
        config: SearchConfig,
        settings: AppSettings,
    ) -> RoutePlan | None:
        agent = cls(config, settings)
        return agent.run(leads)

    def run(self, leads: list[QualifiedLead]) -> RoutePlan | None:
        route_cfg = self.config.route_planning
        if not route_cfg or not route_cfg.enabled:
            return None
        if not self.settings.google_maps_api_key:
            console.print(
                "[yellow]⚠ RouteAgent: GOOGLE_MAPS_API_KEY no configurada — omitiendo rutas"
            )
            return None
        if route_cfg.origin_lat == 0.0 and route_cfg.origin_lng == 0.0:
            console.print(
                "[yellow]⚠ RouteAgent: origen inválido (lat/lng=0) — omitiendo rutas"
            )
            return None

        origin = {
            "lat": route_cfg.origin_lat,
            "lng": route_cfg.origin_lng,
            "place_id": "",
        }
        visitable = [
            lead
            for lead in leads
            if lead.tier in route_cfg.tiers_to_visit and _has_coordinates(lead)
        ]
        if not visitable:
            console.print(
                "[yellow]⚠ RouteAgent: no hay leads visitables con coordenadas válidas"
            )
            return None

        # Inclusion prioritizes commercial urgency and then physical effort.
        visitable.sort(
            key=lambda lead: (
                lead.contact_priority,
                straight_line_distance_km(origin, {"lat": lead.lat, "lng": lead.lng}),
                -lead.final_score,
            )
        )

        if len(visitable) > route_cfg.max_waypoints_per_route:
            console.print(
                "[yellow]⚠ RouteAgent: "
                f"{len(visitable)} leads visitables exceden el límite; "
                f"se usarán las primeras {route_cfg.max_waypoints_per_route}"
            )
            visitable = visitable[: route_cfg.max_waypoints_per_route]

        waypoint_inputs = [
            {
                "lat": lead.lat,
                "lng": lead.lng,
                "place_id": lead.place_id,
            }
            for lead in visitable
        ]
        try:
            result = compute_optimized_route(
                api_key=self.settings.google_maps_api_key,
                origin=origin,
                waypoints=waypoint_inputs,
                travel_mode=route_cfg.travel_mode,
                departure_time=route_cfg.departure_time,
            )
        except RouteToolError as exc:
            console.print(f"[yellow]⚠ RouteAgent: {exc}")
            return None

        optimized_order = _normalize_optimized_order(
            result.get("optimized_order", []),
            len(visitable),
        )
        optimized_leads = [visitable[index] for index in optimized_order]
        ordered_points = [
            {"lat": lead.lat, "lng": lead.lng, "place_id": lead.place_id}
            for lead in optimized_leads
        ]
        legs = result.get("legs", [])

        arrival_minutes = 0.0
        route_waypoints: list[RouteWaypoint] = []
        for index, lead in enumerate(optimized_leads):
            if index < len(legs):
                arrival_minutes += legs[index].get("duration_s", 0) / 60.0
            next_leg = legs[index + 1] if index + 1 < len(legs) else {}
            route_waypoints.append(
                RouteWaypoint(
                    lead_name=lead.name,
                    address=lead.address,
                    lat=lead.lat,
                    lng=lead.lng,
                    place_id=lead.place_id,
                    tier=lead.tier,
                    contact_priority=lead.contact_priority,
                    final_score=round(lead.final_score, 2),
                    phone=lead.phone or lead.whatsapp_number,
                    visit_order=index + 1,
                    estimated_arrival_minutes=round(arrival_minutes, 1),
                    distance_to_next_km=round(
                        next_leg.get("distance_m", 0) / 1000.0,
                        2,
                    ),
                    duration_to_next_minutes=round(
                        next_leg.get("duration_s", 0) / 60.0,
                        1,
                    ),
                    google_maps_url=build_google_maps_place_url(
                        {
                            "lat": lead.lat,
                            "lng": lead.lng,
                            "place_id": lead.place_id,
                        }
                    ),
                )
            )

        google_maps_urls = build_google_maps_url(
            origin=origin,
            waypoints=ordered_points,
            destination=origin,
            travel_mode=travel_mode_for_google_maps(route_cfg.travel_mode),
        )
        total_distance_km = round(result.get("total_distance_m", 0) / 1000.0, 2)
        total_duration_minutes = round(result.get("total_duration_s", 0) / 60.0, 1)

        console.print(
            "[green]🗺️ Ruta optimizada: "
            f"{len(route_waypoints)} paradas, "
            f"{total_distance_km:.2f} km, "
            f"{total_duration_minutes:.1f} min"
        )

        return RoutePlan(
            origin=route_cfg.origin_address
            or f"{route_cfg.origin_lat:.6f},{route_cfg.origin_lng:.6f}",
            waypoints=route_waypoints,
            total_distance_km=total_distance_km,
            total_duration_minutes=total_duration_minutes,
            google_maps_urls=google_maps_urls,
            route_groups=max(1, len(google_maps_urls)),
        )


def _has_coordinates(lead: QualifiedLead) -> bool:
    return bool(lead.lat or lead.lng) and not (lead.lat == 0.0 and lead.lng == 0.0)


def _normalize_optimized_order(order: list[int], size: int) -> list[int]:
    if len(order) != size or sorted(order) != list(range(size)):
        return list(range(size))
    return order
