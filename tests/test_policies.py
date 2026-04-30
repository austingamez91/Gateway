from __future__ import annotations

from typing import Any

import pytest
from fastapi import Request

from gatewaykit.config import GatewayConfig, parse_config
from gatewaykit.policies import InMemoryRateLimiter


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
