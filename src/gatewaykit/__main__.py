"""Command-line entrypoint for GatewayKit."""

from __future__ import annotations

import sys

import uvicorn

from gatewaykit.app import create_app
from gatewaykit.config import ConfigError, load_config, resolve_config_path


def main(argv: list[str] | None = None) -> int:
    try:
        config_path = resolve_config_path(argv)
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"gatewaykit: {exc}", file=sys.stderr)
        return 2

    uvicorn.run(
        create_app(config),
        host="0.0.0.0",
        port=config.gateway.port,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
