import json
from pathlib import Path

from wfdata_publisher.source import parse_window

FIXTURE = Path(__file__).parent / "fixtures" / "tent-bounties.sample.json"
EXPECTED_CURRENT_KEYS = (
    "AssassinateBountyAss",
    "AttritionBountyExt",
    "AttritionBountyLib",
    "CaptureBountyCapOne",
    "CaptureBountyCapTwo",
    "ReclamationBountyCap",
    "RescueBountyResc",
    "SabotageBountySab",
)


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_current_window_uses_only_the_declared_scan_scope() -> None:
    window = parse_window(load_fixture(), "current")
    assert window is not None
    assert window.event_key == "warframe.cetus.bounty_current"
    assert window.dedupe_key == "2026-09-17T03:48:51Z"
    assert window.match_keys == EXPECTED_CURRENT_KEYS
    assert window.labels()[0] == "刺杀指挥官"
    assert window.konzu_found is True


def test_lower_normal_tiers_steel_path_and_narmer_are_never_scanned() -> None:
    window = parse_window(load_fixture(), "current")
    assert window is not None
    sources = {job.source for job in window.jobs}
    assert sources == {"tentA", "tentB", "tentC", "konzu.normal.tier5"}
    # Only present in tiers 1-4 of konzu.normal.
    assert "AssassinateBountyCap" not in window.match_keys
    assert "ReclamationBountyCache" not in window.match_keys


def test_tent_jobs_keep_their_slot_as_source() -> None:
    window = parse_window(load_fixture(), "current")
    assert window is not None
    by_key = {job.key: job for job in window.jobs}
    assert by_key["RescueBountyResc"].source == "tentA"
    assert by_key["AttritionBountyExt"].tier == 5
    shared = {job.source for job in window.jobs if job.key == "ReclamationBountyCap"}
    assert shared == {"tentB", "tentC"}


def test_next_window_is_absent_until_the_source_exposes_it() -> None:
    assert parse_window(load_fixture(), "next") is None


def test_next_window_scans_tents_only() -> None:
    payload = load_fixture()
    activation = "2026-09-17T14:18:50.647+08:00"
    payload["next"] = {
        "activation": activation,
        "expiry": "2026-09-17T16:48:49.000+08:00",
        "tentA": {
            "jobs": [{"id": "RescueBountyResc", "nameZh": "搜索并救援"}],
        },
        "konzu": {
            "activation": activation,
            "expiry": "2026-09-17T16:48:49.000+08:00",
            "normal": [
                {"tier": 4, "jobId": "AssassinateBountyAss", "nameZh": "刺杀指挥官"},
                {"tier": 5, "jobId": "ReclamationBountyCache", "nameZh": "找出遗失的器物"},
            ],
        },
    }
    window = parse_window(payload, "next")
    assert window is not None
    assert window.event_key == "warframe.cetus.bounty_next"
    assert window.dedupe_key == "2026-09-17T06:18:50Z"
    assert window.match_keys == ("RescueBountyResc",)
    assert window.konzu_found is None


def test_next_window_ignores_a_top_level_konzu_block() -> None:
    payload = load_fixture()
    payload["next"] = {
        "activation": "2026-09-17T14:18:50.647+08:00",
        "expiry": "2026-09-17T16:48:49.000+08:00",
        "tentA": {"jobs": [{"id": "RescueBountyResc", "nameZh": "搜索并救援"}]},
    }
    window = parse_window(payload, "next")
    assert window is not None
    assert window.match_keys == ("RescueBountyResc",)


def test_current_window_flags_a_konzu_block_that_does_not_match() -> None:
    payload = load_fixture()
    payload["konzu"]["activation"] = "2026-09-17T09:00:00+08:00"
    window = parse_window(payload, "current")
    assert window is not None
    assert window.konzu_found is False
    assert "AttritionBountyExt" not in window.match_keys
    assert window.match_keys == tuple(
        key for key in EXPECTED_CURRENT_KEYS if key != "AttritionBountyExt"
    )


def test_windows_without_bounties_or_broken_timestamps_are_ignored() -> None:
    assert parse_window({"current": {"activation": "x", "expiry": "y"}}, "current") is None
    assert (
        parse_window(
            {
                "current": {
                    "activation": "2026-09-17T11:48:51+08:00",
                    "expiry": "2026-09-17T14:18:50+08:00",
                    "tentA": {"jobs": []},
                }
            },
            "current",
        )
        is None
    )
    assert (
        parse_window(
            {
                "current": {
                    "activation": "2026-09-17T11:48:51",
                    "expiry": "2026-09-17T14:18:50+08:00",
                    "tentA": {"jobs": [{"id": "RescueBountyResc", "nameZh": "搜索并救援"}]},
                }
            },
            "current",
        )
        is None
    )
