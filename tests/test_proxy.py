from __future__ import annotations

import json

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from httpx import Response

from gatewaykit.app import create_app
from gatewaykit.config import RouteConfig, parse_config
from gatewaykit.proxy import (
    apply_header_transform,
    build_forward_path,
    build_upstream_url,
    retry_delay_seconds,
    transform_request_body,
    transform_response_body,
)


def json_loads(body: bytes) -> dict:
    return json.loads(body.decode())


def gateway_config(
    upstream_url: str = "http://upstream.test",
    upstream: dict | None = None,
    strip_prefix: bool = False,
    global_timeout: str = "30s",
    route_timeout: str | None = None,
    global_rate_limit: dict | None = None,
    route_rate_limit: dict | None = None,
    auth: dict | None = None,
    retry: dict | None = None,
    circuit_breaker: dict | None = None,
    request_transform: dict | None = None,
    response_transform: dict | None = None,
) -> dict:
    route = {
        "path": "/api/users",
        "methods": ["GET", "POST"],
        "strip_prefix": strip_prefix,
        "upstream": upstream or {"url": upstream_url},
    }
    if route_timeout is not None:
        route["timeout"] = route_timeout
    if route_rate_limit is not None:
        route["rate_limit"] = route_rate_limit
    if auth is not None:
        route["auth"] = auth
    if retry is not None:
        route["retry"] = retry
    if circuit_breaker is not None:
        route["circuit_breaker"] = circuit_breaker
    if request_transform is not None:
        route["request_transform"] = request_transform
    if response_transform is not None:
        route["response_transform"] = response_transform
    gateway = {"port": 8080, "global_timeout": global_timeout}
    if global_rate_limit is not None:
        gateway["global_rate_limit"] = global_rate_limit
    return {
        "gateway": gateway,
        "routes": [route],
    }


def mock_upstream_app() -> FastAPI:
    app = FastAPI()

    @app.api_route("/{path:path}", methods=["GET", "POST"])
    async def echo(request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "method": request.method,
                "path": request.url.path,
                "query": request.url.query,
                "body": (await request.body()).decode(),
                "content_type": request.headers.get("content-type"),
                "connection": request.headers.get("connection"),
                "te": request.headers.get("te"),
            },
            status_code=201 if request.method == "POST" else 200,
            headers={"X-Upstream": "mock"},
        )

    return app


@pytest.mark.asyncio
async def test_proxies_get_to_single_upstream_url_and_preserves_query_string() -> None:
    upstream_transport = httpx.ASGITransport(app=mock_upstream_app())
    gateway = create_app(parse_config(gateway_config()), upstream_transport=upstream_transport)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway.test",
    ) as client:
        response = await client.get("/api/users/123?active=true&sort=name")

    assert response.status_code == 200
    assert response.headers["x-upstream"] == "mock"
    assert response.json()["method"] == "GET"
    assert response.json()["path"] == "/api/users/123"
    assert response.json()["query"] == "active=true&sort=name"


@pytest.mark.asyncio
async def test_proxies_post_body_to_single_upstream_url() -> None:
    upstream_transport = httpx.ASGITransport(app=mock_upstream_app())
    gateway = create_app(parse_config(gateway_config()), upstream_transport=upstream_transport)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway.test",
    ) as client:
        response = await client.post(
            "/api/users",
            content='{"name":"Ada"}',
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 201
    assert response.json()["method"] == "POST"
    assert response.json()["path"] == "/api/users"
    assert response.json()["body"] == '{"name":"Ada"}'
    assert response.json()["content_type"] == "application/json"


@pytest.mark.asyncio
async def test_single_upstream_proxy_preserves_upstream_status_and_body() -> None:
    app = FastAPI()

    @app.get("/api/users/missing")
    async def missing() -> PlainTextResponse:
        return PlainTextResponse("not here", status_code=418)

    gateway = create_app(
        parse_config(gateway_config()),
        upstream_transport=httpx.ASGITransport(app=app),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway.test",
    ) as client:
        response = await client.get("/api/users/missing")

    assert response.status_code == 418
    assert response.text == "not here"


def test_build_upstream_url_preserves_base_path_and_query() -> None:
    url = build_upstream_url(
        "http://upstream.test/base",
        "/api/users",
        "page=1",
    )

    assert url == "http://upstream.test/base/api/users?page=1"


def test_apply_header_transform_adds_removes_and_resolves_values() -> None:
    headers = {"X-Debug": "true", "X-Keep": "yes"}
    transform = parse_config(
        {
            "gateway": {"port": 8080},
            "routes": [
                {
                    "path": "/api/users",
                    "methods": ["GET"],
                    "upstream": {"url": "http://upstream.test"},
                    "request_transform": {
                        "headers": {
                            "add": {
                                "X-Gateway": "gatewaykit",
                                "X-Request-Start": "$request_time",
                                "X-Literal": "$literal:value",
                            },
                            "remove": ["X-Debug"],
                        }
                    },
                }
            ],
        }
    ).routes[0].request_transform.headers

    apply_header_transform(headers, transform, {"request_time": "123"})

    assert headers == {
        "X-Keep": "yes",
        "X-Gateway": "gatewaykit",
        "X-Request-Start": "123",
        "X-Literal": "value",
    }


def test_transform_request_body_maps_source_paths_and_dynamic_values() -> None:
    transform = parse_config(
        {
            "gateway": {"port": 8080},
            "routes": [
                {
                    "path": "/api/users",
                    "methods": ["POST"],
                    "upstream": {"url": "http://upstream.test"},
                    "request_transform": {
                        "body": {
                            "mapping": {
                                "user.id": "userId",
                                "user.name": "userName",
                                "meta.source": "$literal:gateway",
                                "meta.timestamp": "$request_time",
                            }
                        }
                    },
                }
            ],
        }
    ).routes[0].request_transform.body

    transformed = transform_request_body(
        b'{"userId":123,"userName":"Ada"}',
        transform,
        {"request_time": "100"},
    )

    assert transformed == (
        b'{"user":{"id":123,"name":"Ada"},"meta":{"source":"gateway","timestamp":"100"}}'
    )


def test_transform_response_body_wraps_original_body_in_envelope() -> None:
    transform = parse_config(
        {
            "gateway": {"port": 8080},
            "routes": [
                {
                    "path": "/api/users",
                    "methods": ["GET"],
                    "upstream": {"url": "http://upstream.test"},
                    "response_transform": {
                        "body": {
                            "envelope": {
                                "data": "$body",
                                "gateway_metadata": {
                                    "served_at": "$response_time",
                                    "route": "$route_path",
                                },
                            }
                        }
                    },
                }
            ],
        }
    ).routes[0].response_transform.body

    transformed = transform_response_body(
        b'{"ok":true}',
        transform,
        {"response_time": "200", "route_path": "/api/users"},
    )

    assert transformed == (
        b'{"data":{"ok":true},"gateway_metadata":{"served_at":"200","route":"/api/users"}}'
    )


def test_build_forward_path_keeps_original_path_without_strip_prefix() -> None:
    route = route_config(path="/api/users", strip_prefix=False)

    assert build_forward_path(route, "/api/users/123") == "/api/users/123"


def test_build_forward_path_strips_matched_prefix() -> None:
    route = route_config(path="/api/products", strip_prefix=True)

    assert build_forward_path(route, "/api/products/123") == "/123"


def test_build_forward_path_strips_exact_match_to_root() -> None:
    route = route_config(path="/api/products", strip_prefix=True)

    assert build_forward_path(route, "/api/products") == "/"


def route_config(path: str, strip_prefix: bool) -> RouteConfig:
    return parse_config(
        {
            "gateway": {"port": 8080},
            "routes": [
                {
                    "path": path,
                    "methods": ["GET"],
                    "strip_prefix": strip_prefix,
                    "upstream": {"url": "http://upstream.test"},
                }
            ],
        }
    ).routes[0]


@pytest.mark.asyncio
async def test_proxy_uses_longest_prefix_route_upstream() -> None:
    config = parse_config(
        {
            "gateway": {"port": 8080},
            "routes": [
                {
                    "path": "/abcd/",
                    "methods": ["GET"],
                    "upstream": {"url": "http://broad.test"},
                },
                {
                    "path": "/abcd/efg",
                    "methods": ["GET"],
                    "upstream": {"url": "http://specific.test"},
                },
            ],
        }
    )

    def handler(request: httpx.Request) -> Response:
        return Response(200, json={"upstream_url": str(request.url)})

    gateway = create_app(config, upstream_transport=httpx.MockTransport(handler))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway.test",
    ) as client:
        response = await client.get("/abcd/efg/hijk")

    assert response.status_code == 200
    assert response.json()["upstream_url"] == "http://specific.test/abcd/efg/hijk"


@pytest.mark.asyncio
async def test_proxy_selects_multiple_upstream_targets() -> None:
    seen_hosts: list[str] = []

    def handler(request: httpx.Request) -> Response:
        seen_hosts.append(request.url.host or "")
        return Response(200, json={"host": request.url.host})

    gateway = create_app(
        parse_config(
            gateway_config(
                upstream={
                    "targets": [
                        {"url": "http://a.test"},
                        {"url": "http://b.test"},
                    ],
                    "balance": "round_robin",
                }
            )
        ),
        upstream_transport=httpx.MockTransport(handler),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway.test",
    ) as client:
        first = await client.get("/api/users")
        second = await client.get("/api/users")
        third = await client.get("/api/users")

    assert first.json()["host"] == "a.test"
    assert second.json()["host"] == "b.test"
    assert third.json()["host"] == "a.test"
    assert seen_hosts == ["a.test", "b.test", "a.test"]


@pytest.mark.asyncio
async def test_proxy_selects_weighted_upstream_targets() -> None:
    seen_hosts: list[str] = []

    def handler(request: httpx.Request) -> Response:
        seen_hosts.append(request.url.host or "")
        return Response(200, json={"host": request.url.host})

    gateway = create_app(
        parse_config(
            gateway_config(
                upstream={
                    "targets": [
                        {"url": "http://a.test", "weight": 2},
                        {"url": "http://b.test", "weight": 1},
                    ],
                    "balance": "weighted_round_robin",
                }
            )
        ),
        upstream_transport=httpx.MockTransport(handler),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway.test",
    ) as client:
        for _ in range(4):
            await client.get("/api/users")

    assert seen_hosts == ["a.test", "a.test", "b.test", "a.test"]


@pytest.mark.asyncio
async def test_proxy_applies_strip_prefix_before_forwarding() -> None:
    upstream_transport = httpx.ASGITransport(app=mock_upstream_app())
    gateway = create_app(
        parse_config(gateway_config(strip_prefix=True)),
        upstream_transport=upstream_transport,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway.test",
    ) as client:
        response = await client.get("/api/users/123?active=true")

    assert response.status_code == 200
    assert response.json()["path"] == "/123"
    assert response.json()["query"] == "active=true"


@pytest.mark.asyncio
async def test_proxy_strips_hop_by_hop_request_headers() -> None:
    upstream_transport = httpx.ASGITransport(app=mock_upstream_app())
    gateway = create_app(parse_config(gateway_config()), upstream_transport=upstream_transport)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway.test",
    ) as client:
        response = await client.get(
            "/api/users",
            headers={"TE": "trailers"},
        )

    assert response.status_code == 200
    assert response.json()["te"] is None


@pytest.mark.asyncio
async def test_proxy_strips_hop_by_hop_response_headers() -> None:
    def handler(_request: httpx.Request) -> Response:
        return Response(
            200,
            json={"ok": True},
            headers={"Connection": "close", "X-Upstream": "mock"},
        )

    gateway = create_app(
        parse_config(gateway_config()),
        upstream_transport=httpx.MockTransport(handler),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway.test",
    ) as client:
        response = await client.get("/api/users")

    assert response.status_code == 200
    assert response.headers.get("connection") is None
    assert response.headers["x-upstream"] == "mock"


@pytest.mark.asyncio
async def test_request_header_transform_adds_and_removes_headers_before_proxying() -> None:
    captured_headers: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> Response:
        captured_headers["x-gateway"] = request.headers.get("x-gateway")
        captured_headers["x-request-start"] = request.headers.get("x-request-start")
        captured_headers["x-debug"] = request.headers.get("x-debug")
        return Response(200, json={"ok": True})

    gateway = create_app(
        parse_config(
            gateway_config(
                request_transform={
                    "headers": {
                        "add": {
                            "X-Gateway": "gatewaykit",
                            "X-Request-Start": "$request_time",
                        },
                        "remove": ["X-Debug"],
                    }
                }
            )
        ),
        upstream_transport=httpx.MockTransport(handler),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway.test",
    ) as client:
        response = await client.get("/api/users", headers={"X-Debug": "true"})

    assert response.status_code == 200
    assert captured_headers["x-gateway"] == "gatewaykit"
    assert captured_headers["x-request-start"] is not None
    assert captured_headers["x-debug"] is None


@pytest.mark.asyncio
async def test_response_header_transform_adds_and_removes_headers_before_returning() -> None:
    def handler(_request: httpx.Request) -> Response:
        return Response(
            200,
            json={"ok": True},
            headers={"Server": "upstream", "X-Powered-By": "test"},
        )

    gateway = create_app(
        parse_config(
            gateway_config(
                response_transform={
                    "headers": {
                        "add": {
                            "X-Served-By": "gatewaykit",
                            "X-Served-At": "$response_time",
                        },
                        "remove": ["Server", "X-Powered-By"],
                    }
                }
            )
        ),
        upstream_transport=httpx.MockTransport(handler),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway.test",
    ) as client:
        response = await client.get("/api/users")

    assert response.status_code == 200
    assert response.headers["x-served-by"] == "gatewaykit"
    assert response.headers["x-served-at"].isdigit()
    assert "server" not in response.headers
    assert "x-powered-by" not in response.headers


@pytest.mark.asyncio
async def test_request_body_mapping_transforms_json_body_before_proxying() -> None:
    captured_body: dict | None = None
    captured_content_type: str | None = None

    def handler(request: httpx.Request) -> Response:
        nonlocal captured_body, captured_content_type
        captured_body = json_loads(request.content)
        captured_content_type = request.headers.get("content-type")
        return Response(200, json={"ok": True})

    gateway = create_app(
        parse_config(
            gateway_config(
                request_transform={
                    "body": {
                        "mapping": {
                            "user.id": "userId",
                            "user.name": "userName",
                            "meta.source": "$literal:gateway",
                            "meta.timestamp": "$request_time",
                        }
                    }
                }
            )
        ),
        upstream_transport=httpx.MockTransport(handler),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway.test",
    ) as client:
        response = await client.post(
            "/api/users",
            content='{"userId":123,"userName":"Ada"}',
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 200
    assert captured_body["user"] == {"id": 123, "name": "Ada"}
    assert captured_body["meta"]["source"] == "gateway"
    assert captured_body["meta"]["timestamp"].isdigit()
    assert captured_content_type == "application/json"


@pytest.mark.asyncio
async def test_request_body_mapping_rejects_invalid_json_body() -> None:
    gateway = create_app(
        parse_config(
            gateway_config(
                request_transform={
                    "body": {
                        "mapping": {
                            "user.id": "userId",
                        }
                    }
                }
            )
        ),
        upstream_transport=httpx.ASGITransport(app=mock_upstream_app()),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway.test",
    ) as client:
        response = await client.post("/api/users", content="not-json")

    assert response.status_code == 400
    assert response.json() == {"error": "invalid_request_body"}


@pytest.mark.asyncio
async def test_response_body_envelope_wraps_upstream_json_before_returning() -> None:
    def handler(_request: httpx.Request) -> Response:
        return Response(200, json={"id": 123, "name": "Ada"})

    gateway = create_app(
        parse_config(
            gateway_config(
                response_transform={
                    "body": {
                        "envelope": {
                            "data": "$body",
                            "gateway_metadata": {
                                "served_at": "$response_time",
                                "route": "$route_path",
                            },
                        }
                    }
                }
            )
        ),
        upstream_transport=httpx.MockTransport(handler),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway.test",
    ) as client:
        response = await client.get("/api/users")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["data"] == {"id": 123, "name": "Ada"}
    assert response.json()["gateway_metadata"]["route"] == "/api/users"
    assert response.json()["gateway_metadata"]["served_at"].isdigit()


@pytest.mark.asyncio
async def test_response_body_envelope_returns_clean_error_for_invalid_upstream_json() -> None:
    def handler(_request: httpx.Request) -> Response:
        return Response(200, content=b"not-json", headers={"Content-Type": "text/plain"})

    gateway = create_app(
        parse_config(
            gateway_config(
                response_transform={
                    "body": {
                        "envelope": {
                            "data": "$body",
                        }
                    }
                }
            )
        ),
        upstream_transport=httpx.MockTransport(handler),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway.test",
    ) as client:
        response = await client.get("/api/users")

    assert response.status_code == 502
    assert response.json() == {"error": "invalid_upstream_body"}


@pytest.mark.asyncio
async def test_proxy_uses_global_timeout_when_route_timeout_is_absent() -> None:
    captured_timeout: dict[str, float] = {}

    def handler(request: httpx.Request) -> Response:
        captured_timeout.update(request.extensions["timeout"])
        return Response(200, json={"ok": True})

    gateway = create_app(
        parse_config(gateway_config(global_timeout="7s")),
        upstream_transport=httpx.MockTransport(handler),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway.test",
    ) as client:
        response = await client.get("/api/users")

    assert response.status_code == 200
    assert captured_timeout["connect"] == 7.0
    assert captured_timeout["read"] == 7.0


@pytest.mark.asyncio
async def test_proxy_route_timeout_overrides_global_timeout() -> None:
    captured_timeout: dict[str, float] = {}

    def handler(request: httpx.Request) -> Response:
        captured_timeout.update(request.extensions["timeout"])
        return Response(200, json={"ok": True})

    gateway = create_app(
        parse_config(gateway_config(global_timeout="30s", route_timeout="500ms")),
        upstream_transport=httpx.MockTransport(handler),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway.test",
    ) as client:
        response = await client.get("/api/users")

    assert response.status_code == 200
    assert captured_timeout["connect"] == 0.5
    assert captured_timeout["read"] == 0.5


@pytest.mark.asyncio
async def test_proxy_returns_clean_json_for_upstream_timeout() -> None:
    def handler(request: httpx.Request) -> Response:
        raise httpx.ReadTimeout("too slow", request=request)

    gateway = create_app(
        parse_config(gateway_config()),
        upstream_transport=httpx.MockTransport(handler),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway.test",
    ) as client:
        response = await client.get("/api/users")

    assert response.status_code == 504
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"error": "upstream_timeout"}


@pytest.mark.asyncio
async def test_proxy_returns_clean_json_for_upstream_network_failure() -> None:
    def handler(request: httpx.Request) -> Response:
        raise httpx.ConnectError("connection failed", request=request)

    gateway = create_app(
        parse_config(gateway_config()),
        upstream_transport=httpx.MockTransport(handler),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway.test",
    ) as client:
        response = await client.get("/api/users")

    assert response.status_code == 502
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"error": "upstream_unavailable"}


@pytest.mark.asyncio
async def test_global_rate_limit_returns_429_before_proxying() -> None:
    upstream_calls = 0

    def handler(_request: httpx.Request) -> Response:
        nonlocal upstream_calls
        upstream_calls += 1
        return Response(200, json={"ok": True})

    gateway = create_app(
        parse_config(
            gateway_config(
                global_rate_limit={
                    "requests": 1,
                    "window": "60s",
                    "strategy": "fixed_window",
                    "per": "global",
                }
            )
        ),
        upstream_transport=httpx.MockTransport(handler),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway.test",
    ) as client:
        first = await client.get("/api/users")
        second = await client.get("/api/users")

    assert first.status_code == 200
    assert second.status_code == 429
    retry_after = int(second.headers["retry-after"])
    assert 1 <= retry_after <= 60
    assert second.json() == {"error": "rate_limited", "retry_after": retry_after}
    assert upstream_calls == 1


@pytest.mark.asyncio
async def test_route_rate_limit_overrides_global_rate_limit() -> None:
    gateway = create_app(
        parse_config(
            gateway_config(
                global_rate_limit={
                    "requests": 1,
                    "window": "60s",
                    "strategy": "fixed_window",
                    "per": "global",
                },
                route_rate_limit={
                    "requests": 2,
                    "window": "60s",
                    "strategy": "fixed_window",
                    "per": "global",
                },
            )
        ),
        upstream_transport=httpx.ASGITransport(app=mock_upstream_app()),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway.test",
    ) as client:
        first = await client.get("/api/users")
        second = await client.get("/api/users")
        third = await client.get("/api/users")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429


@pytest.mark.asyncio
async def test_api_key_auth_rejects_missing_key_before_proxying() -> None:
    upstream_calls = 0

    def handler(_request: httpx.Request) -> Response:
        nonlocal upstream_calls
        upstream_calls += 1
        return Response(200, json={"ok": True})

    gateway = create_app(
        parse_config(
            gateway_config(
                auth={
                    "type": "api_key",
                    "header": "X-API-Key",
                    "keys": ["sk_live_abc123"],
                }
            )
        ),
        upstream_transport=httpx.MockTransport(handler),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway.test",
    ) as client:
        response = await client.get("/api/users")

    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized"}
    assert upstream_calls == 0


@pytest.mark.asyncio
async def test_api_key_auth_rejects_invalid_key_before_proxying() -> None:
    upstream_calls = 0

    def handler(_request: httpx.Request) -> Response:
        nonlocal upstream_calls
        upstream_calls += 1
        return Response(200, json={"ok": True})

    gateway = create_app(
        parse_config(
            gateway_config(
                auth={
                    "type": "api_key",
                    "header": "X-API-Key",
                    "keys": ["sk_live_abc123"],
                }
            )
        ),
        upstream_transport=httpx.MockTransport(handler),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway.test",
    ) as client:
        response = await client.get("/api/users", headers={"X-API-Key": "wrong"})

    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized"}
    assert upstream_calls == 0


@pytest.mark.asyncio
async def test_api_key_auth_allows_valid_key_to_proxy() -> None:
    gateway = create_app(
        parse_config(
            gateway_config(
                auth={
                    "type": "api_key",
                    "header": "X-API-Key",
                    "keys": ["sk_live_abc123"],
                }
            )
        ),
        upstream_transport=httpx.ASGITransport(app=mock_upstream_app()),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway.test",
    ) as client:
        response = await client.get("/api/users", headers={"X-API-Key": "sk_live_abc123"})

    assert response.status_code == 200
    assert response.json()["path"] == "/api/users"


@pytest.mark.asyncio
async def test_retry_policy_retries_configured_status_and_returns_success() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return Response(503, json={"error": "try again"})
        return Response(200, json={"ok": True})

    gateway = create_app(
        parse_config(
            gateway_config(
                retry={
                    "attempts": 3,
                    "backoff": "fixed",
                    "initial_delay": "1ms",
                    "on": [503],
                }
            )
        ),
        upstream_transport=httpx.MockTransport(handler),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway.test",
    ) as client:
        response = await client.get("/api/users")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert attempts == 2


@pytest.mark.asyncio
async def test_retry_policy_stops_after_configured_attempts() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> Response:
        nonlocal attempts
        attempts += 1
        return Response(503, json={"error": "still unavailable"})

    gateway = create_app(
        parse_config(
            gateway_config(
                retry={
                    "attempts": 3,
                    "backoff": "fixed",
                    "initial_delay": "1ms",
                    "on": [503],
                }
            )
        ),
        upstream_transport=httpx.MockTransport(handler),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway.test",
    ) as client:
        response = await client.get("/api/users")

    assert response.status_code == 503
    assert response.json() == {"error": "still unavailable"}
    assert attempts == 3


@pytest.mark.asyncio
async def test_retry_policy_ignores_unconfigured_status_codes() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> Response:
        nonlocal attempts
        attempts += 1
        return Response(500, json={"error": "not retried"})

    gateway = create_app(
        parse_config(
            gateway_config(
                retry={
                    "attempts": 3,
                    "backoff": "fixed",
                    "initial_delay": "1ms",
                    "on": [503],
                }
            )
        ),
        upstream_transport=httpx.MockTransport(handler),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway.test",
    ) as client:
        response = await client.get("/api/users")

    assert response.status_code == 500
    assert attempts == 1


def test_retry_delay_uses_fixed_or_exponential_backoff() -> None:
    fixed_route = retry_route_config("fixed")
    exponential_route = retry_route_config("exponential")

    assert retry_delay_seconds(fixed_route, completed_attempts=2) == 0.25
    assert retry_delay_seconds(exponential_route, completed_attempts=1) == 0.25
    assert retry_delay_seconds(exponential_route, completed_attempts=2) == 0.5


def retry_route_config(backoff: str) -> RouteConfig:
    return parse_config(
        {
            "gateway": {"port": 8080},
            "routes": [
                {
                    "path": "/retry",
                    "methods": ["GET"],
                    "upstream": {"url": "http://upstream.test"},
                    "retry": {
                        "attempts": 3,
                        "backoff": backoff,
                        "initial_delay": "250ms",
                        "on": [503],
                    },
                }
            ],
        }
    ).routes[0]


@pytest.mark.asyncio
async def test_circuit_breaker_returns_503_without_calling_open_upstream() -> None:
    upstream_calls = 0

    def handler(_request: httpx.Request) -> Response:
        nonlocal upstream_calls
        upstream_calls += 1
        return Response(503, json={"error": "unavailable"})

    gateway = create_app(
        parse_config(
            gateway_config(
                circuit_breaker={
                    "threshold": 2,
                    "window": "60s",
                    "cooldown": "30s",
                }
            )
        ),
        upstream_transport=httpx.MockTransport(handler),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway.test",
    ) as client:
        first = await client.get("/api/users")
        second = await client.get("/api/users")
        third = await client.get("/api/users")

    assert first.status_code == 503
    assert second.status_code == 503
    assert third.status_code == 503
    assert third.json()["error"] == "service_unavailable"
    assert 1 <= third.json()["retry_after"] <= 30
    assert upstream_calls == 2


@pytest.mark.asyncio
async def test_circuit_breaker_success_resets_gateway_failure_count() -> None:
    upstream_statuses = [503, 200, 503, 200]

    def handler(_request: httpx.Request) -> Response:
        return Response(upstream_statuses.pop(0), json={"remaining": len(upstream_statuses)})

    gateway = create_app(
        parse_config(
            gateway_config(
                circuit_breaker={
                    "threshold": 2,
                    "window": "60s",
                    "cooldown": "30s",
                }
            )
        ),
        upstream_transport=httpx.MockTransport(handler),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=gateway),
        base_url="http://gateway.test",
    ) as client:
        first = await client.get("/api/users")
        second = await client.get("/api/users")
        third = await client.get("/api/users")

    assert first.status_code == 503
    assert second.status_code == 200
    assert third.status_code == 503
