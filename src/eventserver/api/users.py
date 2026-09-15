from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from eventserver.api.helpers import permission_response
from eventserver.api.schemas import PermissionChangeRequest, PermissionResponse, RoleChangeRequest
from eventserver.auth.service import require_service_auth
from eventserver.db.session import get_db
from eventserver.services.users import (
    AuthorizationError,
    LastAdminError,
    change_role,
    permission_snapshot,
    set_permissions,
)

router = APIRouter(prefix="/v1/users", tags=["users"], dependencies=[Depends(require_service_auth)])


@router.get("/{openid}/permission", response_model=PermissionResponse)
def get_permission(
    openid: str, platform: str = "qqbot", session: Session = Depends(get_db)
) -> PermissionResponse:
    return permission_response(permission_snapshot(session, platform, openid))


def _set_permission(
    request: Request,
    openid: str,
    body: PermissionChangeRequest,
    granted: bool,
    platform: str,
    session: Session,
) -> PermissionResponse:
    try:
        snapshot = set_permissions(
            session,
            platform=platform,
            openid=openid,
            permissions=set(body.permissions),
            granted=granted,
            operator_openid=body.operator_openid,
            request_id=request.state.request_id,
        )
        session.commit()
        return permission_response(snapshot)
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LastAdminError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{openid}/grant", response_model=PermissionResponse)
def grant_permissions(
    request: Request,
    openid: str,
    body: PermissionChangeRequest,
    platform: str = "qqbot",
    session: Session = Depends(get_db),
) -> PermissionResponse:
    return _set_permission(request, openid, body, True, platform, session)


@router.post("/{openid}/revoke", response_model=PermissionResponse)
def revoke_permissions(
    request: Request,
    openid: str,
    body: PermissionChangeRequest,
    platform: str = "qqbot",
    session: Session = Depends(get_db),
) -> PermissionResponse:
    return _set_permission(request, openid, body, False, platform, session)


@router.post("/{openid}/role", response_model=PermissionResponse)
def update_role(
    request: Request,
    openid: str,
    body: RoleChangeRequest,
    platform: str = "qqbot",
    session: Session = Depends(get_db),
) -> PermissionResponse:
    try:
        snapshot = change_role(
            session,
            platform=platform,
            openid=openid,
            role=body.role,
            operator_openid=body.operator_openid,
            request_id=request.state.request_id,
        )
        session.commit()
        return permission_response(snapshot)
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LastAdminError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
