from datetime import UTC, datetime

import pytest

from demo_reminder.client import PublishResult
from demo_reminder.config import PublisherSettings
from demo_reminder.schedule import DelayError
from demo_reminder.service import ReminderInputError, ReminderService

NOW = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
SETTINGS = PublisherSettings(
    event_server_url="http://eventserver:8080",
    publisher_token="t" * 32,
    ingress_token="i" * 16,
    default_delay_seconds=300,
    max_delay_seconds=3600,
)


class FakePublisher:
    def __init__(self) -> None:
        self.requests: list = []

    def publish(self, request) -> PublishResult:
        self.requests.append(request)
        return PublishResult(
            event_id="evt-1",
            created=True,
            deliveries_created=2,
            notify_at=request.notify_at,
        )


def build_service() -> tuple[ReminderService, FakePublisher]:
    publisher = FakePublisher()
    return ReminderService(SETTINGS, publisher, clock=lambda: NOW), publisher


def test_the_default_delay_is_used_when_the_caller_omits_one() -> None:
    service, publisher = build_service()
    result = service.submit(text="喝水")
    request = publisher.requests[0]
    assert request.delay_seconds == 300
    assert request.notify_at == NOW.replace(minute=5)
    assert request.title == "演示提醒"
    assert result.deliveries_created == 2


def test_a_delay_parameter_is_honoured() -> None:
    service, publisher = build_service()
    service.submit(text="开会", delay="10min")
    assert publisher.requests[0].delay_seconds == 600
    assert publisher.requests[0].notify_at == NOW.replace(minute=10)


def test_an_explicit_delay_seconds_is_honoured() -> None:
    service, publisher = build_service()
    service.submit(text="立刻动身", delay_seconds=90)
    assert publisher.requests[0].delay_seconds == 90
    assert publisher.requests[0].notify_at == NOW.replace(minute=1, second=30)


def test_an_absolute_time_is_converted_to_utc() -> None:
    service, publisher = build_service()
    service.submit(text="看比赛", at="2026-09-17T20:30:00+08:00")
    request = publisher.requests[0]
    assert request.notify_at == datetime(2026, 9, 17, 12, 30, tzinfo=UTC)
    assert request.delay_seconds == 1800


def test_an_absolute_time_in_the_past_is_clamped_to_zero_delay() -> None:
    service, publisher = build_service()
    service.submit(text="已经过了", at="2026-09-17T10:00:00+08:00")
    assert publisher.requests[0].delay_seconds == 0


def test_only_one_timing_parameter_is_accepted() -> None:
    service, _ = build_service()
    with pytest.raises(ReminderInputError):
        service.submit(text="冲突", delay="5m", delay_seconds=60)


def test_an_absolute_time_needs_an_offset() -> None:
    service, _ = build_service()
    with pytest.raises(ReminderInputError):
        service.submit(text="裸时间", at="2026-09-17T21:30:00")


def test_a_schedule_beyond_the_horizon_is_rejected() -> None:
    service, _ = build_service()
    with pytest.raises(DelayError):
        service.submit(text="太远", delay="2h")
    with pytest.raises(ReminderInputError):
        service.submit(text="太远", at="2026-09-17T23:30:00+08:00")


def test_every_request_gets_its_own_dedupe_key() -> None:
    service, publisher = build_service()
    service.submit(text="第一条")
    service.submit(text="第二条")
    first, second = publisher.requests
    assert first.dedupe_key != second.dedupe_key
    assert first.request_id == first.dedupe_key


def test_an_explicit_dedupe_key_is_reused_for_idempotency() -> None:
    service, publisher = build_service()
    service.submit(text="重复提交", dedupe_key="demo-2026-09-17")
    assert publisher.requests[0].dedupe_key == "demo-2026-09-17"
    with pytest.raises(ReminderInputError):
        service.submit(text="非法 key", dedupe_key="有 空格")


@pytest.mark.parametrize("text", ["", "   ", None, 5, "x" * 501])
def test_invalid_text_is_rejected(text) -> None:
    service, _ = build_service()
    with pytest.raises(ReminderInputError):
        service.submit(text=text)


def test_title_is_optional_and_bounded() -> None:
    service, publisher = build_service()
    service.submit(text="内容", title="  自定义标题  ")
    assert publisher.requests[0].title == "自定义标题"
    with pytest.raises(ReminderInputError):
        service.submit(text="内容", title="x" * 101)
