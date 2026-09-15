from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from eventserver.core.models import DomainEvent, Observation


def parse_time(value: str | datetime | None, *, fallback: datetime | None = None) -> datetime:
    if value is None:
        if fallback is None:
            raise ValueError("timestamp is required")
        return fallback
    parsed = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(value.replace("Z", "+00:00"))
    )
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def require(raw: dict[str, Any], key: str, expected: type) -> Any:
    value = raw.get(key)
    if not isinstance(value, expected):
        raise ValueError(f"{key} must be {expected.__name__}")
    return value


def event_id(event_key: str, dedupe_key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"autoqq:{event_key}:{dedupe_key}"))


def build_event(
    *,
    event_key: str,
    provider_key: str,
    dedupe_key: str,
    occurred_at: datetime,
    subject: dict[str, Any],
    data: dict[str, Any],
) -> DomainEvent:
    return DomainEvent(
        event_id=event_id(event_key, dedupe_key),
        event_key=event_key,
        schema_version=1,
        dedupe_key=dedupe_key,
        occurred_at=occurred_at,
        subject=subject,
        data=data,
        metadata={"provider_key": provider_key},
    )


def observation(
    *,
    provider_key: str,
    identity: str,
    observed_at: datetime,
    effective_at: datetime,
    expires_at: datetime | None,
    state: dict[str, Any],
) -> Observation:
    return Observation(
        provider_key=provider_key,
        schema_version=1,
        identity=identity,
        observed_at=observed_at,
        effective_at=effective_at,
        expires_at=expires_at,
        state=state,
        source_metadata={"source": "warframe-worldstate-adapter"},
    )
