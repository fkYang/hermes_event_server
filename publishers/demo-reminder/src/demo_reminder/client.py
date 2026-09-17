from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import USER_AGENT, PublisherSettings
from .messages import render, to_utc_iso
from .models import ReminderRequest

EVENT_KEY = "demo.reminder.scheduled"
SCHEMA_VERSION = 1
MAX_RESPONSE_BYTES = 65_536


class PublishError(RuntimeError):
    pass


@dataclass(frozen=True)
class PublishResult:
    event_id: str
    created: bool
    deliveries_created: int
    notify_at: datetime | None


def build_payload(request: ReminderRequest, *, settings: PublisherSettings) -> dict[str, Any]:
    return {
        "event_key": EVENT_KEY,
        "schema_version": SCHEMA_VERSION,
        "dedupe_key": request.dedupe_key,
        "occurred_at": to_utc_iso(request.requested_at),
        "notify_at": to_utc_iso(request.notify_at),
        "subject": {"type": "reminder", "id": request.request_id},
        "data": {
            "request_id": request.request_id,
            "delay_seconds": request.delay_seconds,
            "notify_at": to_utc_iso(request.notify_at),
        },
        "metadata": {"source": "demo-reminder"},
        "messages": {
            "default": render(request, event_key=EVENT_KEY, timezone=settings.display_timezone)
        },
    }


class EventServerClient:
    def __init__(self, settings: PublisherSettings) -> None:
        self._settings = settings

    def publish(self, request: ReminderRequest) -> PublishResult:
        payload = build_payload(request, settings=self._settings)
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        http_request = Request(
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
            with urlopen(http_request, timeout=self._settings.request_timeout_seconds) as response:
                if response.status != 200:
                    raise PublishError(f"EventServer returned HTTP {response.status}")
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            raise PublishError(f"EventServer returned HTTP {exc.code}") from exc
        except URLError as exc:
            raise PublishError("EventServer is unreachable") from exc
        if len(raw) > MAX_RESPONSE_BYTES:
            raise PublishError("EventServer response exceeds the 64 KiB limit")
        return _parse_response(raw)


def _parse_response(raw: bytes) -> PublishResult:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublishError("EventServer returned a malformed response") from exc
    if not isinstance(data, dict):
        raise PublishError("EventServer returned a malformed response")
    event_id = data.get("event_id")
    if not isinstance(event_id, str) or not event_id:
        raise PublishError("EventServer response is missing event_id")
    return PublishResult(
        event_id=event_id,
        created=bool(data.get("created")),
        deliveries_created=_integer_or_zero(data.get("deliveries_created")),
        notify_at=_parse_timestamp(data.get("notify_at")),
    )


def _integer_or_zero(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
