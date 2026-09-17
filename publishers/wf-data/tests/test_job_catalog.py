import json
from pathlib import Path

from wfdata_publisher.job_catalog import JOB_LABELS, catalog_options, label_for
from wfdata_publisher.source import parse_window

CONFIG = Path(__file__).parents[1] / "config"
FIXTURE = Path(__file__).parent / "fixtures" / "tent-bounties.sample.json"


def test_both_event_catalogs_declare_exactly_the_job_catalog() -> None:
    expected = catalog_options()
    assert len(expected) == 13
    for name in ("event-catalog.current.json", "event-catalog.next.json"):
        entry = json.loads((CONFIG / name).read_text(encoding="utf-8"))
        assert entry["match_key_field"] == "match_keys"
        assert entry["match_keys_required"] is True
        assert entry["subscribable"] is True
        assert entry["match_key_options"] == expected


def test_every_key_the_source_can_report_is_declared_in_the_catalog() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    window = parse_window(payload, "current")
    assert window is not None
    assert set(window.match_keys) <= set(JOB_LABELS)


def test_unknown_keys_fall_back_to_the_raw_identifier() -> None:
    assert label_for("RescueBountyResc") == "搜索并救援"
    assert label_for("SomeFutureBounty") == "SomeFutureBounty"
