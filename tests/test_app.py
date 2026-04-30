from __future__ import annotations

from fastapi.testclient import TestClient

from gatewaykit.app import create_app
from gatewaykit.config import parse_config


def test_health_returns_required_shape() -> None:
    config = parse_config({"gateway": {"port": 8080}, "routes": []})
    client = TestClient(create_app(config))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert isinstance(response.json()["uptime_seconds"], int)
    assert response.json()["uptime_seconds"] >= 0


def test_unmatched_route_returns_404() -> None:
    config = parse_config({"gateway": {"port": 8080}, "routes": []})
    client = TestClient(create_app(config))

    response = client.get("/missing")

    assert response.status_code == 404
    assert response.json() == {"error": "not_found"}


def test_matched_route_with_disallowed_method_returns_405() -> None:
    config = parse_config(
        {
            "gateway": {"port": 8080},
            "routes": [
                {
                    "path": "/api/products",
                    "methods": ["GET"],
                    "upstream": {"url": "http://localhost:3001"},
                }
            ],
        }
    )
    client = TestClient(create_app(config))

    response = client.post("/api/products")

    assert response.status_code == 405
    assert response.json() == {"error": "method_not_allowed"}


def test_matched_route_uses_longest_prefix() -> None:
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
            ],
        }
    )
    client = TestClient(create_app(config))

    response = client.get("/abcd/efg/hijk")

    assert response.status_code == 501
    assert response.json()["route_path"] == "/abcd/efg"
