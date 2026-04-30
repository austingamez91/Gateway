"""FastAPI application factory for GatewayKit."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from gatewaykit.config import GatewayConfig
from gatewaykit.policies import InMemoryCircuitBreaker, InMemoryRateLimiter, check_api_key
from gatewaykit.proxy import proxy_request
from gatewaykit.routing import find_route
from gatewaykit.upstreams import (
    ActiveHealthChecker,
    InMemoryUpstreamHealth,
    InMemoryUpstreamSelector,
    health_checked_routes,
)


def create_app(
    config: GatewayConfig,
    upstream_transport: httpx.AsyncBaseTransport | None = None,
    rate_limiter: InMemoryRateLimiter | None = None,
    upstream_selector: InMemoryUpstreamSelector | None = None,
    circuit_breaker: InMemoryCircuitBreaker | None = None,
) -> FastAPI:
    started_at = time.monotonic()
    limiter = rate_limiter or InMemoryRateLimiter()
    upstream_health = (
        upstream_selector.health
        if upstream_selector is not None
        else InMemoryUpstreamHealth()
    )
    selector = upstream_selector or InMemoryUpstreamSelector(upstream_health)
    breaker = circuit_breaker or InMemoryCircuitBreaker()
    health_checker = ActiveHealthChecker(config, upstream_health, upstream_transport)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        health_task: asyncio.Task[None] | None = None
        if health_checked_routes(config):
            health_task = asyncio.create_task(health_checker.run())

        try:
            yield
        finally:
            if health_task is not None:
                health_checker.stop()
                health_task.cancel()
                with suppress(asyncio.CancelledError):
                    await health_task

    app = FastAPI(title="GatewayKit", lifespan=lifespan)
    app.state.config = config
    app.state.rate_limiter = limiter
    app.state.upstream_selector = selector
    app.state.circuit_breaker = breaker
    app.state.upstream_health = upstream_health
    app.state.health_checker = health_checker

    @app.get("/health")
    async def health() -> dict[str, int | str]:
        return {
            "status": "healthy",
            "uptime_seconds": int(time.monotonic() - started_at),
        }

    @app.api_route(
        "/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    )
    async def gateway_route(request: Request) -> Response:
        route = find_route(request.url.path, config.routes)
        if route is None:
            return JSONResponse({"error": "not_found"}, status_code=404)

        if request.method.upper() not in route.methods:
            return JSONResponse({"error": "method_not_allowed"}, status_code=405)

        auth = check_api_key(request, route)
        if not auth.allowed:
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        rate_limit = await limiter.check(request, route, config)
        if not rate_limit.allowed:
            return JSONResponse(
                {
                    "error": "rate_limited",
                    "retry_after": rate_limit.retry_after_seconds,
                },
                status_code=429,
                headers={"Retry-After": str(rate_limit.retry_after_seconds)},
            )

        circuit = await breaker.before_request(route)
        if not circuit.allowed:
            return JSONResponse(
                {
                    "error": "service_unavailable",
                    "retry_after": circuit.retry_after_seconds,
                },
                status_code=503,
                headers={"Retry-After": str(circuit.retry_after_seconds)},
            )

        proxy_result = await proxy_request(
            request,
            route,
            await selector.select(route),
            config.gateway.global_timeout,
            upstream_transport,
        )
        await breaker.after_request(route, failed=proxy_result.failed)
        return proxy_result.response

    return app
