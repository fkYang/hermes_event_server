import copy
import json
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from eventserver.bootstrap import bootstrap
from eventserver.db.models import ObservationRecord, ProviderCheckpoint, ProviderInstance
from eventserver.providers.warframe.runner import WarframePollRunner

FIXTURE = Path(__file__).parents[1] / "fixtures" / "worldstate_relevant.json"


class FakeClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls = 0

    def fetch(self) -> dict[str, object]:
        self.calls += 1
        return copy.deepcopy(self.payload)


def load_payload() -> dict[str, object]:
    return json.loads(FIXTURE.read_text())


def test_runner_fetches_once_and_creates_three_baselines(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        bootstrap(session, ())
    client = FakeClient(load_payload())

    result = WarframePollRunner(session_factory, client=client, owner="runner-test").run_once()

    assert client.calls == 1
    assert result.claimed == result.succeeded == result.baselines_created == 3
    assert result.failed == result.events_published == 0
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ObservationRecord)) == 3
        checkpoints = list(session.scalars(select(ProviderCheckpoint)))
        assert all(row.lease_owner is None and row.consecutive_failures == 0 for row in checkpoints)


def test_runner_isolates_one_malformed_provider(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        bootstrap(session, ())
    payload = load_payload()
    payload["Goals"] = "invalid"

    result = WarframePollRunner(
        session_factory, client=FakeClient(payload), owner="runner-test"
    ).run_once()

    assert result.succeeded == 2
    assert result.failed == 1
    with session_factory() as session:
        ghoul = session.get(ProviderCheckpoint, "warframe-ghoul-pc")
        assert ghoul is not None and ghoul.consecutive_failures == 1
        session.execute(update(ProviderInstance).values(next_run_at=None))
        session.commit()
