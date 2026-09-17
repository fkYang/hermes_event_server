from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import PublisherSettings
from .messages import render
from .source import BountyWindow, to_utc_iso

USER_AGENT = "AutoQQ-WfDataPublisher/0.1"
MAX_RESPONSE_BYTES = 65_536
SCHEMA_VERSION = 1


class PublishError(RuntimeError):
    pass


def build_payload(
    window: BountyWindow,
    *,
    observed_at: datetime,
    notify_at: datetime | None,
    settings: PublisherSettings,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "event_key": window.event_key,
        "schema_version": SCHEMA_VERSION,
        "dedupe_key": window.dedupe_key,
        "occurred_at": to_utc_iso(observed_at),
        "subject": {"type": "bounty_window", "id": f"cetus.{window.section}"},
        "data": {
            "window": window.section,
            "activation": to_utc_iso(window.activation),
            "expiry": to_utc_iso(window.expiry),
            "match_keys": list(window.match_keys),
            "jobs": [job.as_dict() for job in window.jobs],
        },
        "metadata": {"source": "wf-data"},
        "messages": {
            "default": render(
                window,
                timezone=settings.display_timezone,
                lead_seconds=settings.lead_seconds,
            )
        },
    }
    if notify_at is not None:
        payload["notify_at"] = to_utc_iso(notify_at)
    return payload


class EventServerClient:
    def __init__(self, settings: PublisherSettings) -> None:
        self._settings = settings

    def publish(
        self,
        window: BountyWindow,
        *,
        observed_at: datetime,
        notify_at: datetime | None,
    ) -> None:
        payload = build_payload(
            window, observed_at=observed_at, notify_at=notify_at, settings=self._settings
        )
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        request = Request(
            f"{self._settings.event_server_url}/v1/publish/events",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._settings.publisher_token}",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urlopen(request, timeout=self._settings.request_timeout_seconds) as response:
                if response.status != 200:
                    raise PublishError(f"EventServer returned HTTP {response.status}")
                if len(response.read(MAX_RESPONSE_BYTES + 1)) > MAX_RESPONSE_BYTES:
                    raise PublishError("EventServer response exceeds the 64 KiB limit")
        except HTTPError as exc:
            raise PublishError(f"EventServer returned HTTP {exc.code}") from exc
        except URLError as exc:
            raise PublishError("EventServer is unreachable") from exc
