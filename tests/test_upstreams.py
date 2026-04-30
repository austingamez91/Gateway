from __future__ import annotations

import pytest

from gatewaykit.config import RouteConfig, parse_config
from gatewaykit.upstreams import InMemoryUpstreamSelector, target_sequence


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


def targets_route(balance: str | None = None) -> RouteConfig:
    upstream: dict = {
        "targets": [
            {"url": "http://a.test", "weight": 2},
            {"url": "http://b.test", "weight": 1},
        ]
    }
    if balance is not None:
        upstream["balance"] = balance

    return parse_config(
        {
            "gateway": {"port": 8080},
            "routes": [
                {
                    "path": "/api/products",
                    "methods": ["GET"],
                    "upstream": upstream,
                }
            ],
        }
    ).routes[0]


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
