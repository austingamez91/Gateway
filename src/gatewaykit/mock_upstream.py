"""Manual mock upstream server for local GatewayKit demos."""

from __future__ import annotations

import argparse
import asyncio

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def create_mock_upstream_app(name: str) -> FastAPI:
    app = FastAPI(title=f"GatewayKit Mock Upstream {name}")
    state = {"flaky_calls": 0}

    @app.get("/flaky")
    async def flaky() -> JSONResponse:
        state["flaky_calls"] += 1
        if state["flaky_calls"] % 2 == 1:
            return JSONResponse({"upstream": name, "error": "temporary_failure"}, status_code=503)
        return JSONResponse({"upstream": name, "status": "recovered"})

    @app.get("/slow")
    async def slow(delay: float = 2.0) -> JSONResponse:
        await asyncio.sleep(delay)
        return JSONResponse({"upstream": name, "status": "slow_ok", "delay": delay})

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "upstream": name}

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"])
    async def echo(path: str, request: Request) -> JSONResponse:
        body = await request.body()
        return JSONResponse(
            {
                "upstream": name,
                "method": request.method,
                "path": f"/{path}",
                "query": request.url.query,
                "headers": public_headers(request),
                "body": body.decode(errors="replace"),
            }
        )

    return app


def public_headers(request: Request) -> dict[str, str]:
    return {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in {"authorization", "x-api-key"}
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gatewaykit.mock_upstream")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--name", default="mock")
    args = parser.parse_args(argv)

    uvicorn.run(create_mock_upstream_app(args.name), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
