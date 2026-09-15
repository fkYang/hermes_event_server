import secrets

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from eventserver.config import Settings, get_settings

bearer = HTTPBearer(auto_error=False)


def require_service_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.internal_api_token:
        raise HTTPException(status_code=503, detail="internal API token is not configured")
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not secrets.compare_digest(credentials.credentials, settings.internal_api_token)
    ):
        raise HTTPException(status_code=401, detail="invalid service credentials")
