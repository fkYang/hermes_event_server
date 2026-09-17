from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .source import BountyWindow, to_utc_iso

TITLES = {"current": "Cetus 赏金轮换", "next": "Cetus 赏金预告"}


def render(window: BountyWindow, *, timezone: ZoneInfo, lead_seconds: int) -> dict[str, Any]:
    labels = "、".join(window.labels())
    start = _local(window.activation, timezone)
    offset = _offset_label(window.activation, timezone)
    if window.section == "current":
        headline = f"当前轮次包含：{labels}"
        timing = f"时段：{start} → {_local(window.expiry, timezone)}（{offset}）"
    else:
        headline = f"下一轮包含：{labels}"
        timing = f"开始：{start}，约 {lead_seconds // 60} 分钟后（{offset}）"
    return {
        "title": TITLES[window.section],
        "text": f"{headline}\n{timing}",
        "data": {
            "window": window.section,
            "activation": to_utc_iso(window.activation),
            "expiry": to_utc_iso(window.expiry),
        },
        "template_key": f"{window.event_key}.default",
        "template_version": 1,
    }


def _local(value: datetime, timezone: ZoneInfo) -> str:
    return value.astimezone(timezone).strftime("%m-%d %H:%M")


def _offset_label(value: datetime, timezone: ZoneInfo) -> str:
    offset = value.astimezone(timezone).utcoffset()
    if offset is None:
        return str(timezone)
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"
