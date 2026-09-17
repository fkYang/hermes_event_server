from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from scheduled_reminder.config import IntervalRule, ReminderRule, WeeklyRule


@dataclass(frozen=True, order=True)
class DueReminder:
    scheduled_for: datetime
    reminder_id: str
    rule: ReminderRule


def due_between(rule: ReminderRule, after: datetime, until: datetime) -> list[DueReminder]:
    if after.tzinfo is None or until.tzinfo is None:
        raise ValueError("schedule bounds must be timezone-aware")
    if until <= after:
        return []
    if isinstance(rule, WeeklyRule):
        return _weekly_due(rule, after.astimezone(UTC), until.astimezone(UTC))
    return _interval_due(rule, after.astimezone(UTC), until.astimezone(UTC))


def _weekly_due(rule: WeeklyRule, after: datetime, until: datetime) -> list[DueReminder]:
    local_after = after.astimezone(rule.timezone)
    local_until = until.astimezone(rule.timezone)
    date_cursor = local_after.date()
    due: list[DueReminder] = []
    while date_cursor <= local_until.date():
        if date_cursor.weekday() in rule.weekdays:
            for scheduled_time in rule.times:
                naive = datetime.combine(date_cursor, scheduled_time)
                for candidate in _valid_local_occurrences(naive, rule.timezone):
                    utc_candidate = candidate.astimezone(UTC)
                    if after < utc_candidate <= until:
                        due.append(DueReminder(utc_candidate, rule.reminder_id, rule))
        date_cursor += timedelta(days=1)
    return due


def _valid_local_occurrences(naive: datetime, timezone) -> tuple[datetime, ...]:
    """Return valid wall-clock occurrences, including both DST folds when applicable."""
    occurrences: list[datetime] = []
    for fold in (0, 1):
        candidate = naive.replace(tzinfo=timezone, fold=fold)
        round_trip = candidate.astimezone(UTC).astimezone(timezone)
        if round_trip.replace(tzinfo=None) == naive and all(
            candidate.astimezone(UTC) != existing.astimezone(UTC) for existing in occurrences
        ):
            occurrences.append(candidate)
    return tuple(occurrences)


def _interval_due(rule: IntervalRule, after: datetime, until: datetime) -> list[DueReminder]:
    anchor = rule.anchor_at.astimezone(UTC)
    period = timedelta(minutes=rule.every_minutes)
    if until < anchor:
        return []
    elapsed = after - anchor
    first_index = max(0, int(elapsed // period) + 1)
    due: list[DueReminder] = []
    index = first_index
    while True:
        candidate = anchor + index * period
        if candidate > until:
            return due
        if candidate > after:
            due.append(DueReminder(candidate, rule.reminder_id, rule))
        index += 1
