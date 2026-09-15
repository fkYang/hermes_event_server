from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from eventserver.api.helpers import permission_response
from eventserver.api.schemas import (
    PairingApproveRequest,
    PairingCodeRequest,
    PairingCodeResponse,
    PermissionResponse,
)
from eventserver.auth.service import require_service_auth
from eventserver.db.session import get_db
from eventserver.services.pairing import PairingCodeError, approve_pairing_code, create_pairing_code
from eventserver.services.users import AuthorizationError

router = APIRouter(
    prefix="/v1/pairing-codes", tags=["pairing"], dependencies=[Depends(require_service_auth)]
)


@router.post("", response_model=PairingCodeResponse)
def new_pairing_code(
    body: PairingCodeRequest, session: Session = Depends(get_db)
) -> PairingCodeResponse:
    code, row = create_pairing_code(session, body.platform, body.openid)
    session.commit()
    return PairingCodeResponse(code=code, expires_at=row.expires_at)


@router.post("/{code}/approve", response_model=PermissionResponse)
def approve_code(
    request: Request,
    code: str,
    body: PairingApproveRequest,
    session: Session = Depends(get_db),
) -> PermissionResponse:
    try:
        snapshot = approve_pairing_code(
            session,
            code=code,
            permissions=set(body.permissions),
            operator_openid=body.operator_openid,
            platform=body.platform,
            request_id=request.state.request_id,
        )
        session.commit()
        return permission_response(snapshot)
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PairingCodeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
