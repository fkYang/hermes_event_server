from __future__ import annotations

import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import __version__

USER_AGENT = f"AutoQQ-DemoReminder/{__version__}"


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class PublisherSettings:
    event_server_url: str
    publisher_token: str
    ingress_token: str | None = None
    http_host: str = "0.0.0.0"
    http_port: int = 8080
    default_delay_seconds: int = 300
    max_delay_seconds: int = 3600
    request_timeout_seconds: float = 10.0
    max_body_bytes: int = 16_384
    display_timezone: ZoneInfo = ZoneInfo("Asia/Shanghai")

    @classmethod
    def from_environment(cls) -> PublisherSettings:
        event_server_url = os.environ.get("EVENTSERVER_URL", "").rstrip("/")
        if not event_server_url.startswith(("http://", "https://")):
            raise ConfigurationError("EVENTSERVER_URL must be an http(s) URL")
        token = os.environ.get("PUBLISHER_TOKEN", "")
        if len(token) < 32:
            raise ConfigurationError("PUBLISHER_TOKEN must contain at least 32 characters")
        ingress_token = os.environ.get("INGRESS_TOKEN", "").strip() or None
        if ingress_token is not None and len(ingress_token) < 16:
            raise ConfigurationError("INGRESS_TOKEN must contain at least 16 characters")
        settings = cls(
            event_server_url=event_server_url,
            publisher_token=token,
            ingress_token=ingress_token,
            http_host=os.environ.get("HTTP_HOST", "0.0.0.0").strip() or "0.0.0.0",
            http_port=_integer("HTTP_PORT", 8080, minimum=1, maximum=65535),
            default_delay_seconds=_integer("DEFAULT_DELAY_SECONDS", 300, minimum=0, maximum=86_400),
            max_delay_seconds=_integer("MAX_DELAY_SECONDS", 3600, minimum=60, maximum=86_400),
            request_timeout_seconds=_number(
                "REQUEST_TIMEOUT_SECONDS", 10.0, minimum=1.0, maximum=60.0
            ),
            max_body_bytes=_integer("MAX_BODY_BYTES", 16_384, minimum=256, maximum=1_048_576),
            display_timezone=_timezone(os.environ.get("DISPLAY_TIMEZONE", "Asia/Shanghai")),
        )
        if settings.default_delay_seconds > settings.max_delay_seconds:
            raise ConfigurationError("DEFAULT_DELAY_SECONDS must not exceed MAX_DELAY_SECONDS")
        return settings


def _number(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} must be between {minimum} and {maximum}")
    return value


def _integer(name: str, default: int, *, minimum: int, maximum: int) -> int:
    value = _number(name, float(default), minimum=float(minimum), maximum=float(maximum))
    if value != int(value):
        raise ConfigurationError(f"{name} must be an integer")
    return int(value)


def _timezone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ConfigurationError(f"invalid DISPLAY_TIMEZONE: {value}") from exc
