from __future__ import annotations

from pathlib import Path

import pytest

from gatewaykit.config import ConfigError, load_config, parse_config, resolve_config_path


def minimal_config() -> dict:
    return {
        "gateway": {"port": 8080, "global_timeout": "30s"},
        "routes": [
            {
                "path": "/api/widgets",
                "methods": ["get", "POST"],
                "strip_prefix": True,
                "upstream": {"url": "http://localhost:3001"},
            }
        ],
    }


def test_parse_minimal_config_normalizes_methods() -> None:
    config = parse_config(minimal_config())

    assert config.gateway.port == 8080
    assert len(config.routes) == 1
    assert config.routes[0].path == "/api/widgets"
    assert config.routes[0].methods == ["GET", "POST"]
    assert config.routes[0].strip_prefix is True
    assert config.routes[0].upstream.url == "http://localhost:3001"


def test_parse_provided_gateway_yaml() -> None:
    config = load_config(Path(__file__).parents[1] / "gateway.yaml")

    assert config.gateway.port == 8080
    assert config.gateway.global_rate_limit is not None
    assert len(config.routes) == 5
    assert config.routes[2].upstream.targets is not None
    assert config.routes[2].upstream.balance == "weighted_round_robin"
    assert config.routes[4].auth is not None
    assert config.routes[4].circuit_breaker is not None


def test_rejects_missing_gateway_section() -> None:
    raw = minimal_config()
    del raw["gateway"]

    with pytest.raises(ConfigError, match="gateway"):
        parse_config(raw)


def test_rejects_invalid_route_path() -> None:
    raw = minimal_config()
    raw["routes"][0]["path"] = "api/widgets"

    with pytest.raises(ConfigError, match="path"):
        parse_config(raw)


def test_rejects_invalid_upstream_shape() -> None:
    raw = minimal_config()
    raw["routes"][0]["upstream"] = {
        "url": "http://localhost:3001",
        "targets": [{"url": "http://localhost:3002"}],
    }

    with pytest.raises(ConfigError, match="exactly one"):
        parse_config(raw)


def test_rejects_malformed_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "bad.yaml"
    config_path.write_text("gateway: [", encoding="utf-8")

    with pytest.raises(ConfigError, match="could not parse YAML"):
        load_config(config_path)


def test_resolve_config_path_prefers_cli_arg() -> None:
    path = resolve_config_path(["from-cli.yaml"], {"GATEWAY_CONFIG": "from-env.yaml"})

    assert path == Path("from-cli.yaml")


def test_resolve_config_path_uses_env_fallback() -> None:
    path = resolve_config_path([], {"GATEWAY_CONFIG": "from-env.yaml"})

    assert path == Path("from-env.yaml")


def test_resolve_config_path_requires_cli_or_env() -> None:
    with pytest.raises(ConfigError, match="config path required"):
        resolve_config_path([], {})
