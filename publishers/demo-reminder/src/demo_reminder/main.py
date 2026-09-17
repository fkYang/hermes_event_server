from __future__ import annotations

import logging

from .client import EventServerClient
from .config import PublisherSettings
from .server import ReminderServer
from .service import ReminderService

logger = logging.getLogger("demo_reminder")


def build_server(
    settings: PublisherSettings, service: ReminderService | None = None
) -> ReminderServer:
    return ReminderServer(
        (settings.http_host, settings.http_port),
        settings=settings,
        service=service or ReminderService(settings, EventServerClient(settings)),
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = PublisherSettings.from_environment()
    if not settings.ingress_token:
        raise SystemExit("INGRESS_TOKEN is required: the demo ingress must not be anonymous")
    server = build_server(settings)
    logger.info(
        "demo reminder ingress listening on %s:%s (default delay %ss, max %ss)",
        settings.http_host,
        settings.http_port,
        settings.default_delay_seconds,
        settings.max_delay_seconds,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("demo reminder ingress stopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
