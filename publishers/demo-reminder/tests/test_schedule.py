import pytest

from demo_reminder.schedule import DelayError, humanize_delay, parse_delay


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("5m", 300),
        ("10mins", 600),
        ("90s", 90),
        ("1h", 3600),
        ("2 hours", 7200),
        ("5", 300),
        (5, 300),
        (0, 0),
        ("0s", 0),
    ],
)
def test_supported_delay_forms(value, expected: int) -> None:
    assert parse_delay(value, max_seconds=7200) == expected


@pytest.mark.parametrize("value", ["", "later", "5x", "-5m", "5m30", None, True, ["5m"]])
def test_malformed_delays_are_rejected(value) -> None:
    with pytest.raises(DelayError):
        parse_delay(value, max_seconds=3600)


def test_delays_beyond_the_configured_maximum_are_rejected() -> None:
    with pytest.raises(DelayError):
        parse_delay("2h", max_seconds=3600)


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "立即"),
        (30, "30 秒"),
        (300, "5 分钟"),
        (3600, "1 小时"),
        (5400, "1 小时 30 分钟"),
    ],
)
def test_humanized_delays(seconds: int, expected: str) -> None:
    assert humanize_delay(seconds) == expected
