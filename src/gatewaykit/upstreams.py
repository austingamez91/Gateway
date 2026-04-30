"""Upstream target selection for GatewayKit."""

from __future__ import annotations

import asyncio
from urllib.parse import urlsplit, urlunsplit

import httpx

from gatewaykit.config import GatewayConfig, RouteConfig, parse_duration_seconds


class InMemoryUpstreamSelector:
    """Process-local round-robin upstream selector."""

    def __init__(self, health: InMemoryUpstreamHealth | None = None) -> None:
        self._lock = asyncio.Lock()
        self._cursors: dict[str, int] = {}
        self.health = health or InMemoryUpstreamHealth()

    async def select(self, route: RouteConfig) -> str:
        if route.upstream.url is not None:
            return route.upstream.url

        targets = await self._healthy_target_sequence(route)
        key = route.path

        async with self._lock:
            cursor = self._cursors.get(key, 0)
            selected = targets[cursor % len(targets)]
            self._cursors[key] = cursor + 1
            return selected

    async def _healthy_target_sequence(self, route: RouteConfig) -> list[str]:
        targets = target_sequence(route)
        healthy_targets = [
            target
            for target in targets
            if await self.health.is_healthy(route, target)
        ]
        return healthy_targets or targets


def target_sequence(route: RouteConfig) -> list[str]:
    targets = route.upstream.targets or []
    if route.upstream.balance == "weighted_round_robin":
        return [target.url for target in targets for _ in range(target.weight)]
    return [target.url for target in targets]


class InMemoryUpstreamHealth:
    """Process-local health state for upstream targets."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._failures: dict[tuple[str, str], int] = {}
        self._unhealthy: set[tuple[str, str]] = set()

    async def is_healthy(self, route: RouteConfig, target_url: str) -> bool:
        if route.health_check is None:
            return True

        async with self._lock:
            return health_key(route, target_url) not in self._unhealthy

    async def record(self, route: RouteConfig, target_url: str, healthy: bool) -> None:
        if route.health_check is None:
            return

        key = health_key(route, target_url)
        async with self._lock:
            if healthy:
                self._failures.pop(key, None)
                self._unhealthy.discard(key)
                return

            failures = self._failures.get(key, 0) + 1
            self._failures[key] = failures
            if failures >= route.health_check.unhealthy_threshold:
                self._unhealthy.add(key)


class ActiveHealthChecker:
    """Background active health checker for configured upstream targets."""

    def __init__(
        self,
        config: GatewayConfig,
        health: InMemoryUpstreamHealth,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        self._health = health
        self._transport = transport
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        while not self._stopped.is_set():
            await self.check_once()
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self._next_interval())
            except TimeoutError:
                pass

    def stop(self) -> None:
        self._stopped.set()

    async def check_once(self) -> None:
        async with httpx.AsyncClient(transport=self._transport) as client:
            for route in health_checked_routes(self._config):
                for target in route.upstream.targets or []:
                    await self._check_target(client, route, target.url)

    async def _check_target(
        self,
        client: httpx.AsyncClient,
        route: RouteConfig,
        target_url: str,
    ) -> None:
        assert route.health_check is not None
        try:
            response = await client.get(
                health_check_url(target_url, route.health_check.path),
                timeout=parse_duration_seconds(route.health_check.interval),
            )
            healthy = 200 <= response.status_code < 400
        except httpx.RequestError:
            healthy = False

        await self._health.record(route, target_url, healthy)

    def _next_interval(self) -> float:
        intervals = [
            parse_duration_seconds(route.health_check.interval)
            for route in health_checked_routes(self._config)
            if route.health_check is not None
        ]
        return min(intervals, default=60.0)


def health_checked_routes(config: GatewayConfig) -> list[RouteConfig]:
    return [
        route
        for route in config.routes
        if route.health_check is not None and route.upstream.targets
    ]


def health_check_url(base_url: str, health_path: str) -> str:
    parts = urlsplit(base_url)
    return urlunsplit((parts.scheme, parts.netloc, health_path, "", ""))


def health_key(route: RouteConfig, target_url: str) -> tuple[str, str]:
    return (route.path, target_url)
