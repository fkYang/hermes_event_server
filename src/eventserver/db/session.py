from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from eventserver.config import get_settings


def build_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().database_url
    options: dict[str, object] = {"pool_pre_ping": True}
    if url.startswith("mysql"):
        options.update(
            pool_recycle=1800,
            isolation_level="READ COMMITTED",
            connect_args={"connect_timeout": 5, "read_timeout": 10, "write_timeout": 10},
        )
    return create_engine(url, **options)


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
