import json
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from demo_reminder.client import PublishError, PublishResult
from demo_reminder.config import PublisherSettings
from demo_reminder.main import build_server
from demo_reminder.models import ReminderRequest
from demo_reminder.service import ReminderInputError, ReminderService

TOKEN = "ingress-token-0123456789"
NOW = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
SETTINGS = PublisherSettings(
    event_server_url="http://eventserver:8080",
    publisher_token="t" * 32,
    ingress_token=TOKEN,
    http_host="127.0.0.1",
    http_port=0,
)


class FakePublisher:
    def __init__(self) -> None:
        self.requests: list[ReminderRequest] = []

    def publish(self, request: ReminderRequest) -> PublishResult:
        self.requests.append(request)
        return PublishResult(
            event_id="evt-1", created=True, deliveries_created=3, notify_at=request.notify_at
        )


class FakeService:
    """Used to inject publish failures the real service cannot produce itself."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def submit(self, **kwargs):  # noqa: ANN003, ARG002
        raise self.error


@contextmanager
def serve(service):
    server = build_server(SETTINGS, service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def call(base: str, path: str, *, body=None, token: str | None = TOKEN, raw: bytes | None = None):
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode("utf-8"))
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(f"{base}{path}", data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


@pytest.fixture
def ingress():
    publisher = FakePublisher()
    service = ReminderService(SETTINGS, publisher, clock=lambda: NOW)
    with serve(service) as base:
        yield base, publisher


def test_health_does_not_need_a_token(ingress) -> None:
    base, _ = ingress
    status, payload = call(base, "/health", token=None)
    assert status == 200
    assert payload["status"] == "ok"


def test_the_usage_document_is_served(ingress) -> None:
    base, _ = ingress
    status, payload = call(base, "/v1/reminders", token=None)
    assert status == 200
    assert payload["usage"]["method"] == "POST"


def test_a_reminder_is_published_with_the_requested_delay(ingress) -> None:
    base, publisher = ingress
    status, payload = call(base, "/v1/reminders", body={"delay": "5m", "text": "喝水"})
    assert status == 200
    assert payload == {
        "event_id": "evt-1",
        "created": True,
        "deliveries_created": 3,
        "notify_at": "2026-09-17T12:05:00Z",
    }
    request = publisher.requests[0]
    assert request.delay_seconds == 300
    assert request.text == "喝水"


def test_an_absolute_time_can_be_used_instead_of_a_delay(ingress) -> None:
    base, publisher = ingress
    status, payload = call(
        base, "/v1/reminders", body={"at": "2026-09-17T20:30:00+08:00", "text": "看比赛"}
    )
    assert status == 200
    assert payload["notify_at"] == "2026-09-17T12:30:00Z"
    assert publisher.requests[0].delay_seconds == 1800


@pytest.mark.parametrize("token", [None, "wrong-token"])
def test_the_ingress_requires_its_bearer_token(ingress, token) -> None:
    base, publisher = ingress
    status, payload = call(base, "/v1/reminders", body={"text": "喝水"}, token=token)
    assert status == 401
    assert publisher.requests == []
    assert "error" in payload


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"delay": "5m"}, "text must be a string"),
        ({"text": "喝水", "delay": "nonsense"}, "delay must look like"),
        (
            {"text": "喝水", "delay": "5m", "at": "2026-09-17T20:30:00+08:00"},
            "only one of",
        ),
        ({"text": "喝水", "unknown": 1}, "unsupported fields"),
    ],
)
def test_invalid_requests_are_rejected_with_400(ingress, body, message: str) -> None:
    base, publisher = ingress
    status, payload = call(base, "/v1/reminders", body=body)
    assert status == 400
    assert message in payload["error"]
    assert publisher.requests == []


def test_a_malformed_body_is_rejected(ingress) -> None:
    base, _ = ingress
    status, payload = call(base, "/v1/reminders", raw=b"{not json")
    assert status == 400
    assert "JSON" in payload["error"]


def test_unknown_paths_are_not_found(ingress) -> None:
    base, _ = ingress
    assert call(base, "/v1/other")[0] == 404
    assert call(base, "/v1/other", body={"text": "x"})[0] == 404


def test_a_service_input_error_is_reported_as_400() -> None:
    with serve(FakeService(ReminderInputError("text must not be empty"))) as base:
        status, payload = call(base, "/v1/reminders", body={"text": "x"})
    assert status == 400
    assert payload == {"error": "text must not be empty"}


def test_an_eventserver_failure_is_reported_as_502() -> None:
    with serve(FakeService(PublishError("EventServer returned HTTP 422"))) as base:
        status, payload = call(base, "/v1/reminders", body={"text": "x"})
    assert status == 502
    assert "422" in payload["error"]
