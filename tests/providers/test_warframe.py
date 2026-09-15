from datetime import UTC, datetime

from eventserver.providers.warframe.cetus_night import CetusNightProvider
from eventserver.providers.warframe.ghoul_event import GhoulEventProvider
from eventserver.providers.warframe.konzu_rotation import KonzuRotationProvider

NOW = datetime(2026, 9, 14, 12, tzinfo=UTC)


def test_cetus_first_observation_is_baseline_and_only_day_to_night_triggers() -> None:
    provider = CetusNightProvider()
    day = provider.normalize({"identity": "cycle-1", "is_night": False, "observed_at": NOW})
    night = provider.normalize({"identity": "cycle-2", "is_night": True, "observed_at": NOW})
    assert provider.evaluate(None, night) == []
    [event] = provider.evaluate(day, night)
    assert event.event_key == "warframe.cetus.night"
    assert provider.evaluate(night, night) == []


def test_konzu_rotation_uses_stable_rotation_id() -> None:
    provider = KonzuRotationProvider()
    previous = provider.normalize({"rotation_id": "r1", "observed_at": NOW})
    current = provider.normalize({"rotation_id": "r2", "observed_at": NOW})
    assert provider.evaluate(None, current) == []
    assert provider.evaluate(previous, previous) == []
    [event] = provider.evaluate(previous, current)
    assert event.dedupe_key == "r2"
    assert "暂不可可靠解析" in provider.render(event).text


def test_ghoul_only_triggers_inactive_to_active() -> None:
    provider = GhoulEventProvider()
    inactive = provider.normalize({"identity": "g1", "active": False, "observed_at": NOW})
    active = provider.normalize({"identity": "g2", "active": True, "observed_at": NOW})
    assert provider.evaluate(None, active) == []
    assert len(provider.evaluate(inactive, active)) == 1
    assert provider.evaluate(active, active) == []
