"""FastAPI application factory for GatewayKit."""

from __future__ import annotations

import time

from fastapi import FastAPI

from gatewaykit.config import GatewayConfig


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

    return app
