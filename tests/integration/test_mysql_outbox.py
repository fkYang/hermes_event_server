import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Lock
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session, sessionmaker

from eventserver.config import get_settings
from eventserver.core.models import utc_now
from eventserver.db.models import Delivery, EventOccurrence, EventType
from eventserver.db.session import build_engine
from eventserver.db.transactions import run_with_deadlock_retry
from eventserver.deliveries.outbox import DeliveryOutbox, LeaseConflictError

pytestmark = pytest.mark.mysql


@pytest.fixture
def mysql_factory():
    if os.getenv("RUN_MYSQL_INTEGRATION") != "1":
        pytest.skip("set RUN_MYSQL_INTEGRATION=1 to use the configured _test database")
    settings = get_settings()
    if not settings.mysql_database.endswith("_test"):
        pytest.fail("refusing to run MySQL integration tests outside a _test database")
    engine = build_engine(settings.database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    engine.dispose()


@pytest.fixture
def seeded_deliveries(mysql_factory):
    event_key = "warframe.cetus.night"
    event_id = str(uuid4())
    delivery_ids = (str(uuid4()), str(uuid4()))
    with mysql_factory.begin() as session:
        if session.get(EventType, event_key) is None:
            session.add(EventType(event_key=event_key, display_name="Cetus night"))
        session.add(
            EventOccurrence(
                event_id=event_id,
                event_key=event_key,
                schema_version=1,
                dedupe_key=f"mysql-test-{event_id}",
                occurred_at=utc_now(),
                subject={},
                data={},
            )
        )
        session.flush()
        for delivery_id in delivery_ids:
            session.add(
                Delivery(
                    delivery_id=delivery_id,
                    event_id=event_id,
                    event_key=event_key,
                    platform="mysql-test",
                    openid=f"target-{delivery_id}",
                    message={"text": "test"},
                )
            )
    yield mysql_factory, event_id, delivery_ids
    with mysql_factory.begin() as session:
        session.execute(delete(Delivery).where(Delivery.event_id == event_id))
        session.execute(delete(EventOccurrence).where(EventOccurrence.event_id == event_id))


def test_two_workers_never_claim_the_same_delivery(seeded_deliveries) -> None:
    factory, _, delivery_ids = seeded_deliveries
    barrier = Barrier(2)

    def claim(worker: str) -> list[str]:
        with factory() as session, session.begin():
            barrier.wait(timeout=5)
            items = DeliveryOutbox(session).claim(
                worker_id=worker,
                platform="mysql-test",
                limit=1,
                lease_seconds=30,
            )
            return [item.delivery_id for item in items]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ("worker-a", "worker-b")))
    claimed = [delivery_id for result in results for delivery_id in result]
    assert len(claimed) == len(set(claimed)) == 2
    assert set(claimed) == set(delivery_ids)


def test_expired_lease_ack_fail_and_dead_state(seeded_deliveries) -> None:
    factory, _, delivery_ids = seeded_deliveries
    with factory.begin() as session:
        outbox = DeliveryOutbox(session, max_attempts=2)
        first = outbox.claim(
            worker_id="worker-a", platform="mysql-test", limit=1, lease_seconds=30
        )[0]
        row = session.get(Delivery, first.delivery_id)
        row.lease_until = utc_now() - timedelta(seconds=1)
        other_id = next(item for item in delivery_ids if item != first.delivery_id)
        session.get(Delivery, other_id).next_attempt_at = utc_now() + timedelta(hours=1)

    with factory.begin() as session:
        outbox = DeliveryOutbox(session, max_attempts=2)
        second = outbox.claim(
            worker_id="worker-b", platform="mysql-test", limit=1, lease_seconds=30
        )[0]
        assert second.delivery_id == first.delivery_id
        try:
            outbox.ack(second.delivery_id, first.lease_token)
        except LeaseConflictError:
            pass
        else:
            raise AssertionError("expired lease token was accepted")
        row = outbox.fail(
            second.delivery_id,
            second.lease_token,
            error_code="MYSQL_TEST_FAILURE",
            retryable=True,
        )
        assert row.status == "dead"

    with factory.begin() as session:
        remaining = session.get(
            Delivery, next(item for item in delivery_ids if item != first.delivery_id)
        )
        assert remaining.status == "pending"


def test_real_mysql_deadlock_is_retried(seeded_deliveries) -> None:
    factory, _, delivery_ids = seeded_deliveries
    barrier = Barrier(2)
    attempt_counts = {"left": 0, "right": 0}
    counts_lock = Lock()

    def worker(name: str, first_id: str, second_id: str) -> None:
        def operation(session: Session) -> None:
            with counts_lock:
                attempt_counts[name] += 1
                attempt = attempt_counts[name]
            session.execute(text("SET SESSION innodb_lock_wait_timeout=5"))
            session.scalar(
                select(Delivery).where(Delivery.delivery_id == first_id).with_for_update()
            )
            if attempt == 1:
                barrier.wait(timeout=5)
            session.scalar(
                select(Delivery).where(Delivery.delivery_id == second_id).with_for_update()
            )

        run_with_deadlock_retry(factory, operation, max_attempts=3)

    with ThreadPoolExecutor(max_workers=2) as pool:
        left = pool.submit(worker, "left", delivery_ids[0], delivery_ids[1])
        right = pool.submit(worker, "right", delivery_ids[1], delivery_ids[0])
        left.result(timeout=15)
        right.result(timeout=15)
    assert sum(attempt_counts.values()) >= 3
