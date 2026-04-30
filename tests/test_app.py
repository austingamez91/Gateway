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
