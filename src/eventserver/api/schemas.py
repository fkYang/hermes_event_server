from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from eventserver.core.models import DeliveryMessage


class ErrorResponse(BaseModel):
    code: str
    message: str
    request_id: str


class PermissionValues(BaseModel):
    chat: bool
    command: bool


class PermissionResponse(BaseModel):
    platform: str
    openid: str
    account_status: Literal["unknown", "active", "blocked"]
    role: Literal["user", "admin"]
    permissions: PermissionValues


class PermissionChangeRequest(BaseModel):
    permissions: set[Literal["chat", "command"]] = Field(min_length=1)
    operator_openid: str = Field(min_length=1, max_length=128)


class RoleChangeRequest(BaseModel):
    role: Literal["user", "admin"]
    operator_openid: str = Field(min_length=1, max_length=128)


class MatchKeyOption(BaseModel):
    key: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")
    label: str = Field(min_length=1, max_length=100)


class EventResponse(BaseModel):
    event_key: str
    display_name: str
    description: str
    schema_version: int
    deprecated: bool
    match_key_field: str | None = None
    match_keys_required: bool = False
    match_key_options: list[MatchKeyOption] = Field(default_factory=list)


class SubscriptionRequest(BaseModel):
    event_key: str = Field(min_length=3, max_length=128)
    match_keys: list[str] = Field(default_factory=list, max_length=32)


class SubscriptionResponse(BaseModel):
    event_key: str
    locale: str
    match_keys: list[str] = Field(default_factory=list)
    created: bool | None = None
    updated: bool = False


class DeleteSubscriptionResponse(BaseModel):
    event_key: str
    deleted: bool


class PairingCodeRequest(BaseModel):
    platform: str = "qqbot"
    openid: str = Field(min_length=1, max_length=128)


class PairingCodeResponse(BaseModel):
    code: str
    expires_at: datetime


class PairingApproveRequest(BaseModel):
    permissions: set[Literal["chat", "command"]] = Field(min_length=1)
    operator_openid: str = Field(min_length=1, max_length=128)
    platform: str = "qqbot"


class DeliveryClaimRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=128)
    platform: str = "qqbot"
    limit: int = Field(default=10, ge=1, le=100)
    lease_seconds: int | None = Field(default=None, ge=10, le=600)


class DeliveryTarget(BaseModel):
    platform: str
    openid: str


class ClaimedDeliveryResponse(BaseModel):
    delivery_id: str
    lease_token: str
    event_id: str
    event_key: str
    target: DeliveryTarget
    message: dict[str, Any]
    attempt: int
    created_at: datetime


class DeliveryClaimResponse(BaseModel):
    items: list[ClaimedDeliveryResponse]


class DeliveryAckRequest(BaseModel):
    lease_token: str = Field(min_length=16)
    sent_at: datetime | None = None
    platform_message_id: str | None = Field(default=None, max_length=128)


class DeliveryFailRequest(BaseModel):
    lease_token: str = Field(min_length=16)
    error_code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z0-9_]+$")
    retryable: bool


class DeliveryStatusResponse(BaseModel):
    delivery_id: str
    status: Literal["pending", "leased", "retry", "sent", "dead"]
    attempts: int
    next_attempt_at: datetime


class PublishEventRequest(BaseModel):
    event_key: str = Field(pattern=r"^[a-z0-9]+(?:\.[a-z0-9_]+){2,}$", max_length=128)
    schema_version: int = Field(ge=1)
    dedupe_key: str = Field(min_length=1, max_length=255)
    occurred_at: datetime
    notify_at: datetime | None = None
    subject: dict[str, Any]
    data: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)
    messages: dict[str, DeliveryMessage] = Field(min_length=1)

    @field_validator("notify_at")
    @classmethod
    def reject_naive_notify_at(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("notify_at must include a timezone offset")
        return value


class PublishEventResponse(BaseModel):
    event_id: str
    created: bool
    deliveries_created: int
    notify_at: datetime | None = None
