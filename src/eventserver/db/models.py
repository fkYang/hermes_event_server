from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from eventserver.core.models import utc_now
from eventserver.db.base import Base

BIGINT = BigInteger().with_variant(Integer, "sqlite")
USER_FK = ("users.platform", "users.openid")


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    platform: Mapped[str] = mapped_column(String(32), primary_key=True)
    openid: Mapped[str] = mapped_column(String(128), primary_key=True)
    role: Mapped[str] = mapped_column(
        Enum("user", "admin", name="user_role", native_enum=False), default="user", nullable=False
    )
    account_status: Mapped[str] = mapped_column(
        Enum("active", "blocked", name="account_status", native_enum=False),
        default="active",
        nullable=False,
        index=True,
    )
    display_name: Mapped[str | None] = mapped_column(String(128))


class UserPermission(TimestampMixin, Base):
    __tablename__ = "user_permissions"
    __table_args__ = (
        ForeignKeyConstraint(["platform", "openid"], USER_FK, ondelete="CASCADE"),
        CheckConstraint("permission_key IN ('chat', 'command')", name="ck_permission_key"),
    )

    platform: Mapped[str] = mapped_column(String(32), primary_key=True)
    openid: Mapped[str] = mapped_column(String(128), primary_key=True)
    permission_key: Mapped[str] = mapped_column(String(16), primary_key=True)
    granted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    granted_by: Mapped[str | None] = mapped_column(String(128))


class EventType(TimestampMixin, Base):
    __tablename__ = "event_types"

    event_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    payload_schema: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    subscribable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    match_key_field: Mapped[str | None] = mapped_column(String(64))
    match_key_options: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    match_keys_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class EventPublisher(TimestampMixin, Base):
    """A separately deployed publisher authorized to emit a bounded event namespace."""

    __tablename__ = "event_publishers"

    publisher_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    allowed_event_prefixes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)


class EventAlias(TimestampMixin, Base):
    __tablename__ = "event_aliases"

    alias_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    event_key: Mapped[str] = mapped_column(
        String(128), ForeignKey("event_types.event_key", ondelete="CASCADE"), nullable=False
    )


class ProviderInstance(TimestampMixin, Base):
    __tablename__ = "provider_instances"
    __table_args__ = (Index("ix_provider_due", "enabled", "next_run_at"),)

    provider_instance_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    capability: Mapped[str] = mapped_column(String(24), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    interval_seconds: Mapped[int | None] = mapped_column(Integer)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProviderCheckpoint(TimestampMixin, Base):
    __tablename__ = "provider_checkpoints"
    __table_args__ = (Index("ix_provider_lease", "lease_until"),)

    provider_instance_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("provider_instances.provider_instance_id", ondelete="CASCADE"),
        primary_key=True,
    )
    cursor: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    last_identity: Mapped[str | None] = mapped_column(String(255))
    state_hash: Mapped[str | None] = mapped_column(String(64))
    state: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ObservationRecord(TimestampMixin, Base):
    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint("provider_instance_id", "identity", name="uq_observation_identity"),
        Index("ix_observation_observed", "provider_instance_id", "observed_at"),
    )

    observation_id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    provider_instance_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("provider_instances.provider_instance_id", ondelete="CASCADE"),
        nullable=False,
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    identity: Mapped[str] = mapped_column(String(255), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class EventOccurrence(TimestampMixin, Base):
    __tablename__ = "event_occurrences"
    __table_args__ = (
        UniqueConstraint("event_key", "dedupe_key", name="uq_event_dedupe"),
        Index("ix_event_occurred", "event_key", "occurred_at"),
    )

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_key: Mapped[str] = mapped_column(
        String(128), ForeignKey("event_types.event_key", ondelete="RESTRICT"), nullable=False
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    subject: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        ForeignKeyConstraint(["platform", "openid"], USER_FK, ondelete="CASCADE"),
        Index("ix_subscription_event", "event_key"),
    )

    platform: Mapped[str] = mapped_column(String(32), primary_key=True)
    openid: Mapped[str] = mapped_column(String(128), primary_key=True)
    event_key: Mapped[str] = mapped_column(
        String(128), ForeignKey("event_types.event_key", ondelete="CASCADE"), primary_key=True
    )
    locale: Mapped[str] = mapped_column(String(16), default="zh-CN", nullable=False)
    match_keys: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)


class Delivery(TimestampMixin, Base):
    __tablename__ = "deliveries"
    __table_args__ = (
        UniqueConstraint("event_id", "platform", "openid", name="uq_delivery_target"),
        Index("ix_delivery_claim", "platform", "status", "next_attempt_at", "lease_until"),
    )

    delivery_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("event_occurrences.event_id", ondelete="CASCADE"), nullable=False
    )
    event_key: Mapped[str] = mapped_column(String(128), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    openid: Mapped[str] = mapped_column(String(128), nullable=False)
    message: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(
            "pending", "leased", "retry", "sent", "dead", name="delivery_status", native_enum=False
        ),
        default="pending",
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_token_hash: Mapped[str | None] = mapped_column(String(64))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    platform_message_id: Mapped[str | None] = mapped_column(String(128))
    last_error_code: Mapped[str | None] = mapped_column(String(64))


class PairingCode(TimestampMixin, Base):
    __tablename__ = "pairing_codes"
    __table_args__ = (Index("ix_pairing_expiry", "expires_at", "consumed_at"),)

    code_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    openid: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(128))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_created", "created_at"),)

    audit_id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    actor_platform: Mapped[str | None] = mapped_column(String(32))
    actor_openid_masked: Mapped[str | None] = mapped_column(String(128))
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id_masked: Mapped[str | None] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class WebhookReceipt(TimestampMixin, Base):
    __tablename__ = "webhook_receipts"
    __table_args__ = (
        UniqueConstraint("source_key", "external_id", name="uq_webhook_replay"),
        Index("ix_webhook_status", "status", "received_at"),
    )

    receipt_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_key: Mapped[str] = mapped_column(String(128), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="received", nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
