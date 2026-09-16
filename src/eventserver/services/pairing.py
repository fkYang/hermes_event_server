import hashlib
import secrets
from datetime import timedelta

from sqlalchemy.orm import Session

from eventserver.core.models import utc_now
from eventserver.db.models import PairingCode
from eventserver.services.users import PermissionSnapshot, require_admin, set_permissions

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class PairingCodeError(RuntimeError):
    pass


def pairing_code_hash(code: str) -> str:
    return hashlib.sha256(code.upper().encode()).hexdigest()


def create_pairing_code(
    session: Session, platform: str, openid: str, ttl_minutes: int = 10
) -> tuple[str, PairingCode]:
    code = "".join(secrets.choice(ALPHABET) for _ in range(8))
    row = PairingCode(
        code_hash=pairing_code_hash(code),
        platform=platform,
        openid=openid,
        expires_at=utc_now() + timedelta(minutes=ttl_minutes),
    )
    session.add(row)
    session.flush()
    return code, row


def approve_pairing_code(
    session: Session,
    *,
    code: str,
    permissions: set[str],
    operator_openid: str,
    platform: str = "qqbot",
    request_id: str | None = None,
) -> PermissionSnapshot:
    require_admin(session, platform, operator_openid)
    row = session.get(PairingCode, pairing_code_hash(code))
    now = utc_now()
    if row is None or row.platform != platform:
        raise PairingCodeError("pairing code is invalid")
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=now.tzinfo)
    if row.consumed_at is not None or expires_at <= now:
        raise PairingCodeError("pairing code is expired or already consumed")
    snapshot = set_permissions(
        session,
        platform=platform,
        openid=row.openid,
        permissions=permissions,
        granted=True,
        operator_openid=operator_openid,
        request_id=request_id,
    )
    row.approved_by = operator_openid
    row.approved_at = now
    row.consumed_at = now
    session.flush()
    return snapshot
