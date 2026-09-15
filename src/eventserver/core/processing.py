import hashlib
import json
from dataclasses import dataclass
from datetime import UTC

from sqlalchemy import select
from sqlalchemy.orm import Session

from eventserver.core.models import Observation
from eventserver.core.publication import PublicationResult, PublicationService
from eventserver.core.registry import ProviderRegistry
from eventserver.db.models import ObservationRecord, ProviderCheckpoint, ProviderInstance


@dataclass(frozen=True)
class ProcessingResult:
    baseline_created: bool
    unchanged: bool
    publications: tuple[PublicationResult, ...]


def _state_hash(observation: Observation) -> str:
    body = json.dumps(observation.state, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(body.encode()).hexdigest()


class ObservationProcessor:
    def __init__(self, session: Session, registry: ProviderRegistry) -> None:
        self.session = session
        self.registry = registry

    def process(self, provider_instance_id: str, raw: dict[str, object]) -> ProcessingResult:
        instance = self.session.scalar(
            select(ProviderInstance)
            .where(ProviderInstance.provider_instance_id == provider_instance_id)
            .with_for_update()
        )
        if instance is None or not instance.enabled:
            raise LookupError(f"provider instance is unavailable: {provider_instance_id}")
        provider = self.registry.get(instance.provider_key)
        current = provider.normalize(raw)
        if current.provider_key != instance.provider_key:
            raise ValueError("provider returned an observation for another provider_key")

        checkpoint = self.session.get(ProviderCheckpoint, provider_instance_id)
        if checkpoint is None:
            checkpoint = ProviderCheckpoint(provider_instance_id=provider_instance_id)
            self.session.add(checkpoint)
            self.session.flush()

        current_hash = _state_hash(current)
        if checkpoint.last_identity == current.identity and checkpoint.state_hash == current_hash:
            checkpoint.last_success_at = current.observed_at
            checkpoint.consecutive_failures = 0
            self.session.flush()
            return ProcessingResult(False, True, ())

        previous = self._previous(checkpoint, current)
        events = provider.evaluate(previous, current)
        self._save_observation(provider_instance_id, current)
        publications = tuple(
            PublicationService(self.session, self.registry).publish(event) for event in events
        )
        baseline_created = checkpoint.last_identity is None
        checkpoint.last_identity = current.identity
        checkpoint.state_hash = current_hash
        checkpoint.state = current.state
        checkpoint.last_success_at = current.observed_at
        checkpoint.consecutive_failures = 0
        self.session.flush()
        return ProcessingResult(baseline_created, False, publications)

    def record_failure(self, provider_instance_id: str) -> None:
        checkpoint = self.session.get(ProviderCheckpoint, provider_instance_id)
        if checkpoint is None:
            checkpoint = ProviderCheckpoint(provider_instance_id=provider_instance_id)
            self.session.add(checkpoint)
        checkpoint.consecutive_failures += 1
        self.session.flush()

    @staticmethod
    def _previous(checkpoint: ProviderCheckpoint, current: Observation) -> Observation | None:
        if checkpoint.last_identity is None or checkpoint.state is None:
            return None
        observed_at = checkpoint.last_success_at or current.observed_at
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=UTC)
        return Observation(
            provider_key=current.provider_key,
            schema_version=current.schema_version,
            identity=checkpoint.last_identity,
            observed_at=observed_at,
            effective_at=observed_at,
            state=checkpoint.state,
            source_metadata={"source": "provider-checkpoint"},
        )

    def _save_observation(self, provider_instance_id: str, current: Observation) -> None:
        existing = self.session.scalar(
            select(ObservationRecord.observation_id).where(
                ObservationRecord.provider_instance_id == provider_instance_id,
                ObservationRecord.identity == current.identity,
            )
        )
        if existing is not None:
            return
        self.session.add(
            ObservationRecord(
                provider_instance_id=provider_instance_id,
                schema_version=current.schema_version,
                identity=current.identity,
                observed_at=current.observed_at,
                effective_at=current.effective_at,
                expires_at=current.expires_at,
                state=current.state,
                source_metadata=current.source_metadata,
            )
        )
