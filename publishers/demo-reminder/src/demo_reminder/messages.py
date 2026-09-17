from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from .models import ReminderRequest
from .schedule import humanize_delay


def render(request: ReminderRequest, *, event_key: str, timezone: ZoneInfo) -> dict[str, Any]:
    return {
        "title": request.title,
        "text": f"{request.text}\n{_timing(request, timezone)}",
        "data": {
            "request_id": request.request_id,
            "delay_seconds": request.delay_seconds,
            "notify_at": to_utc_iso(request.notify_at),
        },
        "template_key": f"{event_key}.default",
        "template_version": 1,
    }


def _timing(request: ReminderRequest, timezone: ZoneInfo) -> str:
    local = request.notify_at.astimezone(timezone)
    stamp = local.strftime("%m-%d %H:%M")
    offset = _offset_label(local)
    if request.delay_seconds <= 0:
        return f"提醒时间：{stamp}（{offset}，立即触发）"
    return f"提醒时间：{stamp}（{offset}，{humanize_delay(request.delay_seconds)}后）"


def _offset_label(value: datetime) -> str:
    offset = value.utcoffset()
    if offset is None:
        return "UTC"
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


def to_utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
