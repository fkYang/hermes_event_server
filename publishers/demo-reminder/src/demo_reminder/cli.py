"""One-off demo helper: publish a delayed reminder without running the ingress."""

from __future__ import annotations

import argparse
import json
import sys

from .client import EventServerClient, PublishError
from .config import ConfigurationError, PublisherSettings
from .messages import to_utc_iso
from .schedule import DelayError
from .service import ReminderInputError, ReminderService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="demo_reminder.cli",
        description="Publish one demo reminder through EventServer",
    )
    parser.add_argument("--text", required=True, help="提醒内容")
    parser.add_argument("--title", default=None, help="标题，默认「演示提醒」")
    parser.add_argument("--delay", default=None, help="延迟，例如 5m / 10min / 90s")
    parser.add_argument("--at", default=None, help="绝对时间（ISO-8601 带时区）")
    parser.add_argument("--dedupe-key", default=None, help="重复提交同一个 key 只发布一次")
    args = parser.parse_args(argv)
    try:
        settings = PublisherSettings.from_environment()
        service = ReminderService(settings, EventServerClient(settings))
        result = service.submit(
            text=args.text,
            title=args.title,
            delay=args.delay,
            at=args.at,
            dedupe_key=args.dedupe_key,
        )
    except (ConfigurationError, ReminderInputError, DelayError, PublishError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "event_id": result.event_id,
                "created": result.created,
                "deliveries_created": result.deliveries_created,
                "notify_at": to_utc_iso(result.notify_at) if result.notify_at else None,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
