from eventserver.core.registry import ProviderRegistry
from eventserver.providers.warframe.cetus_night import CetusNightProvider
from eventserver.providers.warframe.ghoul_event import GhoulEventProvider
from eventserver.providers.warframe.konzu_rotation import KonzuRotationProvider


def build_registry(enabled: tuple[str, ...] | None = None) -> ProviderRegistry:
    providers = (CetusNightProvider(), KonzuRotationProvider(), GhoulEventProvider())
    allowed = set(enabled) if enabled is not None else None
    registry = ProviderRegistry()
    for provider in providers:
        if allowed is None or provider.metadata().provider_key in allowed:
            registry.register(provider)
    return registry
