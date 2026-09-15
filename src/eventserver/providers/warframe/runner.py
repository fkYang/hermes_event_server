import argparse
import logging
import signal
from dataclasses import dataclass
from socket import gethostname
from threading import Event
from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from eventserver.config import get_settings
from eventserver.core.processing import ObservationProcessor
from eventserver.db.session import SessionLocal
from eventserver.db.transactions import run_with_deadlock_retry
from eventserver.observability import configure_logging
from eventserver.providers import build_registry
from eventserver.providers.warframe.client import WarframeWorldStateClient
from eventserver.providers.warframe.worldstate_adapter import WarframeWorldStateAdapter
from eventserver.scheduler.leases import (
    ProviderLease,
    claim_due_providers,
    release_provider_lease,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PollRunResult:
    claimed: int
    succeeded: int
    failed: int
    baselines_created: int
    events_published: int


class WarframePollRunner:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        client: WarframeWorldStateClient | None = None,
        adapter: WarframeWorldStateAdapter | None = None,
        owner: str | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.client = client or WarframeWorldStateClient()
        self.adapter = adapter or WarframeWorldStateAdapter()
        self.owner = owner or f"{gethostname()}:{uuid4()}"
        self.registry = build_registry()

    def run_once(self, *, limit: int = 10) -> PollRunResult:
        leases = run_with_deadlock_retry(
            self.session_factory,
            lambda session: claim_due_providers(session, owner=self.owner, limit=limit),
        )
        if not leases:
            return PollRunResult(0, 0, 0, 0, 0)

        try:
            payload = self.client.fetch()
        except Exception:
            logger.exception("Warframe WorldState fetch failed", extra={"providers": len(leases)})
            for lease in leases:
                self._record_failure(lease)
            return PollRunResult(len(leases), 0, len(leases), 0, 0)

        succeeded = 0
        failed = 0
        baselines = 0
        events = 0
        for lease in leases:
            try:
                raw = self.adapter.extract(lease.provider_key, payload)
                result = run_with_deadlock_retry(
                    self.session_factory,
                    lambda session, lease=lease, raw=raw: self._process(session, lease, raw),
                )
            except Exception:
                logger.exception(
                    "Warframe provider processing failed",
                    extra={"provider_instance_id": lease.provider_instance_id},
                )
                self._record_failure(lease)
                failed += 1
                continue
            succeeded += 1
            baselines += int(result.baseline_created)
            events += sum(int(item.created) for item in result.publications)
        return PollRunResult(len(leases), succeeded, failed, baselines, events)

    def _process(self, session: Session, lease: ProviderLease, raw: dict[str, object]):
        result = ObservationProcessor(session, self.registry).process(
            lease.provider_instance_id, raw
        )
        if not release_provider_lease(session, lease.provider_instance_id, self.owner):
            raise RuntimeError("provider lease was lost before processing completed")
        return result

    def _record_failure(self, lease: ProviderLease) -> None:
        def operation(session: Session) -> None:
            ObservationProcessor(session, self.registry).record_failure(lease.provider_instance_id)
            release_provider_lease(session, lease.provider_instance_id, self.owner)

        run_with_deadlock_retry(self.session_factory, operation)


def serve(runner: WarframePollRunner, *, tick_seconds: float) -> None:
    stopping = Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stopping.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    logger.info("Warframe scheduler started", extra={"tick_seconds": tick_seconds})
    while not stopping.is_set():
        result = runner.run_once()
        if result.claimed:
            logger.info(
                "Warframe polling batch completed",
                extra={
                    "claimed": result.claimed,
                    "succeeded": result.succeeded,
                    "failed": result.failed,
                    "baselines": result.baselines_created,
                    "events": result.events_published,
                },
            )
        stopping.wait(tick_seconds)
    logger.info("Warframe scheduler stopped")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Warframe provider scheduler")
    parser.add_argument("--once", action="store_true", help="run one due-provider batch and exit")
    args = parser.parse_args()
    configure_logging()
    settings = get_settings()
    runner = WarframePollRunner(
        SessionLocal,
        client=WarframeWorldStateClient(timeout_seconds=settings.provider_default_timeout_seconds),
    )
    if args.once:
        result = runner.run_once()
        print(
            f"claimed={result.claimed} succeeded={result.succeeded} failed={result.failed} "
            f"baselines={result.baselines_created} events={result.events_published}"
        )
    else:
        serve(runner, tick_seconds=settings.provider_scheduler_tick_seconds)


if __name__ == "__main__":
    main()
