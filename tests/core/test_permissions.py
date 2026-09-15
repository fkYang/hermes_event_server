from sqlalchemy.orm import Session

from eventserver.db.models import User, UserPermission
from eventserver.services.users import (
    AuthorizationError,
    LastAdminError,
    change_role,
    permission_snapshot,
    set_permissions,
)


def seed_admin(session: Session, openid: str = "admin-openid") -> None:
    session.add(User(platform="qqbot", openid=openid, role="admin"))
    session.add(
        UserPermission(platform="qqbot", openid=openid, permission_key="command", granted=True)
    )
    session.commit()


def test_chat_and_command_permissions_are_independent(session: Session) -> None:
    seed_admin(session)
    for permissions, expected in [
        ({"chat"}, (True, False)),
        ({"command"}, (False, True)),
        ({"chat", "command"}, (True, True)),
    ]:
        openid = "user-" + "-".join(sorted(permissions))
        snapshot = set_permissions(
            session,
            platform="qqbot",
            openid=openid,
            permissions=permissions,
            granted=True,
            operator_openid="admin-openid",
        )
        assert (snapshot.chat, snapshot.command) == expected

    unknown = permission_snapshot(session, "qqbot", "missing")
    assert unknown.account_status == "unknown"
    assert (unknown.chat, unknown.command) == (False, False)


def test_operator_requires_active_admin_and_command_permission(session: Session) -> None:
    session.add(User(platform="qqbot", openid="role-only", role="admin"))
    session.commit()
    try:
        set_permissions(
            session,
            platform="qqbot",
            openid="target",
            permissions={"chat"},
            granted=True,
            operator_openid="role-only",
        )
    except AuthorizationError:
        pass
    else:
        raise AssertionError("admin role without command permission must be rejected")


def test_last_active_admin_cannot_be_demoted(session: Session) -> None:
    seed_admin(session)
    try:
        change_role(
            session,
            platform="qqbot",
            openid="admin-openid",
            role="user",
            operator_openid="admin-openid",
        )
    except LastAdminError:
        pass
    else:
        raise AssertionError("last active admin was demoted")


def test_last_active_admin_cannot_lose_command_permission(session: Session) -> None:
    seed_admin(session)
    try:
        set_permissions(
            session,
            platform="qqbot",
            openid="admin-openid",
            permissions={"command"},
            granted=False,
            operator_openid="admin-openid",
        )
    except LastAdminError:
        pass
    else:
        raise AssertionError("last active admin lost command permission")
