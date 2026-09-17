from sqlalchemy import select
from sqlalchemy.orm import Session

from eventserver.core.match_keys import (
    MatchKeyError,
    allowed_match_keys,
    ensure_match_keys_allowed,
    normalize_match_keys,
)
from eventserver.db.models import EventAlias, EventType, Subscription
from eventserver.services.users import AuthorizationError, permission_snapshot


class EventNotFoundError(LookupError):
    pass


class InvalidMatchKeyError(ValueError):
    pass


def resolve_event(session: Session, event_key: str) -> EventType:
    event = session.get(EventType, event_key)
    if event is None:
        alias = session.get(EventAlias, event_key)
        event = session.get(EventType, alias.event_key) if alias else None
    if event is None or not event.enabled or not event.subscribable:
        raise EventNotFoundError(event_key)
    return event


def resolve_event_key(session: Session, event_key: str) -> str:
    return resolve_event(session, event_key).event_key


def list_subscriptions(session: Session, platform: str, openid: str) -> list[Subscription]:
    return list(
        session.scalars(
            select(Subscription)
            .where(Subscription.platform == platform, Subscription.openid == openid)
            .order_by(Subscription.event_key)
        )
    )


def subscribe(
    session: Session,
    platform: str,
    openid: str,
    event_key: str,
    match_keys: list[str] | None = None,
) -> tuple[Subscription, bool, bool]:
    snapshot = permission_snapshot(session, platform, openid)
    if snapshot.account_status != "active" or not snapshot.command:
        raise AuthorizationError("active command permission is required")
    event = resolve_event(session, event_key)
    try:
        requested = normalize_match_keys(match_keys)
        ensure_match_keys_allowed(requested, allowed_match_keys(event.match_key_options))
    except MatchKeyError as exc:
        raise InvalidMatchKeyError(str(exc)) from exc
    if event.match_keys_required and not requested:
        raise InvalidMatchKeyError(f"{event.event_key} requires at least one match key")
    existing = session.get(Subscription, (platform, openid, event.event_key))
    if existing is not None:
        updated = list(existing.match_keys or []) != requested
        existing.match_keys = requested
        session.flush()
        return existing, False, updated
    item = Subscription(
        platform=platform, openid=openid, event_key=event.event_key, match_keys=requested
    )
    session.add(item)
    session.flush()
    return item, True, False


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
