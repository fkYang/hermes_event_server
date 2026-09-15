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

PROVIDER_KEY = "warframe.konzu_rotation"
EVENT_KEY = "warframe.konzu.rotation"


class KonzuRotationProvider:
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
        rotation_id = require(raw, "rotation_id", str)
        return observation(
            provider_key=PROVIDER_KEY,
            identity=rotation_id,
            observed_at=observed_at,
            effective_at=effective_at,
            expires_at=expires_at,
            state={"rotation_id": rotation_id, "confirmed_summary": raw.get("confirmed_summary")},
        )

    def evaluate(self, previous: Observation | None, current: Observation) -> list[DomainEvent]:
        if previous is None or previous.identity == current.identity:
            return []
        return [
            build_event(
                event_key=EVENT_KEY,
                provider_key=PROVIDER_KEY,
                dedupe_key=current.identity,
                occurred_at=current.effective_at,
                subject={"type": "bounty_board", "id": "konzu"},
                data={
                    "rotation_id": current.identity,
                    "confirmed_summary": current.state.get("confirmed_summary"),
                    "expires_at": current.expires_at.isoformat() if current.expires_at else None,
                },
            )
        ]

    def render(self, event: DomainEvent, locale: str = "zh-CN") -> DeliveryMessage:
        summary = event.data.get("confirmed_summary")
        if locale.startswith("zh"):
            text = "Konzu 赏金已轮换"
            if summary:
                text += f"\n{summary}"
            else:
                text += "\n当前任务详情暂不可可靠解析。"
            title = "事件提醒"
        else:
            title = "Event alert"
            text = "Konzu bounties have rotated"
        return DeliveryMessage(
            title=title,
            text=text,
            template_key="warframe.konzu.rotation.default",
            template_version=1,
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(status="healthy")
