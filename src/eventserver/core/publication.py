from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from eventserver.core.models import DomainEvent
from eventserver.core.registry import ProviderRegistry
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
    def __init__(self, session: Session, registry: ProviderRegistry) -> None:
        self.session = session
        self.registry = registry

    def publish(self, event: DomainEvent) -> PublicationResult:
        event_type = self.session.get(EventType, event.event_key)
        if event_type is None or not event_type.enabled:
            raise PublicationError(f"event type is not enabled: {event.event_key}")
        if event_type.schema_version != event.schema_version:
            raise PublicationError("event schema version does not match registry")

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

        provider = self.registry.provider_for_event(event.event_key)
        recipients = list(
            self.session.execute(
                select(Subscription.platform, Subscription.openid, Subscription.locale)
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
        for platform, openid, locale in recipients:
            message = provider.render(event, locale).model_dump(mode="json")
            self.session.add(
                Delivery(
                    delivery_id=str(uuid4()),
                    event_id=event.event_id,
                    event_key=event.event_key,
                    platform=platform,
                    openid=openid,
                    message=message,
                )
            )
        self.session.flush()
        return PublicationResult(event.event_id, True, len(recipients))
