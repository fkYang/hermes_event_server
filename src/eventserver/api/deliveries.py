from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from eventserver.api.schemas import (
    ClaimedDeliveryResponse,
    DeliveryAckRequest,
    DeliveryClaimRequest,
    DeliveryClaimResponse,
    DeliveryFailRequest,
    DeliveryStatusResponse,
    DeliveryTarget,
)
from eventserver.auth.service import require_service_auth
from eventserver.config import Settings, get_settings
from eventserver.db.session import get_db
from eventserver.deliveries.outbox import DeliveryOutbox, LeaseConflictError

router = APIRouter(
    prefix="/v1/deliveries", tags=["deliveries"], dependencies=[Depends(require_service_auth)]
)


@router.post("/claim", response_model=DeliveryClaimResponse)
def claim_deliveries(
    body: DeliveryClaimRequest,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_db),
) -> DeliveryClaimResponse:
    outbox = DeliveryOutbox(session, settings.delivery_max_attempts)
    claimed = outbox.claim(
        worker_id=body.worker_id,
        platform=body.platform,
        limit=body.limit,
        lease_seconds=body.lease_seconds or settings.delivery_default_lease_seconds,
    )
    session.commit()
    return DeliveryClaimResponse(
        items=[
            ClaimedDeliveryResponse(
                delivery_id=item.delivery_id,
                lease_token=item.lease_token,
                event_id=item.event_id,
                event_key=item.event_key,
                target=DeliveryTarget(platform=item.platform, openid=item.openid),
                message=item.message,
                attempt=item.attempt,
                created_at=item.created_at,
            )
            for item in claimed
        ]
    )


def _status(row: object) -> DeliveryStatusResponse:
    return DeliveryStatusResponse(
        delivery_id=row.delivery_id,
        status=row.status,
        attempts=row.attempts,
        next_attempt_at=row.next_attempt_at,
    )


@router.post("/{delivery_id}/ack", response_model=DeliveryStatusResponse)
def ack_delivery(
    delivery_id: str,
    body: DeliveryAckRequest,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_db),
) -> DeliveryStatusResponse:
    try:
        row = DeliveryOutbox(session, settings.delivery_max_attempts).ack(
            delivery_id,
            body.lease_token,
            sent_at=body.sent_at,
            platform_message_id=body.platform_message_id,
        )
        session.commit()
        return _status(row)
    except LeaseConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{delivery_id}/fail", response_model=DeliveryStatusResponse)
def fail_delivery(
    delivery_id: str,
    body: DeliveryFailRequest,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_db),
) -> DeliveryStatusResponse:
    try:
        row = DeliveryOutbox(session, settings.delivery_max_attempts).fail(
            delivery_id,
            body.lease_token,
            error_code=body.error_code,
            retryable=body.retryable,
        )
        session.commit()
        return _status(row)
    except LeaseConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
