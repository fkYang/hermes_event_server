from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from eventserver.api.helpers import resolve_notify_at
from eventserver.api.schemas import PublishEventRequest, PublishEventResponse
from eventserver.auth.publisher import PublisherIdentity
from eventserver.config import Settings, get_settings
from eventserver.core.models import DomainEvent
from eventserver.core.publication import PublicationError, PublicationService
from eventserver.db.models import AuditLog
from eventserver.db.session import get_db
from eventserver.services.common import mask_identifier

router = APIRouter(prefix="/v1/publish", tags=["publisher"])


@router.post("/events", response_model=PublishEventResponse)
def publish_event(
    request: Request,
    body: PublishEventRequest,
    publisher: PublisherIdentity,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_db),
) -> PublishEventResponse:
    if not any(body.event_key.startswith(prefix) for prefix in publisher.allowed_event_prefixes):
        raise HTTPException(
            status_code=403, detail="publisher is not authorized for this event key"
        )
    event = DomainEvent(
        event_id=str(uuid4()),
        event_key=body.event_key,
        schema_version=body.schema_version,
        dedupe_key=body.dedupe_key,
        occurred_at=body.occurred_at,
        subject=body.subject,
        data=body.data,
        metadata={**body.metadata, "publisher_key": publisher.publisher_key},
    )
    try:
        notify_at = resolve_notify_at(body.notify_at, settings)
        result = PublicationService(session).publish(
            event, body.messages, next_attempt_at=notify_at
        )
    except PublicationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.add(
        AuditLog(
            target_type="event_occurrence",
            target_id_masked=mask_identifier(result.event_id),
            action="publisher_publish",
            result="created" if result.created else "duplicate",
            request_id=request.state.request_id,
            details={
                "publisher_key": publisher.publisher_key,
                "event_key": body.event_key,
                "deliveries_created": result.deliveries_created,
                "notify_at": notify_at.isoformat() if notify_at else None,
            },
        )
    )
    session.commit()
    return PublishEventResponse(
        event_id=result.event_id,
        created=result.created,
        deliveries_created=result.deliveries_created,
        notify_at=notify_at,
    )
