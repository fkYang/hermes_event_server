from sqlalchemy.orm import Session

from eventserver.db.models import EventAlias, EventType, User, UserPermission
from eventserver.services.subscriptions import subscribe, unsubscribe


def test_subscribe_resolves_alias_and_is_idempotent(session: Session) -> None:
    session.add(User(platform="qqbot", openid="user-1"))
    session.add(
        UserPermission(platform="qqbot", openid="user-1", permission_key="command", granted=True)
    )
    session.add(EventType(event_key="warframe.cetus.night", display_name="Cetus night"))
    session.add(EventAlias(alias_key="cetus_night", event_key="warframe.cetus.night"))
    session.commit()

    first, created = subscribe(session, "qqbot", "user-1", "cetus_night")
    second, created_again = subscribe(session, "qqbot", "user-1", "warframe.cetus.night")
    assert first.event_key == second.event_key == "warframe.cetus.night"
    assert created is True
    assert created_again is False
    assert unsubscribe(session, "qqbot", "user-1", "cetus_night") is True
    assert unsubscribe(session, "qqbot", "user-1", "cetus_night") is False
