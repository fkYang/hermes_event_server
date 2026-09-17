from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from eventserver.api.schemas import (
    DeleteSubscriptionResponse,
    SubscriptionRequest,
    SubscriptionResponse,
)
from eventserver.auth.service import require_service_auth
from eventserver.db.models import AuditLog
from eventserver.db.session import get_db
from eventserver.services.common import mask_identifier
from eventserver.services.subscriptions import (
    EventNotFoundError,
    InvalidMatchKeyError,
    list_subscriptions,
    subscribe,
    unsubscribe,
)
from eventserver.services.users import AuthorizationError

router = APIRouter(
    prefix="/v1/users/{openid}/subscriptions",
    tags=["subscriptions"],
    dependencies=[Depends(require_service_auth)],
)


@router.get("", response_model=list[SubscriptionResponse])
def get_subscriptions(
    openid: str, platform: str = "qqbot", session: Session = Depends(get_db)
) -> list[SubscriptionResponse]:
    return [
        SubscriptionResponse(
            event_key=item.event_key, locale=item.locale, match_keys=list(item.match_keys or [])
        )
        for item in list_subscriptions(session, platform, openid)
    ]


@router.post("", response_model=SubscriptionResponse)
def add_subscription(
    request: Request,
    openid: str,
    body: SubscriptionRequest,
    platform: str = "qqbot",
    session: Session = Depends(get_db),
) -> SubscriptionResponse:
    try:
        item, created, updated = subscribe(
            session, platform, openid, body.event_key, body.match_keys
        )
        session.add(
            AuditLog(
                actor_platform=platform,
                actor_openid_masked=mask_identifier(openid),
                target_type="subscription",
                target_id_masked=mask_identifier(openid),
                action="subscribe" if created else "update_subscription",
                result="success",
                request_id=request.state.request_id,
                details={"event_key": item.event_key, "match_keys": list(item.match_keys or [])},
            )
        )
        session.commit()
        return SubscriptionResponse(
            event_key=item.event_key,
            locale=item.locale,
            match_keys=list(item.match_keys or []),
            created=created,
            updated=updated,
        )
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except InvalidMatchKeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EventNotFoundError as exc:
        raise HTTPException(status_code=404, detail="event is not available") from exc


@router.delete("/{event_key}", response_model=DeleteSubscriptionResponse)
def remove_subscription(
    request: Request,
    openid: str,
    event_key: str,
    platform: str = "qqbot",
    session: Session = Depends(get_db),
) -> DeleteSubscriptionResponse:
    try:
        deleted = unsubscribe(session, platform, openid, event_key)
        session.add(
            AuditLog(
                actor_platform=platform,
                actor_openid_masked=mask_identifier(openid),
                target_type="subscription",
                target_id_masked=mask_identifier(openid),
                action="unsubscribe",
                result="success" if deleted else "noop",
                request_id=request.state.request_id,
                details={"event_key": event_key},
            )
        )
        session.commit()
        return DeleteSubscriptionResponse(event_key=event_key, deleted=deleted)
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
