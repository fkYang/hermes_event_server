from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from eventserver.core.processing import ObservationProcessor
from eventserver.db.models import (
    Delivery,
    EventOccurrence,
    EventType,
    ProviderInstance,
    Subscription,
    User,
    UserPermission,
)
from eventserver.providers import build_registry


def test_observation_pipeline_baselines_then_publishes(session: Session) -> None:
    session.add(EventType(event_key="warframe.cetus.night", display_name="Cetus night"))
    session.add(
        ProviderInstance(
            provider_instance_id="cetus-pc",
            provider_key="warframe.cetus_night",
            capability="polling",
            interval_seconds=60,
        )
    )
    session.add(User(platform="qqbot", openid="subscriber"))
    session.add(
        UserPermission(
            platform="qqbot", openid="subscriber", permission_key="command", granted=True
        )
    )
    session.add(
        Subscription(platform="qqbot", openid="subscriber", event_key="warframe.cetus.night")
    )
    session.commit()

    processor = ObservationProcessor(session, build_registry())
    now = datetime(2026, 9, 14, 12, tzinfo=UTC)
    baseline = processor.process(
        "cetus-pc", {"identity": "day-cycle", "is_night": False, "observed_at": now}
    )
    unchanged = processor.process(
        "cetus-pc", {"identity": "day-cycle", "is_night": False, "observed_at": now}
    )
    changed = processor.process(
        "cetus-pc", {"identity": "night-cycle", "is_night": True, "observed_at": now}
    )

    assert baseline.baseline_created is True and baseline.publications == ()
    assert unchanged.unchanged is True
    assert changed.publications[0].deliveries_created == 1
    assert session.scalar(select(func.count()).select_from(EventOccurrence)) == 1
    assert session.scalar(select(func.count()).select_from(Delivery)) == 1
