from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from eventserver.auth.service import require_service_auth
from eventserver.config import Settings
from eventserver.db.base import Base
from eventserver.db.session import get_db
from eventserver.main import create_app


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as value:
        yield value


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    settings = Settings(internal_api_token="a" * 32)
    app = create_app(settings)

    def override_db() -> Iterator[Session]:
        with session_factory() as value:
            yield value

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_service_auth] = lambda: None
    with TestClient(app) as test_client:
        yield test_client
