from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from eventserver.core.publication import PublicationService
from eventserver.db.models import Delivery, EventType, Subscription, User, UserPermission
from eventserver.providers import build_registry
from eventserver.providers.warframe.cetus_night import CetusNightProvider


def test_publication_is_idempotent_and_only_targets_command_enabled_users(session: Session) -> None:
    provider = CetusNightProvider()
    registry = build_registry()
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
    service = PublicationService(session, registry)
    result = service.publish(event)
    duplicate = service.publish(event)
    assert result.created is True and result.deliveries_created == 1
    assert duplicate.created is False and duplicate.deliveries_created == 0
    assert session.scalar(select(func.count()).select_from(Delivery)) == 1
