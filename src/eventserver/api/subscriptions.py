from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from eventserver.api.schemas import (
    DeleteSubscriptionResponse,
    SubscriptionRequest,
    SubscriptionResponse,
)
from eventserver.auth.service import require_service_auth
from eventserver.db.session import get_db
from eventserver.services.subscriptions import (
    EventNotFoundError,
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
        SubscriptionResponse(event_key=item.event_key, locale=item.locale)
        for item in list_subscriptions(session, platform, openid)
    ]


@router.post("", response_model=SubscriptionResponse)
def add_subscription(
    openid: str,
    body: SubscriptionRequest,
    platform: str = "qqbot",
    session: Session = Depends(get_db),
) -> SubscriptionResponse:
    try:
        item, created = subscribe(session, platform, openid, body.event_key)
        session.commit()
        return SubscriptionResponse(event_key=item.event_key, locale=item.locale, created=created)
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except EventNotFoundError as exc:
        raise HTTPException(status_code=404, detail="event is not available") from exc


@router.delete("/{event_key}", response_model=DeleteSubscriptionResponse)
def remove_subscription(
    openid: str,
    event_key: str,
    platform: str = "qqbot",
    session: Session = Depends(get_db),
) -> DeleteSubscriptionResponse:
    try:
        deleted = unsubscribe(session, platform, openid, event_key)
        session.commit()
        return DeleteSubscriptionResponse(event_key=event_key, deleted=deleted)
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
