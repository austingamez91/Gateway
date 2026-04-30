"""FastAPI application factory for GatewayKit."""

from __future__ import annotations

import time

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from gatewaykit.config import GatewayConfig
from gatewaykit.policies import InMemoryRateLimiter, check_api_key
from gatewaykit.proxy import proxy_request
from gatewaykit.routing import find_route


def create_app(
    config: GatewayConfig,
    upstream_transport: httpx.AsyncBaseTransport | None = None,
    rate_limiter: InMemoryRateLimiter | None = None,
) -> FastAPI:
    started_at = time.monotonic()
    limiter = rate_limiter or InMemoryRateLimiter()
    app = FastAPI(title="GatewayKit")
    app.state.config = config
    app.state.rate_limiter = limiter

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
    async def gateway_route(request: Request) -> JSONResponse:
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

        return await proxy_request(
            request,
            route,
            config.gateway.global_timeout,
            upstream_transport,
        )

    return app
