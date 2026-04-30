from __future__ import annotations

from fastapi.testclient import TestClient

from gatewaykit.mock_upstream import create_mock_upstream_app


def test_mock_upstream_echoes_request_details() -> None:
    client = TestClient(create_mock_upstream_app("users"))

    response = client.post(
        "/api/users/123?debug=true",
        headers={"Content-Type": "application/json", "X-API-Key": "secret"},
        content='{"name":"Ada"}',
    )

    assert response.status_code == 200
    assert response.json()["upstream"] == "users"
    assert response.json()["method"] == "POST"
    assert response.json()["path"] == "/api/users/123"
    assert response.json()["query"] == "debug=true"
    assert response.json()["body"] == '{"name":"Ada"}'
    assert "x-api-key" not in response.json()["headers"]


def test_mock_upstream_flaky_endpoint_alternates_failure_and_success() -> None:
    client = TestClient(create_mock_upstream_app("orders"))

    first = client.get("/flaky")
    second = client.get("/flaky")

    assert first.status_code == 503
    assert second.status_code == 200
    assert second.json()["status"] == "recovered"
