from __future__ import annotations

import json
from datetime import UTC
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scheduled_reminder.config import PublisherSettings, ReminderConfig
from scheduled_reminder.scheduling import DueReminder


class PublishError(RuntimeError):
    pass


class EventServerClient:
    def __init__(self, settings: PublisherSettings) -> None:
        self.settings = settings

    def publish(self, config: ReminderConfig, due: DueReminder) -> None:
        scheduled_at = due.scheduled_for.astimezone(UTC).isoformat().replace("+00:00", "Z")
        rule = due.rule
        payload = {
            "event_key": config.event_key,
            "schema_version": config.schema_version,
            "dedupe_key": f"{due.reminder_id}:{scheduled_at}",
            "occurred_at": scheduled_at,
            "subject": {"type": "reminder", "id": due.reminder_id},
            "data": {
                "reminder_id": due.reminder_id,
                "schedule_kind": rule.kind,
                "scheduled_for": scheduled_at,
                "timezone": str(rule.timezone),
                "title": rule.title,
            },
            "metadata": {"source": "scheduled-reminder"},
            "messages": {
                "default": {
                    "title": rule.title,
                    "text": rule.text,
                    "data": {"reminder_id": due.reminder_id, "scheduled_for": scheduled_at},
                    "template_key": "reminder.scheduled.triggered.default",
                    "template_version": 1,
                }
            },
        }
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        request = Request(
            f"{self.settings.event_server_url}/v1/publish/events",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.settings.publisher_token}",
                "Content-Type": "application/json",
                "User-Agent": "AutoQQ-ScheduledReminderPublisher/0.1",
            },
        )
        try:
            with urlopen(request, timeout=self.settings.timeout_seconds) as response:
                if response.status != 200:
                    raise PublishError(f"EventServer returned HTTP {response.status}")
                if len(response.read(65537)) > 65536:
                    raise PublishError("EventServer response exceeds the 64 KiB limit")
        except HTTPError as exc:
            raise PublishError(f"EventServer returned HTTP {exc.code}") from exc
        except URLError as exc:
            raise PublishError("EventServer is unreachable") from exc
