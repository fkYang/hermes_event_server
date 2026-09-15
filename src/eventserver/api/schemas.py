from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


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


class EventResponse(BaseModel):
    event_key: str
    display_name: str
    description: str
    schema_version: int
    deprecated: bool


class SubscriptionRequest(BaseModel):
    event_key: str = Field(min_length=3, max_length=128)


class SubscriptionResponse(BaseModel):
    event_key: str
    locale: str
    created: bool | None = None


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
