import hashlib
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from eventserver.auth.service import bearer
from eventserver.db.models import EventPublisher
from eventserver.db.session import get_db


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def require_publisher_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_db),
) -> EventPublisher:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="invalid publisher credentials")
    supplied_hash = token_hash(credentials.credentials)
    rows = session.query(EventPublisher).where(EventPublisher.enabled.is_(True)).all()
    for publisher in rows:
        if secrets.compare_digest(supplied_hash, publisher.token_hash):
            return publisher
    raise HTTPException(status_code=401, detail="invalid publisher credentials")


PublisherIdentity = Annotated[EventPublisher, Depends(require_publisher_auth)]
