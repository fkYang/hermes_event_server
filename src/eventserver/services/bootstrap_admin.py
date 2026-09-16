from sqlalchemy import select
from sqlalchemy.orm import Session

from eventserver.core.models import utc_now
from eventserver.db.models import AuditLog, PairingCode, User, UserPermission
from eventserver.services.common import mask_identifier
from eventserver.services.pairing import ALPHABET, pairing_code_hash
from eventserver.services.users import (
    PermissionSnapshot,
    active_command_admin_count,
    permission_snapshot,
)


class FirstAdminBootstrapError(RuntimeError):
    pass


def bootstrap_first_admin(
    session: Session, *, code: str, platform: str = "qqbot"
) -> PermissionSnapshot:
    if active_command_admin_count(session, platform) != 0:
        raise FirstAdminBootstrapError("an active administrator already exists")

    normalized_code = code.strip().upper()
    if len(normalized_code) != 8 or any(char not in ALPHABET for char in normalized_code):
        raise FirstAdminBootstrapError("pairing code is invalid, expired, or already consumed")

    row = session.scalar(
        select(PairingCode)
        .where(PairingCode.code_hash == pairing_code_hash(normalized_code))
        .with_for_update()
    )
    now = utc_now()
    if row is None or row.platform != platform:
        raise FirstAdminBootstrapError("pairing code is invalid, expired, or already consumed")
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=now.tzinfo)
    if row.consumed_at is not None or expires_at <= now:
        raise FirstAdminBootstrapError("pairing code is invalid, expired, or already consumed")

    user = session.get(User, (platform, row.openid))
    if user is not None and user.account_status == "blocked":
        raise FirstAdminBootstrapError("the pairing target is blocked")
    if user is None:
        user = User(platform=platform, openid=row.openid)
        session.add(user)
        session.flush()
    user.account_status = "active"
    user.role = "admin"

    for key in ("chat", "command"):
        permission = session.get(UserPermission, (platform, row.openid, key))
        if permission is None:
            permission = UserPermission(
                platform=platform,
                openid=row.openid,
                permission_key=key,
            )
            session.add(permission)
        permission.granted = True
        permission.granted_by = "bootstrap-pairing"

    row.approved_by = "bootstrap"
    row.approved_at = now
    row.consumed_at = now
    session.add(
        AuditLog(
            actor_platform="system",
            actor_openid_masked=None,
            target_type="user",
            target_id_masked=mask_identifier(row.openid),
            action="bootstrap_first_admin",
            result="success",
            details={
                "platform": platform,
                "role": "admin",
                "permissions": ["chat", "command"],
                "source": "pairing_code",
            },
        )
    )
    session.flush()
    return permission_snapshot(session, platform, row.openid)
