from sqlalchemy import select
from sqlalchemy.orm import Session

from eventserver.db.models import EventAlias, EventType, Subscription
from eventserver.services.users import AuthorizationError, permission_snapshot


class EventNotFoundError(LookupError):
    pass


def resolve_event_key(session: Session, event_key: str) -> str:
    event = session.get(EventType, event_key)
    if event is None:
        alias = session.get(EventAlias, event_key)
        event = session.get(EventType, alias.event_key) if alias else None
    if event is None or not event.enabled or not event.subscribable:
        raise EventNotFoundError(event_key)
    return event.event_key


def list_subscriptions(session: Session, platform: str, openid: str) -> list[Subscription]:
    return list(
        session.scalars(
            select(Subscription)
            .where(Subscription.platform == platform, Subscription.openid == openid)
            .order_by(Subscription.event_key)
        )
    )


def subscribe(
    session: Session, platform: str, openid: str, event_key: str
) -> tuple[Subscription, bool]:
    snapshot = permission_snapshot(session, platform, openid)
    if snapshot.account_status != "active" or not snapshot.command:
        raise AuthorizationError("active command permission is required")
    canonical = resolve_event_key(session, event_key)
    existing = session.get(Subscription, (platform, openid, canonical))
    if existing:
        return existing, False
    item = Subscription(platform=platform, openid=openid, event_key=canonical)
    session.add(item)
    session.flush()
    return item, True


def unsubscribe(session: Session, platform: str, openid: str, event_key: str) -> bool:
    snapshot = permission_snapshot(session, platform, openid)
    if snapshot.account_status != "active" or not snapshot.command:
        raise AuthorizationError("active command permission is required")
    try:
        canonical = resolve_event_key(session, event_key)
    except EventNotFoundError:
        canonical = event_key
    existing = session.get(Subscription, (platform, openid, canonical))
    if existing is None:
        return False
    session.delete(existing)
    session.flush()
    return True
