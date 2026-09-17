from sqlalchemy import select
from sqlalchemy.orm import Session

from eventserver.bootstrap import bootstrap
from eventserver.db.models import EventType, ProviderInstance, UserPermission


def test_bootstrap_is_idempotent_and_grants_both_permissions(session: Session) -> None:
    session.add(EventType(event_key="warframe.cetus.night", display_name="legacy"))
    session.add(
        ProviderInstance(
            provider_instance_id="legacy-cetus",
            provider_key="warframe.cetus_night",
            capability="polling",
        )
    )
    session.commit()
    bootstrap(session, ("initial-admin",))
    bootstrap(session, ("initial-admin",))
    legacy_event = session.get(EventType, "warframe.cetus.night")
    legacy_provider = session.get(ProviderInstance, "legacy-cetus")
    assert legacy_event is not None and legacy_event.enabled is False
    assert legacy_event.deprecated_at is not None
    assert legacy_provider is not None and legacy_provider.enabled is False
    permissions = list(
        session.scalars(select(UserPermission).where(UserPermission.openid == "initial-admin"))
    )
    assert {row.permission_key: row.granted for row in permissions} == {
        "chat": True,
        "command": True,
    }
