"""FastAPI application factory for GatewayKit."""

from __future__ import annotations

import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from gatewaykit.config import GatewayConfig
from gatewaykit.routing import find_route


def create_app(config: GatewayConfig) -> FastAPI:
    started_at = time.monotonic()
    app = FastAPI(title="GatewayKit")
    app.state.config = config

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

        return JSONResponse(
            {
                "error": "proxy_not_implemented",
                "route_path": route.path,
            },
            status_code=501,
        )

    return app
