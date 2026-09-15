from typing import Any

from eventserver.core.models import (
    DeliveryMessage,
    DomainEvent,
    Observation,
    ProviderHealth,
    ProviderMetadata,
    utc_now,
)
from eventserver.providers.warframe.common import build_event, observation, parse_time, require

PROVIDER_KEY = "warframe.cetus_night"
EVENT_KEY = "warframe.cetus.night"


class CetusNightProvider:
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_key=PROVIDER_KEY,
            event_keys=(EVENT_KEY,),
            capability="polling",
            implementation_version="1.0.0",
        )

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        return dict(config)

    def normalize(self, raw: dict[str, Any]) -> Observation:
        observed_at = parse_time(raw.get("observed_at"), fallback=utc_now())
        effective_at = parse_time(raw.get("effective_at"), fallback=observed_at)
        expires_at = parse_time(raw["expires_at"]) if raw.get("expires_at") else None
        return observation(
            provider_key=PROVIDER_KEY,
            identity=require(raw, "identity", str),
            observed_at=observed_at,
            effective_at=effective_at,
            expires_at=expires_at,
            state={"is_night": require(raw, "is_night", bool)},
        )

    def evaluate(self, previous: Observation | None, current: Observation) -> list[DomainEvent]:
        if (
            previous is None
            or previous.state.get("is_night") is True
            or current.state["is_night"] is not True
        ):
            return []
        return [
            build_event(
                event_key=EVENT_KEY,
                provider_key=PROVIDER_KEY,
                dedupe_key=current.identity,
                occurred_at=current.effective_at,
                subject={"type": "location", "id": "cetus"},
                data={"expires_at": current.expires_at.isoformat() if current.expires_at else None},
            )
        ]

    def render(self, event: DomainEvent, locale: str = "zh-CN") -> DeliveryMessage:
        text = "希图斯已进入夜晚" if locale.startswith("zh") else "Night has begun in Cetus"
        return DeliveryMessage(
            title="事件提醒" if locale.startswith("zh") else "Event alert",
            text=text,
            template_key="warframe.cetus.night.default",
            template_version=1,
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(status="healthy")
