from dataclasses import dataclass

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from eventserver.db.models import AuditLog, User, UserPermission
from eventserver.services.common import mask_identifier

VALID_PERMISSIONS = frozenset({"chat", "command"})


class AuthorizationError(RuntimeError):
    pass


class LastAdminError(RuntimeError):
    pass


@dataclass(frozen=True)
class PermissionSnapshot:
    platform: str
    openid: str
    account_status: str
    role: str
    chat: bool
    command: bool


def permission_snapshot(session: Session, platform: str, openid: str) -> PermissionSnapshot:
    user = session.get(User, (platform, openid))
    if user is None:
        return PermissionSnapshot(platform, openid, "unknown", "user", False, False)
    rows = session.scalars(
        select(UserPermission).where(
            UserPermission.platform == platform, UserPermission.openid == openid
        )
    )
    values = {item.permission_key: item.granted for item in rows}
    return PermissionSnapshot(
        platform,
        openid,
        user.account_status,
        user.role,
        values.get("chat", False),
        values.get("command", False),
    )


def require_admin(session: Session, platform: str, operator_openid: str) -> User:
    snapshot = permission_snapshot(session, platform, operator_openid)
    if not (snapshot.account_status == "active" and snapshot.role == "admin" and snapshot.command):
        raise AuthorizationError("operator must be an active admin with command permission")
    return session.get(User, (platform, operator_openid))  # type: ignore[return-value]


def set_permissions(
    session: Session,
    *,
    platform: str,
    openid: str,
    permissions: set[str],
    granted: bool,
    operator_openid: str,
    request_id: str | None = None,
) -> PermissionSnapshot:
    invalid = permissions - VALID_PERMISSIONS
    if invalid or not permissions:
        raise ValueError(f"invalid permissions: {sorted(invalid)}")
    require_admin(session, platform, operator_openid)
    target = session.get(User, (platform, openid))
    if target is None:
        target = User(platform=platform, openid=openid)
        session.add(target)
        session.flush()
    if (
        not granted
        and "command" in permissions
        and target.role == "admin"
        and target.account_status == "active"
    ):
        existing_command = session.get(UserPermission, (platform, openid, "command"))
        if (
            existing_command is not None
            and existing_command.granted
            and _active_command_admin_count(session, platform) == 1
        ):
            raise LastAdminError("cannot revoke command from the last active admin")
    for key in permissions:
        row = session.get(UserPermission, (platform, openid, key))
        if row is None:
            row = UserPermission(platform=platform, openid=openid, permission_key=key)
            session.add(row)
        row.granted = granted
        row.granted_by = operator_openid
    session.add(
        AuditLog(
            actor_platform=platform,
            actor_openid_masked=mask_identifier(operator_openid),
            target_type="user",
            target_id_masked=mask_identifier(openid),
            action="grant" if granted else "revoke",
            result="success",
            request_id=request_id,
            details={"permissions": sorted(permissions)},
        )
    )
    session.flush()
    return permission_snapshot(session, platform, openid)


def change_role(
    session: Session,
    *,
    platform: str,
    openid: str,
    role: str,
    operator_openid: str,
    request_id: str | None = None,
) -> PermissionSnapshot:
    if role not in {"user", "admin"}:
        raise ValueError("role must be user or admin")
    require_admin(session, platform, operator_openid)
    target = session.get(User, (platform, openid))
    if target is None:
        target = User(platform=platform, openid=openid)
        session.add(target)
    if target.role == "admin" and role == "user" and target.account_status == "active":
        command_granted = session.scalar(
            select(UserPermission.granted).where(
                UserPermission.platform == platform,
                UserPermission.openid == openid,
                UserPermission.permission_key == "command",
            )
        )
        if command_granted:
            active_admins = _active_command_admin_count(session, platform)
            if active_admins == 1:
                raise LastAdminError("cannot demote the last active command-enabled admin")
    target.role = role
    session.add(
        AuditLog(
            actor_platform=platform,
            actor_openid_masked=mask_identifier(operator_openid),
            target_type="user",
            target_id_masked=mask_identifier(openid),
            action="change_role",
            result="success",
            request_id=request_id,
            details={"role": role},
        )
    )
    session.flush()
    return permission_snapshot(session, platform, openid)


def _active_command_admin_count(session: Session, platform: str) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(User)
            .join(
                UserPermission,
                and_(
                    UserPermission.platform == User.platform,
                    UserPermission.openid == User.openid,
                    UserPermission.permission_key == "command",
                    UserPermission.granted.is_(True),
                ),
            )
            .where(
                User.platform == platform,
                User.role == "admin",
                User.account_status == "active",
            )
        )
        or 0
    )
