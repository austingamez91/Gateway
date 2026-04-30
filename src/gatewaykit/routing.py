"""Route matching for configured gateway routes."""

from __future__ import annotations

from gatewaykit.config import RouteConfig


def find_route(path: str, routes: list[RouteConfig]) -> RouteConfig | None:
    matches = [route for route in routes if route_matches(path, route.path)]
    if not matches:
        return None
    return max(matches, key=lambda route: len(route.path))


def route_matches(request_path: str, route_path: str) -> bool:
    if request_path == route_path:
        return True

    if route_path == "/":
        return request_path.startswith("/")

    normalized_route = route_path.rstrip("/")
    return request_path.startswith(f"{normalized_route}/")
