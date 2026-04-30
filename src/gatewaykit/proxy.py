"""HTTP proxying primitives for GatewayKit."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import Request
from starlette.responses import Response

from gatewaykit.config import (
    HeaderTransformConfig,
    RequestBodyTransformConfig,
    ResponseBodyTransformConfig,
    RouteConfig,
    parse_duration_seconds,
)

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


@dataclass(frozen=True)
class ProxyResult:
    response: Response
    failed: bool


async def proxy_request(
    request: Request,
    route: RouteConfig,
    upstream_base_url: str,
    global_timeout: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ProxyResult:
    request_started_at = time.time()
    upstream_url = build_upstream_url(
        upstream_base_url,
        build_forward_path(route, request.url.path),
        request.url.query,
    )
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in REQUEST_EXCLUDED_HEADERS
    }
    apply_header_transform(
        headers,
        route.request_transform.headers if route.request_transform else None,
        context={
            "request_time": str(int(request_started_at)),
            "route_path": route.path,
        },
    )
    body = await request.body()
    request_body_transform = route.request_transform.body if route.request_transform else None
    if request_body_transform is not None:
        try:
            body = transform_request_body(
                body,
                request_body_transform,
                context={
                    "request_time": str(int(request_started_at)),
                    "route_path": route.path,
                },
            )
        except ValueError:
            return ProxyResult(json_error("invalid_request_body", 400), failed=False)
        remove_headers(headers, ["Content-Type"])
        headers["Content-Type"] = "application/json"
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
            return ProxyResult(json_error("upstream_timeout", 504), failed=True)
        except httpx.RequestError:
            return ProxyResult(json_error("upstream_unavailable", 502), failed=True)

    response_headers = {
        key: value
        for key, value in upstream_response.headers.items()
        if key.lower() not in RESPONSE_EXCLUDED_HEADERS
    }
    apply_header_transform(
        response_headers,
        route.response_transform.headers if route.response_transform else None,
        context={
            "request_time": str(int(request_started_at)),
            "response_time": str(int(time.time())),
            "route_path": route.path,
        },
    )
    response_body = upstream_response.content
    media_type = upstream_response.headers.get("content-type")
    response_body_transform = route.response_transform.body if route.response_transform else None
    if response_body_transform is not None:
        try:
            response_body = transform_response_body(
                response_body,
                response_body_transform,
                context={
                    "request_time": str(int(request_started_at)),
                    "response_time": str(int(time.time())),
                    "route_path": route.path,
                },
            )
        except ValueError:
            return ProxyResult(json_error("invalid_upstream_body", 502), failed=True)
        remove_headers(response_headers, ["Content-Type"])
        media_type = "application/json"
    response = Response(
        content=response_body,
        status_code=upstream_response.status_code,
        headers=response_headers,
        media_type=media_type,
    )
    return ProxyResult(response, failed=upstream_response.status_code >= 500)


def transform_request_body(
    body: bytes,
    transform: RequestBodyTransformConfig,
    context: dict[str, str],
) -> bytes:
    source = parse_json_body(body)
    mapped: dict[str, object] = {}
    for destination_path, source_path in transform.mapping.items():
        set_path(mapped, destination_path, resolve_template_value(source_path, source, context))
    return encode_json(mapped)


def transform_response_body(
    body: bytes,
    transform: ResponseBodyTransformConfig,
    context: dict[str, str],
) -> bytes:
    original_body = parse_json_body(body)
    enveloped = resolve_template_tree(transform.envelope, original_body, context)
    return encode_json(enveloped)


def parse_json_body(body: bytes) -> object:
    try:
        return json.loads(body.decode() or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("body transform requires JSON") from exc


def encode_json(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode()


def resolve_template_tree(template: object, body: object, context: dict[str, str]) -> object:
    if isinstance(template, dict):
        return {
            key: resolve_template_tree(value, body, context)
            for key, value in template.items()
        }
    if isinstance(template, list):
        return [resolve_template_tree(item, body, context) for item in template]
    if isinstance(template, str):
        return resolve_template_value(template, body, context)
    return template


def resolve_template_value(value: str, body: object, context: dict[str, str]) -> object:
    if value == "$body":
        return body
    if value.startswith("$literal:"):
        return value.removeprefix("$literal:")
    if value.startswith("$"):
        return context.get(value.removeprefix("$"), value)
    return get_path(body, value)


def get_path(value: object, path: str) -> object:
    current = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def set_path(target: dict[str, object], path: str, value: object) -> None:
    current = target
    parts = path.split(".")
    for part in parts[:-1]:
        next_value = current.setdefault(part, {})
        if not isinstance(next_value, dict):
            next_value = {}
            current[part] = next_value
        current = next_value
    current[parts[-1]] = value


def apply_header_transform(
    headers: dict[str, str],
    transform: HeaderTransformConfig | None,
    context: dict[str, str],
) -> dict[str, str]:
    if transform is None:
        return headers

    remove_headers(headers, transform.remove)
    for key, value in transform.add.items():
        headers[key] = resolve_dynamic_value(value, context)
    return headers


def remove_headers(headers: dict[str, str], names: list[str]) -> None:
    to_remove = {name.lower() for name in names}
    for key in list(headers):
        if key.lower() in to_remove:
            del headers[key]


def resolve_dynamic_value(value: str, context: dict[str, str]) -> str:
    if value.startswith("$literal:"):
        return value.removeprefix("$literal:")
    if value.startswith("$"):
        return context.get(value.removeprefix("$"), value)
    return value


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
