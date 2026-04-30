"""Request policy enforcement for GatewayKit."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from math import ceil, floor

from fastapi import Request

from gatewaykit.config import GatewayConfig, RateLimitConfig, RouteConfig, parse_duration_seconds


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int = 0


@dataclass(frozen=True)
class AuthResult:
    allowed: bool


@dataclass(frozen=True)
class CircuitBreakerResult:
    allowed: bool
    retry_after_seconds: int = 0


def check_api_key(request: Request, route: RouteConfig) -> AuthResult:
    if route.auth is None:
        return AuthResult(allowed=True)

    candidate = request.headers.get(route.auth.header)
    return AuthResult(allowed=candidate in route.auth.keys)


class InMemoryRateLimiter:
    """Concurrency-safe in-memory rate limiter.

    This is intentionally process-local. It is sufficient for the prototype and keeps the
    policy surface small enough to replace with a shared store later.
    """

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or time.monotonic
        self._lock = asyncio.Lock()
        self._fixed_windows: dict[tuple[str, ...], tuple[float, int]] = {}
        self._sliding_windows: dict[tuple[str, ...], deque[float]] = {}

    async def check(
        self,
        request: Request,
        route: RouteConfig,
        config: GatewayConfig,
    ) -> RateLimitResult:
        rate_limit = route.rate_limit or config.gateway.global_rate_limit
        if rate_limit is None:
            return RateLimitResult(allowed=True)

        identity = bucket_identity(request, rate_limit)
        bucket_key = (route.path, rate_limit.strategy, rate_limit.per, identity)

        async with self._lock:
            if rate_limit.strategy == "fixed_window":
                return self._check_fixed_window(bucket_key, rate_limit)
            return self._check_sliding_window(bucket_key, rate_limit)

    def _check_fixed_window(
        self,
        bucket_key: tuple[str, ...],
        rate_limit: RateLimitConfig,
    ) -> RateLimitResult:
        now = self._clock()
        window_seconds = parse_duration_seconds(rate_limit.window)
        window_start = floor(now / window_seconds) * window_seconds
        stored_window_start, count = self._fixed_windows.get(bucket_key, (window_start, 0))

        if stored_window_start != window_start:
            stored_window_start = window_start
            count = 0

        if count >= rate_limit.requests:
            retry_after = window_seconds - (now - stored_window_start)
            return RateLimitResult(False, ceil(retry_after))

        self._fixed_windows[bucket_key] = (stored_window_start, count + 1)
        return RateLimitResult(True)

    def _check_sliding_window(
        self,
        bucket_key: tuple[str, ...],
        rate_limit: RateLimitConfig,
    ) -> RateLimitResult:
        now = self._clock()
        window_seconds = parse_duration_seconds(rate_limit.window)
        timestamps = self._sliding_windows.setdefault(bucket_key, deque())

        while timestamps and timestamps[0] <= now - window_seconds:
            timestamps.popleft()

        if len(timestamps) >= rate_limit.requests:
            retry_after = window_seconds - (now - timestamps[0])
            return RateLimitResult(False, ceil(retry_after))

        timestamps.append(now)
        return RateLimitResult(True)


def bucket_identity(request: Request, rate_limit: RateLimitConfig) -> str:
    if rate_limit.per == "global":
        return "global"
    if request.client is None:
        return "unknown"
    return request.client.host


class InMemoryCircuitBreaker:
    """Route-scoped in-memory circuit breaker."""

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or time.monotonic
        self._lock = asyncio.Lock()
        self._states: dict[str, CircuitBreakerState] = {}

    async def before_request(self, route: RouteConfig) -> CircuitBreakerResult:
        if route.circuit_breaker is None:
            return CircuitBreakerResult(allowed=True)

        async with self._lock:
            state = self._states.get(route.path)
            if state is None or state.opened_at is None:
                return CircuitBreakerResult(allowed=True)

            cooldown = parse_duration_seconds(route.circuit_breaker.cooldown)
            elapsed = self._clock() - state.opened_at
            if elapsed >= cooldown:
                self._states[route.path] = CircuitBreakerState()
                return CircuitBreakerResult(allowed=True)

            return CircuitBreakerResult(False, ceil(cooldown - elapsed))

    async def after_request(self, route: RouteConfig, failed: bool) -> None:
        if route.circuit_breaker is None:
            return

        async with self._lock:
            state = self._states.setdefault(route.path, CircuitBreakerState())
            now = self._clock()
            window = parse_duration_seconds(route.circuit_breaker.window)

            if not failed:
                self._states[route.path] = CircuitBreakerState()
                return

            state.failure_timestamps = [
                timestamp for timestamp in state.failure_timestamps if timestamp > now - window
            ]
            state.failure_timestamps.append(now)

            if len(state.failure_timestamps) >= route.circuit_breaker.threshold:
                state.opened_at = now


@dataclass
class CircuitBreakerState:
    failure_timestamps: list[float] | None = None
    opened_at: float | None = None

    def __post_init__(self) -> None:
        if self.failure_timestamps is None:
            self.failure_timestamps = []
