from datetime import UTC, datetime

from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session

from eventserver.db.models import ProviderInstance
from eventserver.scheduler.leases import (
    claim_due_providers,
    due_provider_statement,
    release_provider_lease,
)


def test_provider_claim_uses_skip_locked_and_advances_schedule(session: Session) -> None:
    now = datetime(2026, 9, 14, 12, tzinfo=UTC)
    session.add(
        ProviderInstance(
            provider_instance_id="provider-1",
            provider_key="warframe.cetus_night",
            capability="polling",
            interval_seconds=30,
        )
    )
    session.commit()

    [lease] = claim_due_providers(session, owner="scheduler-1", now=now)
    assert lease.provider_instance_id == "provider-1"
    assert claim_due_providers(session, owner="scheduler-2", now=now) == []
    assert release_provider_lease(session, "provider-1", "scheduler-2") is False
    assert release_provider_lease(session, "provider-1", "scheduler-1") is True

    sql = str(due_provider_statement(now=now, limit=10).compile(dialect=mysql.dialect())).upper()
    assert "FOR UPDATE SKIP LOCKED" in sql
