from __future__ import annotations

import hmac
import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from . import __version__
from .client import PublishError, PublishResult
from .config import PublisherSettings
from .messages import to_utc_iso
from .schedule import DelayError
from .service import ReminderInputError, ReminderService

logger = logging.getLogger("demo_reminder.ingress")

REMINDER_PATH = "/v1/reminders"
ALLOWED_FIELDS = ("text", "title", "delay", "delay_seconds", "at", "dedupe_key")

USAGE: dict[str, Any] = {
    "service": "autoqq-demo-reminder",
    "version": __version__,
    "usage": {
        "method": "POST",
        "path": REMINDER_PATH,
        "headers": {"Authorization": "Bearer <INGRESS_TOKEN>"},
        "body": {
            "text": "提醒内容（必填）",
            "title": "标题，默认「演示提醒」",
            "delay": "延迟，例如 5m / 10min / 90s / 1h，纯数字按分钟解释",
            "at": "绝对时间（ISO-8601 带时区），与 delay 互斥",
            "dedupe_key": "可选；重复提交同一个 key 只会发布一次",
        },
        "example": {"delay": "5m", "text": "5 分钟后提醒我一下"},
    },
}


class ReminderServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        address: tuple[str, int],
        *,
        settings: PublisherSettings,
        service: ReminderService,
    ) -> None:
        self.settings = settings
        self.service = service
        super().__init__(address, _ReminderHandler)


class _ReminderHandler(BaseHTTPRequestHandler):
    server_version = f"AutoQQ-DemoReminder/{__version__}"
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler naming
        path = urlparse(self.path).path
        if path == "/health":
            self._respond(HTTPStatus.OK, {"status": "ok", "version": __version__})
        elif path in ("/", REMINDER_PATH):
            self._respond(HTTPStatus.OK, USAGE)
        else:
            self._respond(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler naming
        if urlparse(self.path).path != REMINDER_PATH:
            self._respond(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        settings: PublisherSettings = self.server.settings  # type: ignore[attr-defined]
        if not self._authorized(settings):
            self._respond(HTTPStatus.UNAUTHORIZED, {"error": "missing or invalid ingress token"})
            return
        raw = self._read_body(settings.max_body_bytes)
        if raw is None:
            return
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._respond(HTTPStatus.BAD_REQUEST, {"error": "body must be a JSON object"})
            return
        if not isinstance(payload, dict):
            self._respond(HTTPStatus.BAD_REQUEST, {"error": "body must be a JSON object"})
            return
        unknown = sorted(set(payload) - set(ALLOWED_FIELDS))
        if unknown:
            self._respond(
                HTTPStatus.BAD_REQUEST, {"error": f"unsupported fields: {', '.join(unknown)}"}
            )
            return
        try:
            result = self.server.service.submit(  # type: ignore[attr-defined]
                **{field: payload[field] for field in ALLOWED_FIELDS if field in payload}
            )
        except (ReminderInputError, DelayError) as exc:
            self._respond(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except PublishError as exc:
            self._respond(HTTPStatus.BAD_GATEWAY, {"error": str(exc)})
        else:
            logger.info(
                "accepted reminder event_id=%s created=%s deliveries_created=%s notify_at=%s",
                result.event_id,
                result.created,
                result.deliveries_created,
                to_utc_iso(result.notify_at) if result.notify_at else None,
            )
            self._respond(HTTPStatus.OK, _serialize(result))

    def _authorized(self, settings: PublisherSettings) -> bool:
        expected = settings.ingress_token
        if not expected:
            return False
        header = self.headers.get("Authorization", "")
        prefix = "Bearer "
        if not header.startswith(prefix):
            return False
        return hmac.compare_digest(header[len(prefix) :].strip(), expected)

    def _read_body(self, max_body_bytes: int) -> bytes | None:
        raw_length = self.headers.get("Content-Length", "")
        try:
            length = int(raw_length)
        except ValueError:
            self._respond(HTTPStatus.LENGTH_REQUIRED, {"error": "Content-Length is required"})
            return None
        if length > max_body_bytes:
            self._respond(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "body is too large"})
            return None
        return self.rfile.read(length)

    def _respond(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
        logger.debug("%s %s", self.address_string(), format % args)


def _serialize(result: PublishResult) -> dict[str, Any]:
    return {
        "event_id": result.event_id,
        "created": result.created,
        "deliveries_created": result.deliveries_created,
        "notify_at": to_utc_iso(result.notify_at) if result.notify_at else None,
    }
