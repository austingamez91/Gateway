from __future__ import annotations

import httpx
import pytest

from gatewaykit.config import RouteConfig, parse_config
from gatewaykit.upstreams import (
    ActiveHealthChecker,
    InMemoryUpstreamHealth,
    InMemoryUpstreamSelector,
    target_sequence,
)


def single_url_route() -> RouteConfig:
    return parse_config(
        {
            "gateway": {"port": 8080},
            "routes": [
                {
                    "path": "/api/users",
                    "methods": ["GET"],
                    "upstream": {"url": "http://single.test"},
                }
            ],
        }
    ).routes[0]


def targets_route(
    balance: str | None = None,
    health_check: dict | None = None,
) -> RouteConfig:
    upstream: dict = {
        "targets": [
            {"url": "http://a.test", "weight": 2},
            {"url": "http://b.test", "weight": 1},
        ]
    }
    if balance is not None:
        upstream["balance"] = balance

    route: dict = {
        "path": "/api/products",
        "methods": ["GET"],
        "upstream": upstream,
    }
    if health_check is not None:
        route["health_check"] = health_check

    return parse_config({"gateway": {"port": 8080}, "routes": [route]}).routes[0]


def health_check_config(unhealthy_threshold: int = 2) -> dict:
    return {
        "path": "/healthz",
        "interval": "30s",
        "unhealthy_threshold": unhealthy_threshold,
    }


@pytest.mark.asyncio
async def test_selector_returns_single_upstream_url() -> None:
    selector = InMemoryUpstreamSelector()

    assert await selector.select(single_url_route()) == "http://single.test"


@pytest.mark.asyncio
async def test_selector_round_robins_targets_by_default() -> None:
    selector = InMemoryUpstreamSelector()
    route = targets_route()

    assert [await selector.select(route) for _ in range(4)] == [
        "http://a.test",
        "http://b.test",
        "http://a.test",
        "http://b.test",
    ]


@pytest.mark.asyncio
async def test_selector_supports_weighted_round_robin() -> None:
    selector = InMemoryUpstreamSelector()
    route = targets_route("weighted_round_robin")

    assert [await selector.select(route) for _ in range(5)] == [
        "http://a.test",
        "http://a.test",
        "http://b.test",
        "http://a.test",
        "http://a.test",
    ]


def test_weighted_target_sequence_expands_by_weight() -> None:
    assert target_sequence(targets_route("weighted_round_robin")) == [
        "http://a.test",
        "http://a.test",
        "http://b.test",
    ]


@pytest.mark.asyncio
async def test_selector_skips_unhealthy_targets_when_alternatives_remain() -> None:
    health = InMemoryUpstreamHealth()
    selector = InMemoryUpstreamSelector(health)
    route = targets_route(health_check=health_check_config())

    await health.record(route, "http://b.test", healthy=False)
    await health.record(route, "http://b.test", healthy=False)

    assert [await selector.select(route) for _ in range(3)] == [
        "http://a.test",
        "http://a.test",
        "http://a.test",
    ]


@pytest.mark.asyncio
async def test_selector_falls_back_to_all_targets_when_none_are_healthy() -> None:
    health = InMemoryUpstreamHealth()
    selector = InMemoryUpstreamSelector(health)
    route = targets_route(health_check=health_check_config())

    for target_url in ["http://a.test", "http://b.test"]:
        await health.record(route, target_url, healthy=False)
        await health.record(route, target_url, healthy=False)

    assert [await selector.select(route) for _ in range(2)] == [
        "http://a.test",
        "http://b.test",
    ]


@pytest.mark.asyncio
async def test_active_health_checker_marks_targets_unhealthy_after_threshold() -> None:
    config = parse_config(
        {
            "gateway": {"port": 8080},
            "routes": [
                {
                    "path": "/api/products",
                    "methods": ["GET"],
                    "upstream": {
                        "targets": [
                            {"url": "http://a.test"},
                            {"url": "http://b.test"},
                        ]
                    },
                    "health_check": health_check_config(),
                }
            ],
        }
    )
    health = InMemoryUpstreamHealth()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "b.test":
            return httpx.Response(500)
        return httpx.Response(204)

    checker = ActiveHealthChecker(config, health, httpx.MockTransport(handler))

    await checker.check_once()
    await checker.check_once()

    selector = InMemoryUpstreamSelector(health)
    assert [await selector.select(config.routes[0]) for _ in range(3)] == [
        "http://a.test",
        "http://a.test",
        "http://a.test",
    ]


@pytest.mark.asyncio
async def test_active_health_checker_recovers_target_after_success() -> None:
    health = InMemoryUpstreamHealth()
    route = targets_route(health_check=health_check_config())

    await health.record(route, "http://b.test", healthy=False)
    await health.record(route, "http://b.test", healthy=False)
    await health.record(route, "http://b.test", healthy=True)

    assert await health.is_healthy(route, "http://b.test")
