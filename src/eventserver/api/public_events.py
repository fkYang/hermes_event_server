from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from eventserver.api.schemas import EventResponse
from eventserver.auth.service import require_service_auth
from eventserver.db.models import EventType
from eventserver.db.session import get_db

router = APIRouter(
    prefix="/v1/events", tags=["events"], dependencies=[Depends(require_service_auth)]
)


@router.get("", response_model=list[EventResponse])
def list_events(session: Session = Depends(get_db)) -> list[EventResponse]:
    events = session.scalars(
        select(EventType).where(EventType.enabled.is_(True)).order_by(EventType.event_key)
    )
    return [
        EventResponse(
            event_key=item.event_key,
            display_name=item.display_name,
            description=item.description,
            schema_version=item.schema_version,
            deprecated=item.deprecated_at is not None,
        )
        for item in events
    ]
