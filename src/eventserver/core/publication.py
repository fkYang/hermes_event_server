from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from eventserver.core.match_keys import recipient_matches
from eventserver.core.models import DeliveryMessage, DomainEvent
from eventserver.core.schema_validation import PayloadSchemaError, validate_payload
from eventserver.db.models import (
    Delivery,
    EventOccurrence,
    EventType,
    Subscription,
    User,
    UserPermission,
)


class PublicationError(RuntimeError):
    pass


@dataclass(frozen=True)
class PublicationResult:
    event_id: str
    created: bool
    deliveries_created: int


class PublicationService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def publish(
        self,
        event: DomainEvent,
        messages: dict[str, DeliveryMessage],
        *,
        next_attempt_at: datetime | None = None,
    ) -> PublicationResult:
        event_type = self.session.get(EventType, event.event_key)
        if event_type is None or not event_type.enabled:
            raise PublicationError(f"event type is not enabled: {event.event_key}")
        if event_type.schema_version != event.schema_version:
            raise PublicationError("event schema version does not match registry")
        try:
            validate_payload(event_type.payload_schema, event.data)
        except PayloadSchemaError as exc:
            raise PublicationError(f"event payload schema validation failed: {exc}") from exc
        if "default" not in messages:
            raise PublicationError("a default delivery message is required")

        existing = self.session.scalar(
            select(EventOccurrence).where(
                EventOccurrence.event_key == event.event_key,
                EventOccurrence.dedupe_key == event.dedupe_key,
            )
        )
        if existing:
            return PublicationResult(existing.event_id, False, 0)

        occurrence = EventOccurrence(
            event_id=event.event_id,
            event_key=event.event_key,
            schema_version=event.schema_version,
            dedupe_key=event.dedupe_key,
            occurred_at=event.occurred_at,
            subject=event.subject,
            data=event.data,
            metadata_json=event.metadata,
        )
        try:
            with self.session.begin_nested():
                self.session.add(occurrence)
                self.session.flush()
        except IntegrityError:
            existing = self.session.scalar(
                select(EventOccurrence).where(
                    EventOccurrence.event_key == event.event_key,
                    EventOccurrence.dedupe_key == event.dedupe_key,
                )
            )
            if existing is None:
                raise
            return PublicationResult(existing.event_id, False, 0)

        recipients = list(
            self.session.execute(
                select(
                    Subscription.platform,
                    Subscription.openid,
                    Subscription.locale,
                    Subscription.match_keys,
                )
                .join(
                    User,
                    and_(
                        User.platform == Subscription.platform,
                        User.openid == Subscription.openid,
                    ),
                )
                .join(
                    UserPermission,
                    and_(
                        UserPermission.platform == Subscription.platform,
                        UserPermission.openid == Subscription.openid,
                        UserPermission.permission_key == "command",
                        UserPermission.granted.is_(True),
                    ),
                )
                .where(
                    Subscription.event_key == event.event_key,
                    User.account_status == "active",
                )
            )
        )
        created = 0
        for platform, openid, locale, subscribed_keys in recipients:
            if not recipient_matches(
                field=event_type.match_key_field,
                event_data=event.data,
                subscribed=subscribed_keys,
            ):
                continue
            message = messages.get(locale, messages["default"]).model_dump(mode="json")
            delivery = Delivery(
                delivery_id=str(uuid4()),
                event_id=event.event_id,
                event_key=event.event_key,
                platform=platform,
                openid=openid,
                message=message,
            )
            if next_attempt_at is not None:
                delivery.next_attempt_at = next_attempt_at
            self.session.add(delivery)
            created += 1
        self.session.flush()
        return PublicationResult(event.event_id, True, created)
