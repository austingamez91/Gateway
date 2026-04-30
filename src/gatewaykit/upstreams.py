"""Upstream target selection for GatewayKit."""

from __future__ import annotations

import asyncio

from gatewaykit.config import RouteConfig


class InMemoryUpstreamSelector:
    """Process-local round-robin upstream selector."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._cursors: dict[str, int] = {}

    async def select(self, route: RouteConfig) -> str:
        if route.upstream.url is not None:
            return route.upstream.url

        targets = target_sequence(route)
        key = route.path

        async with self._lock:
            cursor = self._cursors.get(key, 0)
            selected = targets[cursor % len(targets)]
            self._cursors[key] = cursor + 1
            return selected


def target_sequence(route: RouteConfig) -> list[str]:
    targets = route.upstream.targets or []
    if route.upstream.balance == "weighted_round_robin":
        return [target.url for target in targets for _ in range(target.weight)]
    return [target.url for target in targets]
