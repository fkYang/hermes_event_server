import json
import logging
import re
from datetime import UTC, datetime

from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "eventserver_http_requests_total",
    "HTTP requests handled by route template",
    ("method", "route", "status"),
)
REQUEST_DURATION = Histogram(
    "eventserver_http_request_duration_seconds",
    "HTTP request duration by route template",
    ("method", "route"),
)

_BEARER = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+")
_SECRET_FIELD = re.compile(
    r'(?i)("?(?:password|token|secret|lease_token|pairing_code)"?\s*[:=]\s*")([^"\s]+)'
)


def redact_text(value: str) -> str:
    value = _BEARER.sub(r"\1[REDACTED]", value)
    return _SECRET_FIELD.sub(r"\1[REDACTED]", value)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
        }
        for key in ("request_id", "method", "route", "status", "duration_ms"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("eventserver")
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False
