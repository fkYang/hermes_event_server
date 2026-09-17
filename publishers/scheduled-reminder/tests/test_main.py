from datetime import UTC, datetime

from scheduled_reminder.config import PublisherSettings
from scheduled_reminder.main import ReminderPublisher


class FakeClient:
    def __init__(self) -> None:
        self.published = []

    def publish(self, config, due) -> None:
        self.published.append((config, due))


def test_first_run_does_not_backfill_then_publishes_due_rule(tmp_path) -> None:
    config_file = tmp_path / "reminders.json"
    config_file.write_text(
        """{
          "event_key": "reminder.scheduled.triggered",
          "reminders": [{
            "id": "every-hour", "kind": "interval", "timezone": "UTC",
            "anchor_at": "2026-09-16T00:00:00Z", "every_minutes": 60,
            "title": "Hourly", "text": "Message"
          }]
        }""",
        encoding="utf-8",
    )
    settings = PublisherSettings("http://eventserver", "x" * 32, config_file)
    client = FakeClient()
    publisher = ReminderPublisher(settings, client)
    assert publisher.run_once(datetime(2026, 9, 16, 0, 15, tzinfo=UTC)) == 0
    assert publisher.run_once(datetime(2026, 9, 16, 1, 1, tzinfo=UTC)) == 1
    assert client.published[0][1].scheduled_for == datetime(2026, 9, 16, 1, tzinfo=UTC)
