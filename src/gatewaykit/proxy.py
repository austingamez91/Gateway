"""HTTP proxying primitives for GatewayKit."""

from __future__ import annotations

import asyncio
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import Request
from starlette.responses import Response

from gatewaykit.config import RouteConfig, parse_duration_seconds

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
REQUEST_EXCLUDED_HEADERS = HOP_BY_HOP_HEADERS | {"host", "content-length"}
RESPONSE_EXCLUDED_HEADERS = HOP_BY_HOP_HEADERS | {"content-length"}


async def proxy_request(
    request: Request,
    route: RouteConfig,
    global_timeout: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Response:
    if route.upstream.url is None:
        return json_error("upstream_targets_not_implemented", 501)

    upstream_url = build_upstream_url(
        route.upstream.url,
        build_forward_path(route, request.url.path),
        request.url.query,
    )
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in REQUEST_EXCLUDED_HEADERS
    }
    body = await request.body()
    timeout = parse_duration_seconds(route.timeout or global_timeout)

    async with httpx.AsyncClient(transport=transport) as client:
        try:
            upstream_response = await send_with_retries(
                client,
                method=request.method,
                url=upstream_url,
                body=body,
                headers=headers,
                timeout=timeout,
                route=route,
            )
        except httpx.TimeoutException:
            return json_error("upstream_timeout", 504)
        except httpx.RequestError:
            return json_error("upstream_unavailable", 502)

    response_headers = {
        key: value
        for key, value in upstream_response.headers.items()
        if key.lower() not in RESPONSE_EXCLUDED_HEADERS
    }
    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=response_headers,
        media_type=upstream_response.headers.get("content-type"),
    )


async def send_with_retries(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    body: bytes,
    headers: dict[str, str],
    timeout: float,
    route: RouteConfig,
) -> httpx.Response:
    max_attempts = max(1, route.retry.attempts) if route.retry else 1
    attempt = 1

    while True:
        response = await client.request(
            method,
            url,
            content=body,
            headers=headers,
            timeout=timeout,
        )
        if route.retry is None:
            return response
        if response.status_code not in route.retry.on:
            return response
        if attempt >= max_attempts:
            return response

        await asyncio.sleep(retry_delay_seconds(route, attempt))
        attempt += 1


def retry_delay_seconds(route: RouteConfig, completed_attempts: int) -> float:
    if route.retry is None:
        return 0.0

    initial_delay = parse_duration_seconds(route.retry.initial_delay)
    if route.retry.backoff == "fixed":
        return initial_delay
    return initial_delay * (2 ** (completed_attempts - 1))


def build_upstream_url(base_url: str, request_path: str, query: str) -> str:
    parts = urlsplit(base_url)
    base_path = parts.path.rstrip("/")
    proxy_path = request_path if request_path.startswith("/") else f"/{request_path}"
    path = f"{base_path}{proxy_path}" if base_path else proxy_path
    return urlunsplit((parts.scheme, parts.netloc, path, query, ""))


def build_forward_path(route: RouteConfig, request_path: str) -> str:
    if not route.strip_prefix:
        return request_path

    route_path = route.path.rstrip("/")
    if route_path in {"", "/"}:
        return request_path

    remainder = request_path[len(route_path) :]
    if not remainder:
        return "/"

    return remainder if remainder.startswith("/") else f"/{remainder}"


def json_error(error: str, status_code: int) -> Response:
    return Response(
        content=f'{{"error":"{error}"}}',
        status_code=status_code,
        media_type="application/json",
    )
