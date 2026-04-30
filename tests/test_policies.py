from __future__ import annotations

from typing import Any

import pytest
from fastapi import Request

from gatewaykit.config import GatewayConfig, parse_config
from gatewaykit.policies import InMemoryRateLimiter, check_api_key


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def config_with_rate_limit(rate_limit: dict[str, Any]) -> GatewayConfig:
    return parse_config(
        {
            "gateway": {"port": 8080, "global_rate_limit": rate_limit},
            "routes": [
                {
                    "path": "/api/users",
                    "methods": ["GET"],
                    "upstream": {"url": "http://upstream.test"},
                }
            ],
        }
    )


def fake_request(client_host: str = "1.2.3.4") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/users",
        "headers": [],
        "client": (client_host, 12345),
    }
    return Request(scope)


def fake_request_with_headers(headers: list[tuple[bytes, bytes]]) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/users",
        "headers": headers,
        "client": ("1.2.3.4", 12345),
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_fixed_window_rate_limit_blocks_until_next_window() -> None:
    clock = FakeClock()
    config = config_with_rate_limit(
        {
            "requests": 2,
            "window": "10s",
            "strategy": "fixed_window",
            "per": "global",
        }
    )
    route = config.routes[0]
    limiter = InMemoryRateLimiter(clock=clock)

    assert (await limiter.check(fake_request(), route, config)).allowed is True
    assert (await limiter.check(fake_request(), route, config)).allowed is True

    blocked = await limiter.check(fake_request(), route, config)
    assert blocked.allowed is False
    assert blocked.retry_after_seconds == 10

    clock.advance(10)
    assert (await limiter.check(fake_request(), route, config)).allowed is True


@pytest.mark.asyncio
async def test_sliding_window_rate_limit_reopens_after_oldest_request_expires() -> None:
    clock = FakeClock()
    config = config_with_rate_limit(
        {
            "requests": 2,
            "window": "10s",
            "strategy": "sliding_window",
            "per": "global",
        }
    )
    route = config.routes[0]
    limiter = InMemoryRateLimiter(clock=clock)

    assert (await limiter.check(fake_request(), route, config)).allowed is True
    clock.advance(1)
    assert (await limiter.check(fake_request(), route, config)).allowed is True

    blocked = await limiter.check(fake_request(), route, config)
    assert blocked.allowed is False
    assert blocked.retry_after_seconds == 9

    clock.advance(9)
    assert (await limiter.check(fake_request(), route, config)).allowed is True


@pytest.mark.asyncio
async def test_ip_rate_limit_buckets_by_client_host() -> None:
    config = config_with_rate_limit(
        {
            "requests": 1,
            "window": "60s",
            "strategy": "fixed_window",
            "per": "ip",
        }
    )
    route = config.routes[0]
    limiter = InMemoryRateLimiter(clock=FakeClock())

    assert (await limiter.check(fake_request("1.2.3.4"), route, config)).allowed is True
    assert (await limiter.check(fake_request("1.2.3.4"), route, config)).allowed is False
    assert (await limiter.check(fake_request("5.6.7.8"), route, config)).allowed is True


def test_api_key_auth_allows_routes_without_auth_config() -> None:
    config = config_with_rate_limit(
        {
            "requests": 1,
            "window": "60s",
            "strategy": "fixed_window",
            "per": "global",
        }
    )

    assert check_api_key(fake_request(), config.routes[0]).allowed is True


def test_api_key_auth_rejects_missing_or_invalid_keys() -> None:
    config = parse_config(
        {
            "gateway": {"port": 8080},
            "routes": [
                {
                    "path": "/api/internal",
                    "methods": ["GET"],
                    "upstream": {"url": "http://upstream.test"},
                    "auth": {
                        "type": "api_key",
                        "header": "X-API-Key",
                        "keys": ["sk_live_abc123"],
                    },
                }
            ],
        }
    )
    route = config.routes[0]

    assert check_api_key(fake_request_with_headers([]), route).allowed is False
    assert (
        check_api_key(
            fake_request_with_headers([(b"x-api-key", b"wrong")]),
            route,
        ).allowed
        is False
    )


def test_api_key_auth_accepts_configured_key() -> None:
    config = parse_config(
        {
            "gateway": {"port": 8080},
            "routes": [
                {
                    "path": "/api/internal",
                    "methods": ["GET"],
                    "upstream": {"url": "http://upstream.test"},
                    "auth": {
                        "type": "api_key",
                        "header": "X-API-Key",
                        "keys": ["sk_live_abc123"],
                    },
                }
            ],
        }
    )

    assert (
        check_api_key(
            fake_request_with_headers([(b"x-api-key", b"sk_live_abc123")]),
            config.routes[0],
        ).allowed
        is True
    )
