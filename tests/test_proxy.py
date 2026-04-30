from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from httpx import Response

from gatewaykit.app import create_app
from gatewaykit.config import RouteConfig, parse_config
from gatewaykit.proxy import build_forward_path, build_upstream_url


def gateway_config(upstream_url: str = "http://upstream.test", strip_prefix: bool = False) -> dict:
    return {
        "gateway": {"port": 8080},
        "routes": [
            {
                "path": "/api/users",
                "methods": ["GET", "POST"],
                "strip_prefix": strip_prefix,
                "upstream": {"url": upstream_url},
            }
        ],
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
