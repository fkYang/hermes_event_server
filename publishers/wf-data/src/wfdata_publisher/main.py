from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta

from .client import EventServerClient, PublishError
from .config import PublisherSettings
from .source import BountyWindow, SourceError, WfDataSource, parse_window

logger = logging.getLogger("wfdata_publisher")

SECTIONS = ("current", "next")


class BountyPublisher:
    """Publishes one event per rotation window and lets EventServer fan out.

    The publisher never decides who is notified: it reports the tasks of each
    window and EventServer intersects them with every subscription's watched
    keys. Repeated polls of the same activation are suppressed locally, and a
    restart simply republishes once so the server-side dedupe key absorbs it.
    """

    def __init__(self, settings: PublisherSettings, client, source: WfDataSource) -> None:
        self._settings = settings
        self._client = client
        self._source = source
        self._published: dict[str, datetime] = {}
        self._missing: set[str] = set()

    def run_once(self, now: datetime | None = None) -> int:
        observed_at = (now or datetime.now(UTC)).astimezone(UTC)
        payload = self._source.fetch()
        published = 0
        for section in SECTIONS:
            window = parse_window(payload, section)
            if window is None:
                self._note_missing(section)
                continue
            if section in self._missing:
                self._missing.discard(section)
                logger.info("%s bounty window is available again", section)
            if self._published.get(section) == window.activation:
                continue
            self._client.publish(window, observed_at=observed_at, notify_at=self.notify_at(window))
            self._published[section] = window.activation
            published += 1
            self._log_published(window)
        return published

    def _note_missing(self, section: str) -> None:
        """The upcoming window is absent most of the time; only `current` matters."""
        if section == "current" and section not in self._missing:
            self._missing.add(section)
            logger.warning("the current bounty window is missing from the source payload")

    @staticmethod
    def _log_published(window: BountyWindow) -> None:
        """One informational line per window, plus one warning when konzu is absent."""
        if window.konzu_found is False:
            logger.warning(
                "%s was published without a konzu block; only tent slots were scanned",
                window.event_key,
            )
        scope = "tent-only" if window.konzu_found is None else "tent+konzu"
        logger.info(
            "published %s with dedupe key %s (%s, %d match keys)",
            window.event_key,
            window.dedupe_key,
            scope,
            len(window.match_keys),
        )

    def notify_at(self, window: BountyWindow) -> datetime | None:
        """Deliver the upcoming window `LEAD_SECONDS` before it activates."""
        if window.section != "next":
            return None
        return window.activation - timedelta(seconds=self._settings.lead_seconds)

    def serve(self) -> None:
        while True:
            try:
                self.run_once()
            except (OSError, ValueError, SourceError, PublishError) as exc:
                logger.error("cetus bounty cycle failed: %s", exc)
            time.sleep(self._settings.poll_seconds)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = PublisherSettings.from_environment()
    BountyPublisher(settings, EventServerClient(settings), WfDataSource(settings)).serve()


if __name__ == "__main__":
    main()
