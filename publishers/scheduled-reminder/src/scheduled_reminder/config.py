from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class PublisherSettings:
    event_server_url: str
    publisher_token: str
    config_file: Path
    timeout_seconds: float = 10.0
    tick_seconds: float = 15.0

    @classmethod
    def from_environment(cls) -> PublisherSettings:
        url = os.environ.get("EVENTSERVER_URL", "").rstrip("/")
        token = os.environ.get("PUBLISHER_TOKEN", "")
        config_file = Path(os.environ.get("REMINDER_CONFIG_FILE", "/config/reminders.json"))
        if not url.startswith(("http://", "https://")):
            raise ConfigurationError("EVENTSERVER_URL must be an http(s) URL")
        if len(token) < 32:
            raise ConfigurationError("PUBLISHER_TOKEN must contain at least 32 characters")
        return cls(event_server_url=url, publisher_token=token, config_file=config_file)


@dataclass(frozen=True)
class WeeklyRule:
    reminder_id: str
    title: str
    text: str
    timezone: ZoneInfo
    weekdays: tuple[int, ...]
    times: tuple[time, ...]
    kind: Literal["weekly"] = "weekly"


@dataclass(frozen=True)
class IntervalRule:
    reminder_id: str
    title: str
    text: str
    timezone: ZoneInfo
    anchor_at: datetime
    every_minutes: int
    kind: Literal["interval"] = "interval"


ReminderRule = WeeklyRule | IntervalRule


@dataclass(frozen=True)
class ReminderConfig:
    event_key: str
    schema_version: int
    rules: tuple[ReminderRule, ...]
    max_due_per_tick: int = 100


def load_config(path: Path) -> ReminderConfig:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigurationError(f"cannot read reminder config: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"reminder config is not valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ConfigurationError("reminder config must be an object")
    event_key = _required_string(payload, "event_key")
    if not _valid_event_key(event_key):
        raise ConfigurationError("event_key must use <domain>.<resource>.<event> syntax")
    schema_version = payload.get("schema_version", 1)
    if not isinstance(schema_version, int) or schema_version < 1:
        raise ConfigurationError("schema_version must be a positive integer")
    max_due = payload.get("max_due_per_tick", 100)
    if not isinstance(max_due, int) or not 1 <= max_due <= 1000:
        raise ConfigurationError("max_due_per_tick must be between 1 and 1000")
    raw_rules = payload.get("reminders")
    if not isinstance(raw_rules, list):
        raise ConfigurationError("reminders must be a list")
    rules = tuple(_parse_rule(raw_rule) for raw_rule in raw_rules)
    identifiers = [rule.reminder_id for rule in rules]
    if len(identifiers) != len(set(identifiers)):
        raise ConfigurationError("reminder ids must be unique")
    return ReminderConfig(event_key, schema_version, rules, max_due)


def _parse_rule(payload: Any) -> ReminderRule:
    if not isinstance(payload, dict):
        raise ConfigurationError("each reminder must be an object")
    reminder_id = _required_string(payload, "id")
    if not reminder_id.replace("-", "").replace("_", "").isalnum() or len(reminder_id) > 128:
        raise ConfigurationError("reminder id must be alphanumeric, hyphen, or underscore")
    title = _required_string(payload, "title", max_length=200)
    text = _required_string(payload, "text", max_length=4000)
    timezone = _timezone(_required_string(payload, "timezone"))
    kind = _required_string(payload, "kind")
    if kind == "weekly":
        weekdays = _weekdays(payload.get("weekdays"))
        times = _times(payload.get("times"))
        return WeeklyRule(reminder_id, title, text, timezone, weekdays, times)
    if kind == "interval":
        anchor_at = _aware_datetime(_required_string(payload, "anchor_at"))
        every_minutes = payload.get("every_minutes")
        if not isinstance(every_minutes, int) or not 1 <= every_minutes <= 10080:
            raise ConfigurationError("every_minutes must be between 1 and 10080")
        return IntervalRule(reminder_id, title, text, timezone, anchor_at, every_minutes)
    raise ConfigurationError("reminder kind must be weekly or interval")


def _required_string(payload: dict[str, Any], key: str, max_length: int = 128) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise ConfigurationError(f"{key} must be a non-empty string up to {max_length} characters")
    return value


def _timezone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ConfigurationError(f"invalid timezone: {value}") from exc


def _weekdays(value: Any) -> tuple[int, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigurationError("weekdays must be a non-empty list")
    parsed = []
    for item in value:
        if not isinstance(item, str) or item.lower() not in WEEKDAYS:
            raise ConfigurationError("weekdays must use English weekday names")
        parsed.append(WEEKDAYS[item.lower()])
    return tuple(sorted(set(parsed)))


def _times(value: Any) -> tuple[time, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigurationError("times must be a non-empty list")
    parsed: list[time] = []
    for item in value:
        if not isinstance(item, str):
            raise ConfigurationError("times must contain HH:MM strings")
        try:
            parsed.append(time.fromisoformat(item))
        except ValueError as exc:
            raise ConfigurationError(f"invalid time: {item}") from exc
    if any(item.second or item.microsecond for item in parsed):
        raise ConfigurationError("times must use HH:MM precision")
    return tuple(sorted(set(parsed)))


def _aware_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ConfigurationError("anchor_at must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ConfigurationError("anchor_at must include an offset")
    return parsed


def _valid_event_key(value: str) -> bool:
    parts = value.split(".")
    return len(parts) >= 3 and all(part.replace("_", "").isalnum() and part for part in parts)
