from __future__ import annotations

import re
from typing import Any

_DELAY_PATTERN = re.compile(r"^(?P<value>\d{1,7})\s*(?P<unit>[A-Za-z]*)$")

_UNIT_SECONDS = {
    "s": 1,
    "sec": 1,
    "secs": 1,
    "second": 1,
    "seconds": 1,
    "m": 60,
    "min": 60,
    "mins": 60,
    "minute": 60,
    "minutes": 60,
    "h": 3600,
    "hr": 3600,
    "hrs": 3600,
    "hour": 3600,
    "hours": 3600,
}

#: A bare number is read as minutes: ``5`` and ``5m`` mean the same thing.
_BARE_NUMBER_SECONDS = 60


class DelayError(ValueError):
    pass


def parse_delay(value: Any, *, max_seconds: int) -> int:
    """Return the delay in seconds for ``5m``/``10min``/``90s``/``1h``/``5``."""
    if isinstance(value, bool):
        raise DelayError("delay must be a duration like 5m, 10min, 90s or a number of minutes")
    if isinstance(value, (int, float)):
        seconds = int(value * _BARE_NUMBER_SECONDS)
    elif isinstance(value, str):
        match = _DELAY_PATTERN.fullmatch(value.strip())
        if match is None:
            raise DelayError("delay must look like 5m, 10min, 90s or 1h")
        unit = match.group("unit").lower()
        if unit and unit not in _UNIT_SECONDS:
            raise DelayError(f"unsupported delay unit: {match.group('unit')}")
        seconds = int(match.group("value")) * _UNIT_SECONDS.get(unit, _BARE_NUMBER_SECONDS)
    else:
        raise DelayError("delay must be a duration like 5m, 10min, 90s or a number of minutes")
    if seconds < 0:
        raise DelayError("delay must not be negative")
    if seconds > max_seconds:
        raise DelayError(f"delay must not exceed {max_seconds} seconds")
    return seconds


def humanize_delay(seconds: int) -> str:
    if seconds <= 0:
        return "立即"
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours} 小时")
    if minutes:
        parts.append(f"{minutes} 分钟")
    if secs:
        parts.append(f"{secs} 秒")
    return " ".join(parts)
