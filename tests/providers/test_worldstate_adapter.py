import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

from eventserver.providers.warframe.worldstate_adapter import (
    WarframeWorldStateAdapter,
    WorldStateSchemaError,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "worldstate_relevant.json"


def payload() -> dict[str, object]:
    return json.loads(FIXTURE.read_text())


def test_adapter_extracts_day_konzu_and_active_ghoul() -> None:
    extracted = WarframeWorldStateAdapter().extract_all(payload())
    cetus = extracted["warframe.cetus_night"]
    konzu = extracted["warframe.konzu_rotation"]
    ghoul = extracted["warframe.ghoul_event"]
    assert cetus["is_night"] is False
    assert cetus["expires_at"] < konzu["expires_at"]
    assert konzu["rotation_id"] == "49224:1789400958"
    assert konzu["confirmed_summary"] is None
    assert ghoul["active"] is True
    assert ghoul["identity"] == "fixture-ghoul-event"


def test_cetus_switches_to_night_during_final_3000_seconds() -> None:
    fixture = payload()
    day = WarframeWorldStateAdapter().cetus_night(fixture)
    night_payload = deepcopy(fixture)
    night_payload["Time"] = int((day["expires_at"] + timedelta(seconds=1)).timestamp())
    night = WarframeWorldStateAdapter().cetus_night(night_payload)
    assert night["is_night"] is True
    assert night["identity"].endswith(":night")


def test_missing_cetus_section_fails_closed() -> None:
    fixture = payload()
    fixture["SyndicateMissions"] = []
    try:
        WarframeWorldStateAdapter().cetus_night(fixture)
    except WorldStateSchemaError:
        pass
    else:
        raise AssertionError("missing Cetus mission was accepted")
