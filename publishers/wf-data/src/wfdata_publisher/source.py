from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import PublisherSettings

SECTION_EVENT_KEYS: dict[str, str] = {
    "current": "warframe.cetus.bounty_current",
    "next": "warframe.cetus.bounty_next",
}
TENT_TAGS = ("tentA", "tentB", "tentC")
KONZU_TIER = 5
USER_AGENT = "AutoQQ-WfDataPublisher/0.1"


class SourceError(RuntimeError):
    pass


def to_utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class JobEntry:
    key: str
    name_zh: str
    source: str
    tier: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"key": self.key, "name_zh": self.name_zh, "source": self.source, "tier": self.tier}


@dataclass(frozen=True)
class BountyWindow:
    section: str
    event_key: str
    activation: datetime
    expiry: datetime
    match_keys: tuple[str, ...]
    jobs: tuple[JobEntry, ...]
    konzu_found: bool | None = None
    """True when the konzu block was scanned, None when the event ignores konzu."""

    @property
    def dedupe_key(self) -> str:
        return to_utc_iso(self.activation)

    def labels(self) -> tuple[str, ...]:
        names: dict[str, str] = {}
        for job in self.jobs:
            names.setdefault(job.key, job.name_zh)
        return tuple(names.get(key, key) for key in self.match_keys)


def parse_window(payload: dict[str, Any], section: str) -> BountyWindow | None:
    """Extract one rotation window, or None when it is absent or unusable.

    The parser never logs: it is called on every poll, so callers decide what is
    worth reporting. The `current` event scans the three tent slots plus the
    tier-5 entry of `konzu.normal`; the `next` event scans only its tent slots.
    Steel path, Narmer and the lower normal tiers are never scanned.
    """
    raw = payload.get(section)
    if not isinstance(raw, dict):
        return None
    activation = _timestamp(raw.get("activation"))
    expiry = _timestamp(raw.get("expiry"))
    if activation is None or expiry is None:
        return None
    jobs, konzu_found = _collect_jobs(payload, section, activation)
    if not jobs:
        return None
    match_keys = tuple(sorted({job.key for job in jobs}))
    return BountyWindow(
        section=section,
        event_key=SECTION_EVENT_KEYS[section],
        activation=activation,
        expiry=expiry,
        match_keys=match_keys,
        jobs=tuple(jobs),
        konzu_found=konzu_found,
    )


def _collect_jobs(
    payload: dict[str, Any], section: str, activation: datetime
) -> tuple[list[JobEntry], bool | None]:
    """Return the scanned jobs and whether konzu participated in the scan."""
    jobs = _tent_jobs(payload[section])
    if section != "current":
        return jobs, None
    block = _konzu_block(payload, section, activation)
    if block is None:
        return jobs, False
    return jobs + _konzu_jobs(block), True


def _tent_jobs(section_data: dict[str, Any]) -> list[JobEntry]:
    jobs: list[JobEntry] = []
    for tag in TENT_TAGS:
        block = section_data.get(tag)
        if not isinstance(block, dict):
            continue
        for entry in _as_list(block.get("jobs")):
            job_key = entry.get("id")
            if not isinstance(job_key, str) or not job_key:
                continue
            jobs.append(JobEntry(job_key, _label(entry.get("nameZh"), job_key), tag))
    return jobs


def _konzu_jobs(block: dict[str, Any]) -> list[JobEntry]:
    jobs: list[JobEntry] = []
    for entry in _as_list(block.get("normal")):
        tier = entry.get("tier")
        if tier != KONZU_TIER:
            continue
        job_key = entry.get("jobId")
        if not isinstance(job_key, str) or not job_key:
            continue
        jobs.append(
            JobEntry(
                job_key,
                _label(entry.get("nameZh"), job_key),
                f"konzu.normal.tier{tier}",
                tier,
            )
        )
    return jobs


def _konzu_block(
    payload: dict[str, Any], section: str, activation: datetime
) -> dict[str, Any] | None:
    """Return the konzu block that belongs to this window.

    The observed payload carries `konzu` next to `current`, so a block is
    accepted only when its own activation matches the window being parsed. That
    keeps the upcoming window from borrowing the current window's bounties.
    """
    candidates: list[Any] = []
    section_data = payload.get(section)
    if isinstance(section_data, dict):
        candidates.append(section_data.get("konzu"))
    candidates.append(payload.get("konzu"))
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if _timestamp(candidate.get("activation")) == activation:
            return candidate
    return None


def _as_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _label(value: Any, fallback: str) -> str:
    if isinstance(value, str) and value:
        return value
    return fallback


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC).replace(microsecond=0)


class WfDataSource:
    def __init__(self, settings: PublisherSettings) -> None:
        self._settings = settings

    def fetch(self) -> dict[str, Any]:
        request = Request(
            self._settings.wf_data_url,
            method="GET",
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=self._settings.request_timeout_seconds) as response:
                if response.status != 200:
                    raise SourceError(f"wf-data returned HTTP {response.status}")
                body = response.read(self._settings.max_response_bytes + 1)
        except HTTPError as exc:
            raise SourceError(f"wf-data returned HTTP {exc.code}") from exc
        except URLError as exc:
            raise SourceError("wf-data is unreachable") from exc
        if len(body) > self._settings.max_response_bytes:
            raise SourceError("wf-data response exceeds the configured size limit")
        try:
            payload = json.loads(body)
        except ValueError as exc:
            raise SourceError("wf-data response is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise SourceError("wf-data response must be a JSON object")
        return payload
