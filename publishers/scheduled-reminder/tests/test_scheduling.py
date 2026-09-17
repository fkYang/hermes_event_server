from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from scheduled_reminder.config import IntervalRule, WeeklyRule
from scheduled_reminder.scheduling import due_between


def test_weekly_rule_supports_multiple_sunday_times() -> None:
    rule = WeeklyRule(
        "sunday-status",
        "Sunday",
        "Reminder",
        ZoneInfo("Asia/Shanghai"),
        (6,),
        (time(9), time(18, 30)),
    )
    after = datetime(2026, 9, 19, 16, 0, tzinfo=UTC)
    until = datetime(2026, 9, 20, 11, 0, tzinfo=UTC)
    due = due_between(rule, after, until)
    assert [item.scheduled_for.isoformat() for item in due] == [
        "2026-09-20T01:00:00+00:00",
        "2026-09-20T10:30:00+00:00",
    ]


def test_interval_rule_uses_anchor_and_does_not_repeat_boundary() -> None:
    rule = IntervalRule(
        "two-hour-review",
        "Review",
        "Reminder",
        ZoneInfo("Asia/Shanghai"),
        datetime(2026, 9, 16, 9, tzinfo=ZoneInfo("Asia/Shanghai")),
        120,
    )
    after = datetime(2026, 9, 16, 1, tzinfo=UTC)
    until = datetime(2026, 9, 16, 6, tzinfo=UTC)
    due = due_between(rule, after, until)
    assert [item.scheduled_for.isoformat() for item in due] == [
        "2026-09-16T03:00:00+00:00",
        "2026-09-16T05:00:00+00:00",
    ]
