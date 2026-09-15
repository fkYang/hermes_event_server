from datetime import timedelta

from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session

from eventserver.core.models import utc_now
from eventserver.db.models import Delivery, EventOccurrence, EventType
from eventserver.deliveries.outbox import DeliveryOutbox, LeaseConflictError, claim_statement


def seed_delivery(session: Session, delivery_id: str = "delivery-1") -> Delivery:
    session.add(EventType(event_key="warframe.cetus.night", display_name="Cetus night"))
    session.add(
        EventOccurrence(
            event_id="event-1",
            event_key="warframe.cetus.night",
            schema_version=1,
            dedupe_key="cycle-1",
            occurred_at=utc_now(),
            subject={},
            data={},
        )
    )
    delivery = Delivery(
        delivery_id=delivery_id,
        event_id="event-1",
        event_key="warframe.cetus.night",
        platform="qqbot",
        openid="openid-1",
        message={"text": "hello"},
    )
    session.add(delivery)
    session.commit()
    return delivery


def test_claim_and_ack_require_matching_active_lease(session: Session) -> None:
    seed_delivery(session)
    outbox = DeliveryOutbox(session)
    [item] = outbox.claim(worker_id="worker-1", platform="qqbot", limit=10, lease_seconds=60)
    assert item.attempt == 1
    try:
        outbox.ack(item.delivery_id, "wrong-token")
    except LeaseConflictError:
        pass
    else:
        raise AssertionError("ack accepted the wrong token")
    row = outbox.ack(item.delivery_id, item.lease_token)
    assert row.status == "sent"
    assert outbox.claim(worker_id="worker-2", platform="qqbot", limit=10, lease_seconds=60) == []


def test_expired_lease_is_reclaimable_and_fail_is_bounded(session: Session) -> None:
    row = seed_delivery(session)
    outbox = DeliveryOutbox(session, max_attempts=2)
    first = outbox.claim(worker_id="worker-1", platform="qqbot", limit=1, lease_seconds=60)[0]
    row.lease_until = utc_now() - timedelta(seconds=1)
    session.flush()
    second = outbox.claim(worker_id="worker-2", platform="qqbot", limit=1, lease_seconds=60)[0]
    assert second.attempt == 2
    failed = outbox.fail(
        second.delivery_id, second.lease_token, error_code="QQ_TIMEOUT", retryable=True
    )
    assert failed.status == "dead"
    assert first.lease_token != second.lease_token


def test_mysql_claim_query_uses_skip_locked() -> None:
    statement = claim_statement(platform="qqbot", limit=10, now=utc_now())
    sql = str(statement.compile(dialect=mysql.dialect())).upper()
    assert "FOR UPDATE SKIP LOCKED" in sql
