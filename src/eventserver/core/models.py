from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class Observation(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_key: str = Field(min_length=3, max_length=128)
    schema_version: int = Field(ge=1)
    identity: str = Field(min_length=1, max_length=255)
    observed_at: datetime
    effective_at: datetime
    expires_at: datetime | None = None
    state: dict[str, Any]
    source_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("observed_at", "effective_at", "expires_at")
    @classmethod
    def require_aware_datetime(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value


class DomainEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str = Field(min_length=1, max_length=36)
    event_key: str = Field(pattern=r"^[a-z0-9]+(?:\.[a-z0-9_]+){2,}$", max_length=128)
    schema_version: int = Field(ge=1)
    dedupe_key: str = Field(min_length=1, max_length=255)
    occurred_at: datetime
    subject: dict[str, Any]
    data: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def require_aware_occurred_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")
        return value


class DeliveryMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=4000)
    data: dict[str, Any] = Field(default_factory=dict)
    template_key: str = Field(min_length=1, max_length=128)
    template_version: int = Field(ge=1)


class ProviderMetadata(BaseModel):
    provider_key: str
    event_keys: tuple[str, ...]
    capability: Literal["polling", "scheduled", "webhook", "publisher"]
    implementation_version: str
    publish_initial: bool = False


class ProviderHealth(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    checked_at: datetime = Field(default_factory=utc_now)
    detail: str | None = None
