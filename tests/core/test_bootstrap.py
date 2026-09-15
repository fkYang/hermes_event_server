from sqlalchemy import func, select
from sqlalchemy.orm import Session

from eventserver.bootstrap import bootstrap
from eventserver.db.models import EventAlias, EventType, ProviderInstance, UserPermission


def test_bootstrap_is_idempotent_and_grants_both_permissions(session: Session) -> None:
    bootstrap(session, ("initial-admin",))
    bootstrap(session, ("initial-admin",))
    assert session.scalar(select(func.count()).select_from(EventType)) == 3
    assert session.scalar(select(func.count()).select_from(EventAlias)) == 3
    assert session.scalar(select(func.count()).select_from(ProviderInstance)) == 3
    permissions = list(
        session.scalars(select(UserPermission).where(UserPermission.openid == "initial-admin"))
    )
    assert {row.permission_key: row.granted for row in permissions} == {
        "chat": True,
        "command": True,
    }
