from sqlalchemy.orm import Session

from eventserver.config import get_settings
from eventserver.core.models import utc_now
from eventserver.db.models import EventType, ProviderInstance, User, UserPermission
from eventserver.db.session import SessionLocal

LEGACY_EVENT_KEYS = frozenset(
    {"warframe.cetus.night", "warframe.konzu.rotation", "warframe.ghoul.started"}
)
LEGACY_PROVIDER_KEYS = frozenset(
    {"warframe.cetus_night", "warframe.konzu_rotation", "warframe.ghoul_event"}
)


def bootstrap(
    session: Session,
    admin_openids: tuple[str, ...],
) -> None:
    for event_key in LEGACY_EVENT_KEYS:
        row = session.get(EventType, event_key)
        if row is not None:
            row.enabled = False
            if row.deprecated_at is None:
                row.deprecated_at = utc_now()
    for instance in session.query(ProviderInstance).all():
        if instance.provider_key in LEGACY_PROVIDER_KEYS:
            instance.enabled = False
    for openid in admin_openids:
        user = session.get(User, ("qqbot", openid))
        if user is None:
            user = User(platform="qqbot", openid=openid)
            session.add(user)
        user.account_status = "active"
        user.role = "admin"
        for key in ("chat", "command"):
            permission = session.get(UserPermission, ("qqbot", openid, key))
            if permission is None:
                permission = UserPermission(platform="qqbot", openid=openid, permission_key=key)
                session.add(permission)
            permission.granted = True
            permission.granted_by = "bootstrap"
    session.commit()


def main() -> None:
    settings = get_settings()
    with SessionLocal() as session:
        bootstrap(session, settings.initial_admin_openids)
    admin_count = len(settings.initial_admin_openids)
    print(f"retired legacy in-image providers; initialized {admin_count} admins")


if __name__ == "__main__":
    main()
