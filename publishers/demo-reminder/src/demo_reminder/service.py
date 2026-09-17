from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import uuid4

from .client import PublishResult
from .config import PublisherSettings
from .models import ReminderRequest
from .schedule import parse_delay

DEDUPE_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
DEFAULT_TITLE = "演示提醒"
MAX_TEXT_LENGTH = 500
MAX_TITLE_LENGTH = 100


class ReminderInputError(ValueError):
    pass


class ReminderPublisher(Protocol):
    def publish(self, request: ReminderRequest) -> PublishResult: ...


class ReminderService:
    """Turns a request parameter (``5m``, ``10m``, ``at``) into one publication."""

    def __init__(
        self,
        settings: PublisherSettings,
        client: ReminderPublisher,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        self._clock = clock or (lambda: datetime.now(UTC))

    def submit(
        self,
        *,
        text: Any = None,
        title: Any = None,
        delay: Any = None,
        delay_seconds: Any = None,
        at: Any = None,
        dedupe_key: Any = None,
    ) -> PublishResult:
        requested_at = self._clock().astimezone(UTC)
        notify_at, seconds = self._resolve_timing(
            requested_at, delay=delay, delay_seconds=delay_seconds, at=at
        )
        key = _clean_dedupe_key(dedupe_key) if dedupe_key else uuid4().hex
        request = ReminderRequest(
            request_id=key,
            dedupe_key=key,
            title=_clean_title(title),
            text=_clean_text(text),
            delay_seconds=seconds,
            requested_at=requested_at,
            notify_at=notify_at,
        )
        return self._client.publish(request)

    def _resolve_timing(
        self,
        requested_at: datetime,
        *,
        delay: Any,
        delay_seconds: Any,
        at: Any,
    ) -> tuple[datetime, int]:
        provided = [
            name
            for name, value in (("delay", delay), ("delay_seconds", delay_seconds), ("at", at))
            if value is not None
        ]
        if len(provided) > 1:
            raise ReminderInputError(
                f"provide only one of {', '.join(provided)}: they describe the same moment"
            )
        if at is not None:
            notify_at = _parse_absolute(at)
            seconds = max(0, int((notify_at - requested_at).total_seconds()))
        elif delay is None and delay_seconds is None:
            # The configured default is already expressed in seconds.
            seconds = self._settings.default_delay_seconds
            notify_at = requested_at + timedelta(seconds=seconds)
        else:
            seconds = (
                _parse_seconds(delay_seconds)
                if delay_seconds is not None
                else parse_delay(delay, max_seconds=self._settings.max_delay_seconds)
            )
            notify_at = requested_at + timedelta(seconds=seconds)
        if seconds > self._settings.max_delay_seconds:
            raise ReminderInputError(
                f"reminder must not be scheduled more than "
                f"{self._settings.max_delay_seconds} seconds ahead"
            )
        return notify_at, seconds


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        raise ReminderInputError("text must be a string")
    text = value.strip()
    if not text:
        raise ReminderInputError("text must not be empty")
    if len(text) > MAX_TEXT_LENGTH:
        raise ReminderInputError(f"text must not exceed {MAX_TEXT_LENGTH} characters")
    return text


def _clean_title(value: Any) -> str:
    if value is None:
        return DEFAULT_TITLE
    if not isinstance(value, str):
        raise ReminderInputError("title must be a string")
    title = value.strip()
    if not title:
        return DEFAULT_TITLE
    if len(title) > MAX_TITLE_LENGTH:
        raise ReminderInputError(f"title must not exceed {MAX_TITLE_LENGTH} characters")
    return title


def _clean_dedupe_key(value: Any) -> str:
    if not isinstance(value, str) or DEDUPE_PATTERN.fullmatch(value) is None:
        raise ReminderInputError("dedupe_key must be 1-128 characters of [A-Za-z0-9_.:-]")
    return value


def _parse_seconds(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReminderInputError("delay_seconds must be a number of seconds")
    if value < 0:
        raise ReminderInputError("delay_seconds must not be negative")
    return int(value)


def _parse_absolute(value: Any) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ReminderInputError("at must be an ISO-8601 timestamp with an offset") from exc
    if not isinstance(value, datetime):
        raise ReminderInputError("at must be an ISO-8601 timestamp with an offset")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ReminderInputError("at must include a timezone offset, for example +08:00")
    return value.astimezone(UTC)
