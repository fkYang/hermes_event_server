from eventserver.core.provider import Provider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}
        self._events: dict[str, Provider] = {}

    def register(self, provider: Provider) -> None:
        metadata = provider.metadata()
        if metadata.provider_key in self._providers:
            raise ValueError(f"duplicate provider_key: {metadata.provider_key}")
        duplicates = set(metadata.event_keys).intersection(self._events)
        if duplicates:
            raise ValueError(f"duplicate event keys: {sorted(duplicates)}")
        self._providers[metadata.provider_key] = provider
        for event_key in metadata.event_keys:
            self._events[event_key] = provider

    def provider_for_event(self, event_key: str) -> Provider:
        try:
            return self._events[event_key]
        except KeyError as exc:
            raise KeyError(f"no provider registered for event: {event_key}") from exc

    def get(self, provider_key: str) -> Provider:
        return self._providers[provider_key]

    def all(self) -> tuple[Provider, ...]:
        return tuple(self._providers.values())
