"""Command-line entrypoint for GatewayKit."""

from __future__ import annotations

import sys

from gatewaykit.config import ConfigError, load_config, resolve_config_path


def main(argv: list[str] | None = None) -> int:
    try:
        config_path = resolve_config_path(argv)
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"gatewaykit: {exc}", file=sys.stderr)
        return 2

    print(
        f"Loaded GatewayKit config from {config_path}: "
        f"port={config.gateway.port}, routes={len(config.routes)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
