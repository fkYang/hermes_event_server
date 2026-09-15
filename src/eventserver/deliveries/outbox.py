import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from eventserver.core.models import utc_now
from eventserver.db.models import Delivery


class LeaseConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class ClaimedDelivery:
    delivery_id: str
    lease_token: str
    event_id: str
    event_key: str
    platform: str
    openid: str
    message: dict[str, object]
    attempt: int
    created_at: datetime


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def claim_statement(*, platform: str, limit: int, now: datetime) -> Select[tuple[Delivery]]:
    eligible = or_(
        and_(
            Delivery.status.in_(("pending", "retry")),
            Delivery.next_attempt_at <= now,
        ),
        and_(Delivery.status == "leased", Delivery.lease_until < now),
    )
    return (
        select(Delivery)
        .where(Delivery.platform == platform, eligible)
        .order_by(Delivery.next_attempt_at, Delivery.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )


class DeliveryOutbox:
    def __init__(self, session: Session, max_attempts: int = 5) -> None:
        self.session = session
        self.max_attempts = max_attempts

    def claim(
        self,
        *,
        worker_id: str,
        platform: str,
        limit: int,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> list[ClaimedDelivery]:
        now = now or utc_now()
        rows = list(self.session.scalars(claim_statement(platform=platform, limit=limit, now=now)))
        claimed: list[ClaimedDelivery] = []
        for row in rows:
            token = secrets.token_urlsafe(32)
            row.status = "leased"
            row.attempts += 1
            row.lease_owner = worker_id
            row.lease_token_hash = _token_hash(token)
            row.lease_until = now + timedelta(seconds=lease_seconds)
            claimed.append(
                ClaimedDelivery(
                    delivery_id=row.delivery_id,
                    lease_token=token,
                    event_id=row.event_id,
                    event_key=row.event_key,
                    platform=row.platform,
                    openid=row.openid,
                    message=row.message,
                    attempt=row.attempts,
                    created_at=row.created_at,
                )
            )
        self.session.flush()
        return claimed

    def _leased(self, delivery_id: str, lease_token: str, now: datetime) -> Delivery:
        row = self.session.get(Delivery, delivery_id)
        if (
            row is None
            or row.status != "leased"
            or row.lease_token_hash is None
            or row.lease_until is None
            or _aware(row.lease_until) <= now
            or not secrets.compare_digest(row.lease_token_hash, _token_hash(lease_token))
        ):
            raise LeaseConflictError("delivery does not have a matching active lease")
        return row

    @staticmethod
    def _clear_lease(row: Delivery) -> None:
        row.lease_owner = None
        row.lease_token_hash = None
        row.lease_until = None

    def ack(
        self,
        delivery_id: str,
        lease_token: str,
        *,
        sent_at: datetime | None = None,
        platform_message_id: str | None = None,
    ) -> Delivery:
        now = utc_now()
        row = self._leased(delivery_id, lease_token, now)
        row.status = "sent"
        row.sent_at = sent_at or now
        row.platform_message_id = platform_message_id
        self._clear_lease(row)
        self.session.flush()
        return row

    def fail(
        self,
        delivery_id: str,
        lease_token: str,
        *,
        error_code: str,
        retryable: bool,
    ) -> Delivery:
        now = utc_now()
        row = self._leased(delivery_id, lease_token, now)
        row.last_error_code = error_code
        if retryable and row.attempts < self.max_attempts:
            row.status = "retry"
            delay = min(3600, 5 * (2 ** max(0, row.attempts - 1)))
            row.next_attempt_at = now + timedelta(seconds=delay)
        else:
            row.status = "dead"
        self._clear_lease(row)
        self.session.flush()
        return row
