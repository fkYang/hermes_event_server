from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from scheduled_reminder.client import EventServerClient, PublishError
from scheduled_reminder.config import PublisherSettings, load_config
from scheduled_reminder.scheduling import due_between

logger = logging.getLogger("scheduled_reminder")


class ReminderPublisher:
    def __init__(self, settings: PublisherSettings, client: EventServerClient) -> None:
        self.settings = settings
        self.client = client
        self.last_checked_at: datetime | None = None

    def run_once(self, now: datetime | None = None) -> int:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        config = load_config(self.settings.config_file)
        if self.last_checked_at is None:
            self.last_checked_at = current
            return 0
        due = sorted(
            occurrence
            for rule in config.rules
            for occurrence in due_between(rule, self.last_checked_at, current)
        )
        if len(due) > config.max_due_per_tick:
            raise RuntimeError("too many due reminders; refusing an unbounded catch-up")
        for occurrence in due:
            self.client.publish(config, occurrence)
        self.last_checked_at = current
        return len(due)

    def serve(self) -> None:
        while True:
            try:
                published = self.run_once()
                if published:
                    logger.info("published scheduled reminders", extra={"count": published})
            except (OSError, ValueError, PublishError) as exc:
                logger.error("scheduled reminder cycle failed: %s", exc)
            time.sleep(self.settings.tick_seconds)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = PublisherSettings.from_environment()
    ReminderPublisher(settings, EventServerClient(settings)).serve()


if __name__ == "__main__":
    main()
