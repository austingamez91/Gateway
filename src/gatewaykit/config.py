"""Configuration loading and validation for GatewayKit."""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class ConfigError(ValueError):
    """Raised when gateway configuration cannot be loaded or validated."""


class StrictModel(BaseModel):
    """Base model that rejects unknown config fields."""

    model_config = ConfigDict(extra="forbid")


class RateLimitConfig(StrictModel):
    requests: int = Field(gt=0)
    window: str = Field(min_length=1)
    strategy: Literal["fixed_window", "sliding_window"]
    per: Literal["ip", "global"]


class RetryConfig(StrictModel):
    attempts: int = Field(ge=0)
    backoff: Literal["fixed", "exponential"]
    initial_delay: str = Field(min_length=1)
    on: list[int] = Field(default_factory=list)

    @field_validator("on")
    @classmethod
    def validate_retry_statuses(cls, statuses: list[int]) -> list[int]:
        invalid = [status for status in statuses if status < 100 or status > 599]
        if invalid:
            raise ValueError(f"retry status codes must be HTTP status codes: {invalid}")
        return statuses


class UpstreamTargetConfig(StrictModel):
    url: str
    weight: int = Field(default=1, gt=0)

    @field_validator("url")
    @classmethod
    def validate_url(cls, url: str) -> str:
        return validate_http_url(url)


class UpstreamConfig(StrictModel):
    url: str | None = None
    targets: list[UpstreamTargetConfig] | None = None
    balance: Literal["round_robin", "weighted_round_robin"] | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, url: str | None) -> str | None:
        if url is None:
            return None
        return validate_http_url(url)

    @model_validator(mode="after")
    def validate_upstream_shape(self) -> UpstreamConfig:
        has_url = self.url is not None
        has_targets = bool(self.targets)
        if has_url == has_targets:
            raise ValueError("upstream must define exactly one of 'url' or non-empty 'targets'")
        if self.balance is not None and not has_targets:
            raise ValueError("upstream.balance is only valid with upstream.targets")
        return self


class HealthCheckConfig(StrictModel):
    path: str
    interval: str = Field(min_length=1)
    unhealthy_threshold: int = Field(gt=0)

    @field_validator("path")
    @classmethod
    def validate_path(cls, path: str) -> str:
        return validate_path_prefix(path)


class HeaderTransformConfig(StrictModel):
    add: dict[str, str] = Field(default_factory=dict)
    remove: list[str] = Field(default_factory=list)


class RequestBodyTransformConfig(StrictModel):
    mapping: dict[str, str] = Field(default_factory=dict)


class ResponseBodyTransformConfig(StrictModel):
    envelope: dict[str, Any] = Field(default_factory=dict)


class RequestTransformConfig(StrictModel):
    headers: HeaderTransformConfig | None = None
    body: RequestBodyTransformConfig | None = None


class ResponseTransformConfig(StrictModel):
    headers: HeaderTransformConfig | None = None
    body: ResponseBodyTransformConfig | None = None


class AuthConfig(StrictModel):
    type: Literal["api_key"]
    header: str = Field(min_length=1)
    keys: list[str] = Field(min_length=1)


class CircuitBreakerConfig(StrictModel):
    threshold: int = Field(gt=0)
    window: str = Field(min_length=1)
    cooldown: str = Field(min_length=1)


class RouteConfig(StrictModel):
    path: str
    methods: list[str] = Field(min_length=1)
    strip_prefix: bool = False
    upstream: UpstreamConfig
    timeout: str | None = None
    retry: RetryConfig | None = None
    rate_limit: RateLimitConfig | None = None
    health_check: HealthCheckConfig | None = None
    request_transform: RequestTransformConfig | None = None
    response_transform: ResponseTransformConfig | None = None
    auth: AuthConfig | None = None
    circuit_breaker: CircuitBreakerConfig | None = None

    @field_validator("path")
    @classmethod
    def validate_path(cls, path: str) -> str:
        return validate_path_prefix(path)

    @field_validator("methods")
    @classmethod
    def normalize_methods(cls, methods: list[str]) -> list[str]:
        normalized: list[str] = []
        for method in methods:
            stripped = method.strip().upper()
            if not stripped:
                raise ValueError("route methods must not be empty")
            if stripped in normalized:
                raise ValueError(f"duplicate method configured: {stripped}")
            normalized.append(stripped)
        return normalized


class GatewayServerConfig(StrictModel):
    port: int = Field(gt=0, le=65535)
    global_timeout: str = Field(default="30s", min_length=1)
    global_rate_limit: RateLimitConfig | None = None


class GatewayConfig(StrictModel):
    gateway: GatewayServerConfig
    routes: list[RouteConfig] = Field(default_factory=list)


def validate_http_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"must be an absolute HTTP(S) URL: {url}")
    return url


def validate_path_prefix(path: str) -> str:
    if not path.startswith("/"):
        raise ValueError("path must start with '/'")
    return path


def parse_config(raw_config: Mapping[str, Any]) -> GatewayConfig:
    try:
        return GatewayConfig.model_validate(raw_config)
    except ValidationError as exc:
        raise ConfigError(f"invalid gateway config:\n{exc}") from exc


def load_config(path: str | Path) -> GatewayConfig:
    config_path = Path(path).expanduser()
    try:
        raw_text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"could not read config file '{config_path}': {exc}") from exc

    try:
        raw_config = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"could not parse YAML config '{config_path}': {exc}") from exc

    if not isinstance(raw_config, Mapping):
        raise ConfigError(f"config file '{config_path}' must contain a YAML mapping")

    return parse_config(normalize_yaml_mapping_keys(raw_config))


def normalize_yaml_mapping_keys(value: Any) -> Any:
    """Normalize YAML 1.1 boolean-like mapping keys used by the config schema.

    PyYAML follows YAML 1.1 and treats an unquoted key named `on` as boolean True.
    The provided schema uses `retry.on`, so normalize mapping keys recursively after
    parsing while leaving scalar values alone.
    """

    if isinstance(value, Mapping):
        normalized: dict[Any, Any] = {}
        for key, child_value in value.items():
            if key is True:
                key = "on"
            elif key is False:
                key = "off"
            normalized[key] = normalize_yaml_mapping_keys(child_value)
        return normalized

    if isinstance(value, list):
        return [normalize_yaml_mapping_keys(item) for item in value]

    return value


def resolve_config_path(
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    parser = argparse.ArgumentParser(prog="gatewaykit")
    parser.add_argument(
        "config",
        nargs="?",
        help="Path to gateway YAML config. Defaults to GATEWAY_CONFIG.",
    )
    args = parser.parse_args(argv)
    env = os.environ if environ is None else environ
    config_path = args.config or env.get("GATEWAY_CONFIG")

    if not config_path:
        raise ConfigError("config path required as CLI argument or GATEWAY_CONFIG")

    return Path(config_path)
