from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from eventserver.auth.publisher import token_hash
from eventserver.db.models import (
    AuditLog,
    Delivery,
    EventPublisher,
    EventType,
    Subscription,
    User,
    UserPermission,
)
from eventserver.deliveries.outbox import DeliveryOutbox


def _seed(session, *, prefix: str = "example.") -> str:
    token = "p" * 32
    session.add(
        EventPublisher(
            publisher_key="example-source",
            token_hash=token_hash(token),
            allowed_event_prefixes=[prefix],
        )
    )
    session.add(
        EventType(
            event_key="example.sample.available",
            display_name="Sample event",
            payload_schema={
                "type": "object",
                "required": ["activation"],
                "properties": {"activation": {"type": "string"}},
                "additionalProperties": False,
            },
        )
    )
    session.add(User(platform="qqbot", openid="subscriber"))
    session.add(
        UserPermission(
            platform="qqbot", openid="subscriber", permission_key="command", granted=True
        )
    )
    session.add(
        Subscription(platform="qqbot", openid="subscriber", event_key="example.sample.available")
    )
    session.commit()
    return token


def _body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "event_key": "example.sample.available",
        "schema_version": 1,
        "dedupe_key": "cycle-2026-09-16T12:00:00Z",
        "occurred_at": datetime(2026, 9, 16, 12, tzinfo=UTC).isoformat(),
        "subject": {"type": "location", "id": "cetus"},
        "data": {"activation": "2026-09-16T12:00:00Z"},
        "messages": {
            "default": {
                "title": "Sample available",
                "text": "The sample event is available.",
                "template_key": "example.sample.available.default",
                "template_version": 1,
            }
        },
    }
    body.update(overrides)
    return body


def test_publisher_can_publish_once_and_core_creates_delivery(client: TestClient, session) -> None:
    token = _seed(session)
    headers = {"Authorization": f"Bearer {token}"}
    first = client.post("/v1/publish/events", json=_body(), headers=headers)
    second = client.post("/v1/publish/events", json=_body(), headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["created"] is True
    assert second.json()["created"] is False
    assert session.scalar(select(func.count()).select_from(Delivery)) == 1
    audit = list(session.scalars(select(AuditLog).where(AuditLog.action == "publisher_publish")))
    assert {row.result for row in audit} == {"created", "duplicate"}


def test_publisher_is_confined_to_its_namespace_and_schema(client: TestClient, session) -> None:
    token = _seed(session)
    headers = {"Authorization": f"Bearer {token}"}
    denied = client.post(
        "/v1/publish/events", json=_body(event_key="other.sample.available"), headers=headers
    )
    invalid = client.post("/v1/publish/events", json=_body(data={}), headers=headers)
    assert denied.status_code == 403
    assert invalid.status_code == 422


def test_publisher_endpoint_rejects_missing_or_unknown_credentials(client: TestClient) -> None:
    assert client.post("/v1/publish/events", json=_body()).status_code == 401
    assert (
        client.post(
            "/v1/publish/events", json=_body(), headers={"Authorization": "Bearer unknown"}
        ).status_code
        == 401
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def test_publish_schedules_the_delivery_until_notify_at(client: TestClient, session) -> None:
    token = _seed(session)
    headers = {"Authorization": f"Bearer {token}"}
    notify_at = datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=5)
    response = client.post(
        "/v1/publish/events", json=_body(notify_at=notify_at.isoformat()), headers=headers
    )
    assert response.status_code == 200
    assert response.json()["notify_at"] is not None
    delivery = session.scalar(select(Delivery))
    assert abs((_aware(delivery.next_attempt_at) - notify_at).total_seconds()) < 1

    outbox = DeliveryOutbox(session)
    assert outbox.claim(worker_id="worker-1", platform="qqbot", limit=10, lease_seconds=60) == []
    claimed = outbox.claim(
        worker_id="worker-1",
        platform="qqbot",
        limit=10,
        lease_seconds=60,
        now=notify_at + timedelta(seconds=1),
    )
    assert [item.openid for item in claimed] == ["subscriber"]


def test_publish_rejects_naive_and_over_horizon_notify_at(client: TestClient, session) -> None:
    token = _seed(session)
    headers = {"Authorization": f"Bearer {token}"}
    far_future = datetime.now(UTC) + timedelta(days=30)
    naive = client.post(
        "/v1/publish/events",
        json=_body(notify_at="2026-09-18T12:00:00"),
        headers=headers,
    )
    too_far = client.post(
        "/v1/publish/events", json=_body(notify_at=far_future.isoformat()), headers=headers
    )
    assert naive.status_code == 422
    assert too_far.status_code == 422
    assert session.scalar(select(func.count()).select_from(Delivery)) == 0


def test_publish_with_a_past_notify_at_delivers_immediately(client: TestClient, session) -> None:
    token = _seed(session)
    headers = {"Authorization": f"Bearer {token}"}
    past = datetime.now(UTC) - timedelta(minutes=5)
    response = client.post(
        "/v1/publish/events", json=_body(notify_at=past.isoformat()), headers=headers
    )
    assert response.status_code == 200
    delivery = session.scalar(select(Delivery))
    assert _aware(delivery.next_attempt_at) <= datetime.now(UTC)
    claimed = DeliveryOutbox(session).claim(
        worker_id="worker-1", platform="qqbot", limit=10, lease_seconds=60
    )
    assert len(claimed) == 1
