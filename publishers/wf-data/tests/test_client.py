import json
from datetime import UTC, datetime
from pathlib import Path

from wfdata_publisher.client import build_payload
from wfdata_publisher.config import PublisherSettings
from wfdata_publisher.source import parse_window

FIXTURE = Path(__file__).parent / "fixtures" / "tent-bounties.sample.json"
SETTINGS = PublisherSettings(
    wf_data_url="http://wf-data:8080/warframe/cetus/tent-bounties",
    event_server_url="http://eventserver:8080",
    publisher_token="t" * 32,
)
OBSERVED_AT = datetime(2026, 9, 17, 3, 50, tzinfo=UTC)


def window():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    result = parse_window(payload, "current")
    assert result is not None
    return result


def test_payload_matches_the_registered_catalog_contract() -> None:
    payload = build_payload(window(), observed_at=OBSERVED_AT, notify_at=None, settings=SETTINGS)
    assert payload["event_key"] == "warframe.cetus.bounty_current"
    assert payload["schema_version"] == 1
    assert payload["dedupe_key"] == "2026-09-17T03:48:51Z"
    assert payload["occurred_at"] == "2026-09-17T03:50:00Z"
    assert "notify_at" not in payload
    assert set(payload["data"]) == {"window", "activation", "expiry", "match_keys", "jobs"}
    assert payload["data"]["window"] == "current"
    assert "default" in payload["messages"]


def test_upcoming_window_payload_carries_notify_at() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["next"] = {
        "activation": "2026-09-17T14:18:50.647+08:00",
        "expiry": "2026-09-17T16:48:49.000+08:00",
        "tentA": {"jobs": [{"id": "RescueBountyResc", "nameZh": "搜索并救援"}]},
    }
    upcoming = parse_window(payload, "next")
    assert upcoming is not None
    built = build_payload(
        upcoming,
        observed_at=OBSERVED_AT,
        notify_at=datetime(2026, 9, 17, 6, 13, 50, tzinfo=UTC),
        settings=SETTINGS,
    )
    assert built["event_key"] == "warframe.cetus.bounty_next"
    assert built["notify_at"] == "2026-09-17T06:13:50Z"
    assert built["data"]["window"] == "next"
