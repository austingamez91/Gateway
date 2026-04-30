from __future__ import annotations

from gatewaykit.config import RouteConfig, parse_config
from gatewaykit.routing import find_route, route_matches


def routes() -> list[RouteConfig]:
    config = parse_config(
        {
            "gateway": {"port": 8080},
            "routes": [
                {
                    "path": "/abcd/",
                    "methods": ["GET"],
                    "upstream": {"url": "http://localhost:3001"},
                },
                {
                    "path": "/abcd/efg",
                    "methods": ["GET"],
                    "upstream": {"url": "http://localhost:3002"},
                },
                {
                    "path": "/api/user",
                    "methods": ["GET"],
                    "upstream": {"url": "http://localhost:3003"},
                },
            ],
        }
    )
    return config.routes


def test_route_matches_exact_path() -> None:
    assert route_matches("/api/user", "/api/user") is True


def test_route_matches_path_segment_prefix() -> None:
    assert route_matches("/api/user/123", "/api/user") is True


def test_route_does_not_match_partial_segment() -> None:
    assert route_matches("/api/users", "/api/user") is False


def test_find_route_uses_longest_prefix_match() -> None:
    route = find_route("/abcd/efg/hijk", routes())

    assert route is not None
    assert route.path == "/abcd/efg"


def test_find_route_returns_none_without_match() -> None:
    assert find_route("/unknown", routes()) is None
