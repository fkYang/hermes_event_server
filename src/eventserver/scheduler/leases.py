from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from eventserver.core.models import utc_now
from eventserver.db.models import ProviderCheckpoint, ProviderInstance


@dataclass(frozen=True)
class ProviderLease:
    provider_instance_id: str
    provider_key: str
    config: dict[str, object]
    lease_until: datetime


def due_provider_statement(*, now: datetime, limit: int) -> Select[tuple[ProviderInstance]]:
    return (
        select(ProviderInstance)
        .outerjoin(
            ProviderCheckpoint,
            ProviderCheckpoint.provider_instance_id == ProviderInstance.provider_instance_id,
        )
        .where(
            ProviderInstance.enabled.is_(True),
            or_(ProviderInstance.next_run_at.is_(None), ProviderInstance.next_run_at <= now),
            or_(
                ProviderCheckpoint.provider_instance_id.is_(None),
                ProviderCheckpoint.lease_until.is_(None),
                ProviderCheckpoint.lease_until < now,
            ),
        )
        .order_by(ProviderInstance.next_run_at, ProviderInstance.provider_instance_id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )


def claim_due_providers(
    session: Session,
    *,
    owner: str,
    limit: int = 10,
    lease_seconds: int = 60,
    now: datetime | None = None,
) -> list[ProviderLease]:
    now = now or utc_now()
    rows = list(session.scalars(due_provider_statement(now=now, limit=limit)))
    leases: list[ProviderLease] = []
    for instance in rows:
        checkpoint = session.get(ProviderCheckpoint, instance.provider_instance_id)
        if checkpoint is None:
            checkpoint = ProviderCheckpoint(provider_instance_id=instance.provider_instance_id)
            session.add(checkpoint)
        lease_until = now + timedelta(seconds=lease_seconds)
        checkpoint.lease_owner = owner
        checkpoint.lease_until = lease_until
        interval = instance.interval_seconds or lease_seconds
        instance.next_run_at = now + timedelta(seconds=interval)
        leases.append(
            ProviderLease(
                provider_instance_id=instance.provider_instance_id,
                provider_key=instance.provider_key,
                config=instance.config,
                lease_until=lease_until,
            )
        )
    session.flush()
    return leases


def release_provider_lease(session: Session, provider_instance_id: str, owner: str) -> bool:
    checkpoint = session.get(ProviderCheckpoint, provider_instance_id)
    if checkpoint is None or checkpoint.lease_owner != owner:
        return False
    checkpoint.lease_owner = None
    checkpoint.lease_until = None
    session.flush()
    return True
