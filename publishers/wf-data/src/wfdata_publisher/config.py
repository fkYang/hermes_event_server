from __future__ import annotations

import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class PublisherSettings:
    wf_data_url: str
    event_server_url: str
    publisher_token: str
    poll_seconds: float = 60.0
    lead_seconds: int = 300
    request_timeout_seconds: float = 10.0
    max_response_bytes: int = 262_144
    display_timezone: ZoneInfo = ZoneInfo("Asia/Shanghai")

    @classmethod
    def from_environment(cls) -> PublisherSettings:
        wf_data_url = os.environ.get("WF_DATA_URL", "").rstrip("/")
        event_server_url = os.environ.get("EVENTSERVER_URL", "").rstrip("/")
        token = os.environ.get("PUBLISHER_TOKEN", "")
        if not wf_data_url.startswith(("http://", "https://")):
            raise ConfigurationError("WF_DATA_URL must be an http(s) URL")
        if not event_server_url.startswith(("http://", "https://")):
            raise ConfigurationError("EVENTSERVER_URL must be an http(s) URL")
        if len(token) < 32:
            raise ConfigurationError("PUBLISHER_TOKEN must contain at least 32 characters")
        return cls(
            wf_data_url=wf_data_url,
            event_server_url=event_server_url,
            publisher_token=token,
            poll_seconds=_number("POLL_SECONDS", 60.0, minimum=1.0, maximum=3600.0),
            lead_seconds=_integer("LEAD_SECONDS", 300, minimum=0, maximum=3600),
            request_timeout_seconds=_number(
                "REQUEST_TIMEOUT_SECONDS", 10.0, minimum=1.0, maximum=60.0
            ),
            max_response_bytes=_integer(
                "MAX_RESPONSE_BYTES", 262_144, minimum=1024, maximum=16_777_216
            ),
            display_timezone=_timezone(os.environ.get("DISPLAY_TIMEZONE", "Asia/Shanghai")),
        )


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
