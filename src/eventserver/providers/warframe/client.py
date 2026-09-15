import json
from collections.abc import Callable
from time import sleep
from typing import Any

import httpx

WORLDSTATE_URL = "https://api.warframe.com/cdn/worldState.php"
USER_AGENT = "AutoQQ-EventServer/0.1 (+internal-event-provider)"


class WorldStateError(RuntimeError):
    pass


class WarframeWorldStateClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = 10,
        max_response_bytes: int = 4 * 1024 * 1024,
        max_attempts: int = 2,
        transport: httpx.BaseTransport | None = None,
        sleep_fn: Callable[[float], None] = sleep,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.max_attempts = max_attempts
        self.transport = transport
        self.sleep_fn = sleep_fn

    def fetch(self) -> dict[str, Any]:
        timeout = httpx.Timeout(self.timeout_seconds, connect=min(3, self.timeout_seconds))
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                return self._fetch_once(timeout)
            except (httpx.TransportError, WorldStateError) as exc:
                last_error = exc
                if attempt + 1 >= self.max_attempts:
                    break
                self.sleep_fn(0.25 * (2**attempt))
        raise WorldStateError("Warframe WorldState request failed") from last_error

    def _fetch_once(self, timeout: httpx.Timeout) -> dict[str, Any]:
        with (
            httpx.Client(
                timeout=timeout,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                follow_redirects=False,
                transport=self.transport,
            ) as client,
            client.stream("GET", WORLDSTATE_URL) as response,
        ):
            if response.status_code != 200:
                raise WorldStateError(f"unexpected WorldState status: {response.status_code}")
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > self.max_response_bytes:
                raise WorldStateError("WorldState response is too large")
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > self.max_response_bytes:
                    raise WorldStateError("WorldState response is too large")
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WorldStateError("WorldState response is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise WorldStateError("WorldState root must be an object")
        return payload
