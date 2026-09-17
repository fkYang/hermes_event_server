import json

import pytest

from scheduled_reminder.config import ConfigurationError, load_config


def test_load_config_accepts_weekly_multiple_times_and_interval(tmp_path) -> None:
    path = tmp_path / "reminders.json"
    path.write_text(
        json.dumps(
            {
                "event_key": "reminder.scheduled.triggered",
                "reminders": [
                    {
                        "id": "weekly",
                        "kind": "weekly",
                        "timezone": "Asia/Shanghai",
                        "weekdays": ["sunday"],
                        "times": ["18:30", "09:00"],
                        "title": "Weekly",
                        "text": "Message",
                    },
                    {
                        "id": "interval",
                        "kind": "interval",
                        "timezone": "Asia/Shanghai",
                        "anchor_at": "2026-09-16T09:00:00+08:00",
                        "every_minutes": 30,
                        "title": "Interval",
                        "text": "Message",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.event_key == "reminder.scheduled.triggered"
    assert config.rules[0].times[0].isoformat() == "09:00:00"
    assert config.rules[1].every_minutes == 30


def test_load_config_rejects_duplicate_ids(tmp_path) -> None:
    path = tmp_path / "reminders.json"
    path.write_text(
        json.dumps(
            {
                "event_key": "reminder.scheduled.triggered",
                "reminders": [
                    {
                        "id": "same",
                        "kind": "weekly",
                        "timezone": "Asia/Shanghai",
                        "weekdays": ["sunday"],
                        "times": ["09:00"],
                        "title": "A",
                        "text": "A",
                    },
                    {
                        "id": "same",
                        "kind": "weekly",
                        "timezone": "Asia/Shanghai",
                        "weekdays": ["monday"],
                        "times": ["09:00"],
                        "title": "B",
                        "text": "B",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="unique"):
        load_config(path)


def test_load_config_allows_an_empty_rule_set_for_safe_initial_deployment(tmp_path) -> None:
    path = tmp_path / "reminders.json"
    path.write_text(
        json.dumps({"event_key": "reminder.scheduled.triggered", "reminders": []}),
        encoding="utf-8",
    )
    assert load_config(path).rules == ()
