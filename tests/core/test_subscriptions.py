import pytest
from sqlalchemy.orm import Session

from eventserver.db.models import EventAlias, EventType, User, UserPermission
from eventserver.services.subscriptions import InvalidMatchKeyError, subscribe, unsubscribe


def test_subscribe_resolves_alias_and_is_idempotent(session: Session) -> None:
    session.add(User(platform="qqbot", openid="user-1"))
    session.add(
        UserPermission(platform="qqbot", openid="user-1", permission_key="command", granted=True)
    )
    session.add(EventType(event_key="warframe.cetus.night", display_name="Cetus night"))
    session.add(EventAlias(alias_key="cetus_night", event_key="warframe.cetus.night"))
    session.commit()

    first, created, updated = subscribe(session, "qqbot", "user-1", "cetus_night")
    second, created_again, updated_again = subscribe(
        session, "qqbot", "user-1", "warframe.cetus.night"
    )
    assert first.event_key == second.event_key == "warframe.cetus.night"
    assert created is True
    assert created_again is False
    assert updated is False and updated_again is False
    assert unsubscribe(session, "qqbot", "user-1", "cetus_night") is True
    assert unsubscribe(session, "qqbot", "user-1", "cetus_night") is False


def _seed_watchable_event(session: Session, *, required: bool = False) -> None:
    session.add(User(platform="qqbot", openid="watcher"))
    session.add(
        UserPermission(platform="qqbot", openid="watcher", permission_key="command", granted=True)
    )
    session.add(
        EventType(
            event_key="warframe.cetus.bounty_current",
            display_name="Cetus bounty current",
            match_key_field="match_keys",
            match_keys_required=required,
            match_key_options=[
                {"key": "RescueBountyResc", "label": "搜索并救援"},
                {"key": "ReclamationBountyCap", "label": "捕获 Grineer 特工"},
            ],
        )
    )
    session.commit()


def test_subscribe_stores_sorted_match_keys_and_updates_idempotently(session: Session) -> None:
    _seed_watchable_event(session)
    item, created, updated = subscribe(
        session,
        "qqbot",
        "watcher",
        "warframe.cetus.bounty_current",
        ["ReclamationBountyCap", "RescueBountyResc", "RescueBountyResc"],
    )
    assert created is True and updated is False
    assert item.match_keys == ["ReclamationBountyCap", "RescueBountyResc"]

    _, created_again, updated_again = subscribe(
        session, "qqbot", "watcher", "warframe.cetus.bounty_current", item.match_keys
    )
    assert created_again is False and updated_again is False

    _, _, updated_keys = subscribe(
        session, "qqbot", "watcher", "warframe.cetus.bounty_current", ["RescueBountyResc"]
    )
    assert updated_keys is True


def test_subscribe_rejects_an_unknown_match_key(session: Session) -> None:
    _seed_watchable_event(session)
    with pytest.raises(InvalidMatchKeyError):
        subscribe(session, "qqbot", "watcher", "warframe.cetus.bounty_current", ["NotInCatalog"])


def test_subscribe_requires_match_keys_when_the_catalog_demands_them(session: Session) -> None:
    _seed_watchable_event(session, required=True)
    with pytest.raises(InvalidMatchKeyError):
        subscribe(session, "qqbot", "watcher", "warframe.cetus.bounty_current", [])
