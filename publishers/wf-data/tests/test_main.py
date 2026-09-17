import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from wfdata_publisher.config import PublisherSettings
from wfdata_publisher.main import BountyPublisher

FIXTURE = Path(__file__).parent / "fixtures" / "tent-bounties.sample.json"
SETTINGS = PublisherSettings(
    wf_data_url="http://wf-data:8080/warframe/cetus/tent-bounties",
    event_server_url="http://eventserver:8080",
    publisher_token="t" * 32,
)
OBSERVED_AT = datetime(2026, 9, 17, 3, 50, tzinfo=UTC)


class FakeSource:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    def fetch(self) -> dict:
        self.calls += 1
        return self.payload


class FakeClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.published: list[tuple] = []
        self.fail = fail

    def publish(self, window, *, observed_at, notify_at) -> None:
        if self.fail:
            raise RuntimeError("boom")
        self.published.append((window.section, window.dedupe_key, observed_at, notify_at))


def load_payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def with_next(payload: dict) -> dict:
    payload["next"] = {
        "activation": "2026-09-17T14:18:50.647+08:00",
        "expiry": "2026-09-17T16:48:49.000+08:00",
        "tentA": {"jobs": [{"id": "RescueBountyResc", "nameZh": "搜索并救援"}]},
    }
    return payload


def test_first_run_publishes_once_per_available_window() -> None:
    client = FakeClient()
    publisher = BountyPublisher(SETTINGS, client, FakeSource(load_payload()))
    assert publisher.run_once(OBSERVED_AT) == 1
    assert client.published[0][0] == "current"
    assert client.published[0][3] is None


def test_upcoming_window_is_published_with_the_lead_time() -> None:
    client = FakeClient()
    publisher = BountyPublisher(SETTINGS, client, FakeSource(with_next(load_payload())))
    assert publisher.run_once(OBSERVED_AT) == 2
    by_section = {item[0]: item for item in client.published}
    activation = datetime(2026, 9, 17, 6, 18, 50, tzinfo=UTC)
    assert by_section["next"][3] == activation - timedelta(seconds=SETTINGS.lead_seconds)
    assert by_section["next"][1] == "2026-09-17T06:18:50Z"


def test_the_same_activation_is_not_republished_while_polling() -> None:
    source = FakeSource(with_next(load_payload()))
    client = FakeClient()
    publisher = BountyPublisher(SETTINGS, client, source)
    assert publisher.run_once(OBSERVED_AT) == 2
    assert publisher.run_once(OBSERVED_AT + timedelta(minutes=1)) == 0
    assert len(client.published) == 2
    assert source.calls == 2


def test_a_new_activation_publishes_again() -> None:
    payload = load_payload()
    client = FakeClient()
    publisher = BountyPublisher(SETTINGS, client, FakeSource(payload))
    assert publisher.run_once(OBSERVED_AT) == 1
    payload["current"]["activation"] = "2026-09-17T14:18:50.647+08:00"
    assert publisher.run_once(OBSERVED_AT + timedelta(minutes=150)) == 1
    assert client.published[-1][1] == "2026-09-17T06:18:50Z"


def test_a_failed_publish_is_retried_on_the_next_poll() -> None:
    payload = load_payload()
    client = FakeClient(fail=True)
    publisher = BountyPublisher(SETTINGS, client, FakeSource(payload))
    try:
        publisher.run_once(OBSERVED_AT)
    except RuntimeError:
        pass
    else:
        raise AssertionError("publish failure must propagate so the cycle can retry")
    client.fail = False
    assert publisher.run_once(OBSERVED_AT) == 1


def test_each_window_logs_one_line_while_polling(caplog) -> None:
    publisher = BountyPublisher(SETTINGS, FakeClient(), FakeSource(with_next(load_payload())))
    with caplog.at_level(logging.INFO):
        publisher.run_once(OBSERVED_AT)
        publisher.run_once(OBSERVED_AT + timedelta(minutes=1))
        publisher.run_once(OBSERVED_AT + timedelta(minutes=2))
    messages = [record.getMessage() for record in caplog.records]
    assert len(messages) == 2
    assert any("(tent+konzu, 8 match keys)" in message for message in messages)
    assert any("(tent-only, 1 match keys)" in message for message in messages)


def test_a_missing_upcoming_window_is_not_logged(caplog) -> None:
    publisher = BountyPublisher(SETTINGS, FakeClient(), FakeSource(load_payload()))
    with caplog.at_level(logging.INFO):
        assert publisher.run_once(OBSERVED_AT) == 1
        assert publisher.run_once(OBSERVED_AT + timedelta(minutes=1)) == 0
    levels = [record.levelno for record in caplog.records]
    assert levels == [logging.INFO]


def test_a_missing_current_window_is_reported_once(caplog) -> None:
    publisher = BountyPublisher(SETTINGS, FakeClient(), FakeSource({"konzu": {}}))
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            assert publisher.run_once(OBSERVED_AT) == 0
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "the current bounty window is missing" in warnings[0].getMessage()


def test_a_current_window_without_konzu_warns_once(caplog) -> None:
    payload = load_payload()
    payload["konzu"]["activation"] = "2026-09-17T09:00:00+08:00"
    publisher = BountyPublisher(SETTINGS, FakeClient(), FakeSource(payload))
    with caplog.at_level(logging.WARNING):
        publisher.run_once(OBSERVED_AT)
        publisher.run_once(OBSERVED_AT + timedelta(minutes=1))
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "without a konzu block" in warnings[0].getMessage()
