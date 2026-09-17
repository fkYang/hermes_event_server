from datetime import UTC, datetime, timedelta

from fastapi import HTTPException

from eventserver.api.schemas import PermissionResponse, PermissionValues
from eventserver.config import Settings
from eventserver.core.models import utc_now
from eventserver.services.users import PermissionSnapshot


def resolve_notify_at(notify_at: datetime | None, settings: Settings) -> datetime | None:
    """Return the UTC delivery time, or None to deliver as soon as possible."""
    if notify_at is None:
        return None
    value = notify_at.astimezone(UTC)
    now = utc_now()
    if value <= now:
        return now
    horizon = now + timedelta(seconds=settings.delivery_max_schedule_horizon_seconds)
    if value > horizon:
        raise HTTPException(
            status_code=422, detail="notify_at is beyond the configured scheduling horizon"
        )
    return value


def permission_response(snapshot: PermissionSnapshot) -> PermissionResponse:
    return PermissionResponse(
        platform=snapshot.platform,
        openid=snapshot.openid,
        account_status=snapshot.account_status,
        role=snapshot.role,
        permissions=PermissionValues(chat=snapshot.chat, command=snapshot.command),
    )
