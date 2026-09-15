from sqlalchemy.orm import Session

from eventserver.config import get_settings
from eventserver.db.models import EventAlias, EventType, ProviderInstance, User, UserPermission
from eventserver.db.session import SessionLocal

EVENTS = (
    ("warframe.cetus.night", "希图斯进入夜晚", "昼夜状态由白天变为夜晚"),
    ("warframe.konzu.rotation", "Konzu 赏金轮换", "稳定的赏金轮换标识发生变化"),
    ("warframe.ghoul.started", "尸鬼活动出现", "活动由未激活变为激活"),
)
ALIASES = {
    "cetus_night": "warframe.cetus.night",
    "konzu_rotation": "warframe.konzu.rotation",
    "ghoul_event": "warframe.ghoul.started",
}
PROVIDERS = (
    ("warframe-cetus-pc", "warframe.cetus_night", 60),
    ("warframe-konzu-pc", "warframe.konzu_rotation", 300),
    ("warframe-ghoul-pc", "warframe.ghoul_event", 300),
)


def bootstrap(
    session: Session,
    admin_openids: tuple[str, ...],
    enabled_providers: tuple[str, ...] | None = None,
) -> None:
    for event_key, display_name, description in EVENTS:
        row = session.get(EventType, event_key)
        if row is None:
            session.add(
                EventType(
                    event_key=event_key,
                    display_name=display_name,
                    description=description,
                    schema_version=1,
                )
            )
    session.flush()
    for alias_key, event_key in ALIASES.items():
        if session.get(EventAlias, alias_key) is None:
            session.add(EventAlias(alias_key=alias_key, event_key=event_key))
    enabled = (
        set(enabled_providers) if enabled_providers is not None else {row[1] for row in PROVIDERS}
    )
    for instance_id, provider_key, interval_seconds in PROVIDERS:
        if provider_key not in enabled:
            continue
        instance = session.get(ProviderInstance, instance_id)
        if instance is None:
            session.add(
                ProviderInstance(
                    provider_instance_id=instance_id,
                    provider_key=provider_key,
                    capability="polling",
                    interval_seconds=interval_seconds,
                )
            )
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
        bootstrap(session, settings.initial_admin_openids, settings.enabled_providers)
    event_count = len(EVENTS)
    admin_count = len(settings.initial_admin_openids)
    provider_count = len(settings.enabled_providers)
    print(
        f"registered {event_count} event types and {provider_count} providers; "
        f"initialized {admin_count} admins"
    )


if __name__ == "__main__":
    main()
