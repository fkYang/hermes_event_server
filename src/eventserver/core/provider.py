from __future__ import annotations

from typing import Any, Protocol

from eventserver.core.models import (
    DeliveryMessage,
    DomainEvent,
    Observation,
    ProviderHealth,
    ProviderMetadata,
)


class Provider(Protocol):
    def metadata(self) -> ProviderMetadata: ...

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]: ...

    def normalize(self, raw: dict[str, Any]) -> Observation: ...

    def evaluate(self, previous: Observation | None, current: Observation) -> list[DomainEvent]: ...

    def render(self, event: DomainEvent, locale: str = "zh-CN") -> DeliveryMessage: ...

    def health(self) -> ProviderHealth: ...


class PollingProvider(Provider, Protocol):
    def collect(self, checkpoint: dict[str, Any] | None) -> dict[str, Any] | None: ...
