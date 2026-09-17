"""Subscription match-key helpers.

Match keys are opaque, bounded strings declared by the event catalog. The core
never interprets their meaning: it only validates their shape and computes set
intersections between an event's keys and a subscription's watched keys.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

MATCH_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
MAX_MATCH_KEYS = 32


class MatchKeyError(ValueError):
    pass


def normalize_match_keys(values: Iterable[str] | None) -> list[str]:
    """Return a sorted, de-duplicated list of valid match keys."""
    if values is None:
        return []
    normalized: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not MATCH_KEY_PATTERN.match(value):
            raise MatchKeyError(f"invalid match key: {value!r}")
        normalized.add(value)
    if len(normalized) > MAX_MATCH_KEYS:
        raise MatchKeyError(f"at most {MAX_MATCH_KEYS} match keys are allowed")
    return sorted(normalized)


def allowed_match_keys(options: Iterable[Mapping[str, Any]] | None) -> set[str]:
    allowed: set[str] = set()
    for option in options or ():
        key = option.get("key") if isinstance(option, Mapping) else None
        if isinstance(key, str) and key:
            allowed.add(key)
    return allowed


def ensure_match_keys_allowed(values: Iterable[str], allowed: set[str]) -> None:
    unknown = [value for value in values if value not in allowed]
    if unknown:
        raise MatchKeyError(f"match key is not available for this event: {unknown[0]}")


def recipient_matches(
    *, field: str | None, event_data: Mapping[str, Any], subscribed: Iterable[str] | None
) -> bool:
    """Return whether an event reaches a subscription.

    An event without a declared match dimension reaches every subscriber. A
    subscription without watched keys follows the whole event. When both sides
    exist they must intersect, and an event that declares a dimension but does
    not carry it fails closed.
    """
    if not field:
        return True
    watched = set(subscribed or ())
    if not watched:
        return True
    present = event_data.get(field)
    if not isinstance(present, list):
        return False
    return bool({str(item) for item in present} & watched)
