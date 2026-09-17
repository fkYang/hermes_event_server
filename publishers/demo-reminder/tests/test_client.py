import json
from datetime import UTC, datetime
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from demo_reminder import client as client_module
from demo_reminder.client import EventServerClient, PublishError, build_payload
from demo_reminder.config import PublisherSettings
from demo_reminder.models import ReminderRequest

SETTINGS = PublisherSettings(
    event_server_url="http://eventserver:8080",
    publisher_token="t" * 32,
    ingress_token="i" * 16,
)
REQUEST = ReminderRequest(
    request_id="req-1",
    dedupe_key="req-1",
    title="演示提醒",
    text="5 分钟后提醒我一下",
    delay_seconds=300,
    requested_at=datetime(2026, 9, 17, 12, 0, tzinfo=UTC),
    notify_at=datetime(2026, 9, 17, 12, 5, tzinfo=UTC),
)


class FakeResponse:
    def __init__(self, body: bytes, status: int = 200) -> None:
        self._buffer = BytesIO(body)
        self.status = status

    def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc_info) -> None:
        return None


def test_payload_matches_the_registered_catalog_contract() -> None:
    payload = build_payload(REQUEST, settings=SETTINGS)
    assert payload["event_key"] == "demo.reminder.scheduled"
    assert payload["schema_version"] == 1
    assert payload["dedupe_key"] == "req-1"
    assert payload["occurred_at"] == "2026-09-17T12:00:00Z"
    assert payload["notify_at"] == "2026-09-17T12:05:00Z"
    assert payload["subject"] == {"type": "reminder", "id": "req-1"}
    assert set(payload["data"]) == {"request_id", "delay_seconds", "notify_at"}
    assert payload["data"]["delay_seconds"] == 300
    assert payload["messages"]["default"]["title"] == "演示提醒"
    assert "20:05" in payload["messages"]["default"]["text"]


def test_the_catalog_payload_schema_accepts_the_published_data() -> None:
    payload = build_payload(REQUEST, settings=SETTINGS)
    schema = _catalog_schema()
    assert set(payload["data"]) == set(schema["properties"])
    for field in schema["required"]:
        assert field in payload["data"]


def test_publish_parses_the_eventserver_response(monkeypatch) -> None:
    body = json.dumps(
        {
            "event_id": "evt-9",
            "created": True,
            "deliveries_created": 1,
            "notify_at": "2026-09-17T12:05:00Z",
        }
    ).encode("utf-8")
    captured: list[Request] = []

    def fake_urlopen(request, timeout):  # noqa: ANN001, ANN202
        captured.append(request)
        return FakeResponse(body)

    monkeypatch.setattr(client_module, "urlopen", fake_urlopen)
    result = EventServerClient(SETTINGS).publish(REQUEST)
    assert result.event_id == "evt-9"
    assert result.created is True
    assert result.deliveries_created == 1
    assert result.notify_at == datetime(2026, 9, 17, 12, 5, tzinfo=UTC)
    sent = json.loads(captured[0].data.decode("utf-8"))
    assert sent["notify_at"] == "2026-09-17T12:05:00Z"
    assert captured[0].headers["Authorization"] == "Bearer " + "t" * 32


@pytest.mark.parametrize(
    "failure",
    [
        HTTPError("http://eventserver:8080", 422, "unprocessable", {}, None),
        URLError("unreachable"),
    ],
)
def test_transport_failures_are_mapped_to_publish_errors(monkeypatch, failure) -> None:
    def fake_urlopen(request, timeout):  # noqa: ANN001, ANN202
        raise failure

    monkeypatch.setattr(client_module, "urlopen", fake_urlopen)
    with pytest.raises(PublishError):
        EventServerClient(SETTINGS).publish(REQUEST)


@pytest.mark.parametrize("body", [b"{}", b"not json", b'{"event_id": "evt", "created": true}'])
def test_malformed_responses_are_rejected(monkeypatch, body: bytes) -> None:
    monkeypatch.setattr(client_module, "urlopen", lambda request, timeout: FakeResponse(body))
    if body == b'{"event_id": "evt", "created": true}':
        result = EventServerClient(SETTINGS).publish(REQUEST)
        assert result.deliveries_created == 0
        assert result.notify_at is None
    else:
        with pytest.raises(PublishError):
            EventServerClient(SETTINGS).publish(REQUEST)


def _catalog_schema() -> dict:
    from pathlib import Path

    path = Path(__file__).parents[1] / "config" / "event-catalog.json"
    return json.loads(path.read_text(encoding="utf-8"))["payload_schema"]
