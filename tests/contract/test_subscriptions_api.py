from fastapi.testclient import TestClient
from sqlalchemy import func, select

from eventserver.db.models import AuditLog, EventType, Subscription, User, UserPermission

EVENT_KEY = "warframe.cetus.bounty_current"
ENDPOINT = "/v1/users/watcher/subscriptions"


def _seed(session) -> None:
    session.add(User(platform="qqbot", openid="watcher", account_status="active", role="user"))
    session.add(
        UserPermission(platform="qqbot", openid="watcher", permission_key="command", granted=True)
    )
    session.add(
        EventType(
            event_key=EVENT_KEY,
            display_name="Cetus bounty current",
            match_key_field="match_keys",
            match_keys_required=True,
            match_key_options=[
                {"key": "RescueBountyResc", "label": "搜索并救援"},
                {"key": "ReclamationBountyCap", "label": "捕获 Grineer 特工"},
            ],
        )
    )
    session.commit()


def test_event_listing_exposes_match_key_options(client: TestClient, session) -> None:
    _seed(session)
    response = client.get("/v1/events")
    assert response.status_code == 200
    [event] = response.json()
    assert event["match_key_field"] == "match_keys"
    assert event["match_keys_required"] is True
    assert [option["key"] for option in event["match_key_options"]] == [
        "RescueBountyResc",
        "ReclamationBountyCap",
    ]


def test_subscription_creates_then_updates_match_keys(client: TestClient, session) -> None:
    _seed(session)
    first = client.post(ENDPOINT, json={"event_key": EVENT_KEY, "match_keys": ["RescueBountyResc"]})
    assert first.status_code == 200
    assert first.json()["created"] is True
    assert first.json()["updated"] is False
    assert first.json()["match_keys"] == ["RescueBountyResc"]

    repeated = client.post(
        ENDPOINT, json={"event_key": EVENT_KEY, "match_keys": ["RescueBountyResc"]}
    )
    assert repeated.json()["created"] is False
    assert repeated.json()["updated"] is False

    changed = client.post(
        ENDPOINT,
        json={"event_key": EVENT_KEY, "match_keys": ["ReclamationBountyCap", "RescueBountyResc"]},
    )
    assert changed.json()["created"] is False
    assert changed.json()["updated"] is True
    assert session.scalar(select(Subscription.match_keys)) == [
        "ReclamationBountyCap",
        "RescueBountyResc",
    ]
    listed = client.get(ENDPOINT).json()
    assert listed[0]["match_keys"] == ["ReclamationBountyCap", "RescueBountyResc"]
    assert session.scalar(select(func.count()).select_from(AuditLog)) == 3


def test_subscription_rejects_missing_and_unknown_match_keys(client: TestClient, session) -> None:
    _seed(session)
    missing = client.post(ENDPOINT, json={"event_key": EVENT_KEY, "match_keys": []})
    unknown = client.post(ENDPOINT, json={"event_key": EVENT_KEY, "match_keys": ["NotInCatalog"]})
    assert missing.status_code == 400
    assert unknown.status_code == 400
    assert session.scalar(select(func.count()).select_from(Subscription)) == 0


def test_delete_subscription_is_idempotent_and_audited(client: TestClient, session) -> None:
    _seed(session)
    client.post(ENDPOINT, json={"event_key": EVENT_KEY, "match_keys": ["RescueBountyResc"]})
    first = client.delete(f"{ENDPOINT}/{EVENT_KEY}")
    second = client.delete(f"{ENDPOINT}/{EVENT_KEY}")
    assert first.json()["deleted"] is True
    assert second.json()["deleted"] is False
    results = set(session.scalars(select(AuditLog.result)))
    assert "noop" in results
