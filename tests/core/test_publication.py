from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from eventserver.core.models import DeliveryMessage, DomainEvent
from eventserver.core.publication import PublicationService
from eventserver.db.models import Delivery, EventType, Subscription, User, UserPermission
from eventserver.providers.warframe.cetus_night import CetusNightProvider

MESSAGES = {
    "default": {
        "title": "Cetus bounty",
        "text": "bounty rotated",
        "template_key": "test.default",
        "template_version": 1,
    }
}


def test_publication_is_idempotent_and_only_targets_command_enabled_users(session: Session) -> None:
    provider = CetusNightProvider()
    session.add(EventType(event_key="warframe.cetus.night", display_name="Cetus night"))
    for openid, status, command in [
        ("enabled", "active", True),
        ("blocked", "blocked", True),
        ("chat-only", "active", False),
    ]:
        session.add(User(platform="qqbot", openid=openid, account_status=status))
        session.add(
            UserPermission(
                platform="qqbot", openid=openid, permission_key="command", granted=command
            )
        )
        session.add(Subscription(platform="qqbot", openid=openid, event_key="warframe.cetus.night"))
    session.commit()

    now = datetime(2026, 9, 14, 12, tzinfo=UTC)
    day = provider.normalize({"identity": "day", "is_night": False, "observed_at": now})
    night = provider.normalize({"identity": "night", "is_night": True, "observed_at": now})
    [event] = provider.evaluate(day, night)
    service = PublicationService(session)
    messages = {
        "default": {
            "title": "Cetus night",
            "text": "night started",
            "template_key": "test.default",
            "template_version": 1,
        }
    }
    normalized = {
        locale: DeliveryMessage.model_validate(message) for locale, message in messages.items()
    }
    result = service.publish(event, normalized)
    duplicate = service.publish(event, normalized)
    assert result.created is True and result.deliveries_created == 1
    assert duplicate.created is False and duplicate.deliveries_created == 0
    assert session.scalar(select(func.count()).select_from(Delivery)) == 1


def _seed_watchers(session: Session) -> None:
    session.add(
        EventType(
            event_key="warframe.cetus.bounty_current",
            display_name="Cetus bounty current",
            match_key_field="match_keys",
        )
    )
    for openid, watched in [
        ("watcher-a", ["RescueBountyResc"]),
        ("watcher-b", ["AttritionBountyExt"]),
        ("watcher-all", []),
    ]:
        session.add(User(platform="qqbot", openid=openid))
        session.add(
            UserPermission(platform="qqbot", openid=openid, permission_key="command", granted=True)
        )
        session.add(
            Subscription(
                platform="qqbot",
                openid=openid,
                event_key="warframe.cetus.bounty_current",
                match_keys=watched,
            )
        )
    session.commit()


def _bounty_event(data: dict) -> DomainEvent:
    return DomainEvent(
        event_id="bounty-event-1",
        event_key="warframe.cetus.bounty_current",
        schema_version=1,
        dedupe_key="2026-09-17T03:48:51Z",
        occurred_at=datetime(2026, 9, 17, 3, 48, 51, tzinfo=UTC),
        subject={"type": "location", "id": "cetus"},
        data=data,
        metadata={},
    )


def test_publication_only_delivers_to_intersecting_watchers(session: Session) -> None:
    _seed_watchers(session)
    normalized = {
        locale: DeliveryMessage.model_validate(message) for locale, message in MESSAGES.items()
    }
    result = PublicationService(session).publish(
        _bounty_event({"match_keys": ["RescueBountyResc"]}), normalized
    )
    assert result.deliveries_created == 2
    targets = set(session.scalars(select(Delivery.openid)))
    assert targets == {"watcher-a", "watcher-all"}


def test_publication_fails_closed_when_the_declared_field_is_missing(session: Session) -> None:
    _seed_watchers(session)
    normalized = {
        locale: DeliveryMessage.model_validate(message) for locale, message in MESSAGES.items()
    }
    result = PublicationService(session).publish(_bounty_event({}), normalized)
    assert result.deliveries_created == 1
    assert set(session.scalars(select(Delivery.openid))) == {"watcher-all"}
