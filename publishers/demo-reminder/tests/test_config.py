import pytest

from demo_reminder.config import ConfigurationError, PublisherSettings

BASE_ENV = {
    "EVENTSERVER_URL": "http://eventserver:8080",
    "PUBLISHER_TOKEN": "t" * 32,
    "INGRESS_TOKEN": "i" * 16,
}


def test_defaults_match_the_design(monkeypatch) -> None:
    for key, value in BASE_ENV.items():
        monkeypatch.setenv(key, value)
    settings = PublisherSettings.from_environment()
    assert settings.http_port == 8080
    assert settings.default_delay_seconds == 300
    assert settings.max_delay_seconds == 3600
    assert settings.max_body_bytes == 16_384
    assert str(settings.display_timezone) == "Asia/Shanghai"


def test_the_ingress_token_is_optional_for_cli_use(monkeypatch) -> None:
    for key, value in BASE_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("INGRESS_TOKEN")
    assert PublisherSettings.from_environment().ingress_token is None


def test_a_short_ingress_token_is_rejected(monkeypatch) -> None:
    for key, value in BASE_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("INGRESS_TOKEN", "short")
    with pytest.raises(ConfigurationError):
        PublisherSettings.from_environment()


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("EVENTSERVER_URL", "eventserver:8080"),
        ("PUBLISHER_TOKEN", "too-short"),
        ("HTTP_PORT", "0"),
        ("DEFAULT_DELAY_SECONDS", "7200"),
        ("MAX_DELAY_SECONDS", "30"),
        ("MAX_DELAY_SECONDS", "1.5"),
        ("DISPLAY_TIMEZONE", "Mars/Olympus"),
    ],
)
def test_invalid_settings_are_rejected(monkeypatch, key: str, value: str) -> None:
    for env_key, env_value in BASE_ENV.items():
        monkeypatch.setenv(env_key, env_value)
    monkeypatch.setenv(key, value)
    with pytest.raises(ConfigurationError):
        PublisherSettings.from_environment()
