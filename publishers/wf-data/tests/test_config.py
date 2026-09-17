import pytest

from wfdata_publisher.config import ConfigurationError, PublisherSettings

BASE_ENV = {
    "WF_DATA_URL": "http://wf-data:8080/warframe/cetus/tent-bounties",
    "EVENTSERVER_URL": "http://eventserver:8080",
    "PUBLISHER_TOKEN": "t" * 32,
}


def test_defaults_match_the_design(monkeypatch) -> None:
    for key, value in BASE_ENV.items():
        monkeypatch.setenv(key, value)
    settings = PublisherSettings.from_environment()
    assert settings.poll_seconds == 60.0
    assert settings.lead_seconds == 300
    assert settings.max_response_bytes == 262_144
    assert str(settings.display_timezone) == "Asia/Shanghai"


def test_lead_time_is_a_deployment_setting(monkeypatch) -> None:
    for key, value in BASE_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("LEAD_SECONDS", "480")
    assert PublisherSettings.from_environment().lead_seconds == 480


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("WF_DATA_URL", "wf-data:8080"),
        ("EVENTSERVER_URL", ""),
        ("PUBLISHER_TOKEN", "too-short"),
        ("POLL_SECONDS", "0"),
        ("LEAD_SECONDS", "1.5"),
        ("DISPLAY_TIMEZONE", "Mars/Olympus"),
    ],
)
def test_invalid_settings_are_rejected(monkeypatch, key: str, value: str) -> None:
    for env_key, env_value in BASE_ENV.items():
        monkeypatch.setenv(env_key, env_value)
    monkeypatch.setenv(key, value)
    with pytest.raises(ConfigurationError):
        PublisherSettings.from_environment()
