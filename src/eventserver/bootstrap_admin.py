from __future__ import annotations

import getpass
import sys
from collections.abc import Callable
from typing import TextIO

from sqlalchemy import Engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from eventserver.db.session import engine
from eventserver.services.bootstrap_admin import (
    FirstAdminBootstrapError,
    bootstrap_first_admin,
)

LOCK_NAME = "autoqq:first-admin-bootstrap:v1"
LOCK_TIMEOUT_SECONDS = 10


class FirstAdminBootstrapBusyError(RuntimeError):
    pass


def _acquire_lock(connection: Connection) -> bool:
    if connection.dialect.name != "mysql":
        return False
    acquired = connection.scalar(
        text("SELECT GET_LOCK(:lock_name, :timeout_seconds)"),
        {"lock_name": LOCK_NAME, "timeout_seconds": LOCK_TIMEOUT_SECONDS},
    )
    connection.commit()
    if acquired != 1:
        raise FirstAdminBootstrapBusyError("another first-admin bootstrap is in progress")
    return True


def _release_lock(connection: Connection) -> None:
    try:
        if connection.in_transaction():
            connection.rollback()
        connection.execute(text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": LOCK_NAME})
        connection.commit()
    except SQLAlchemyError:
        connection.invalidate()


def bootstrap_first_admin_with_engine(
    database_engine: Engine, *, code: str, platform: str = "qqbot"
):
    with database_engine.connect() as connection:
        locked = _acquire_lock(connection)
        try:
            with Session(bind=connection) as session, session.begin():
                return bootstrap_first_admin(session, code=code, platform=platform)
        finally:
            if locked:
                _release_lock(connection)


def run_cli(
    *,
    database_engine: Engine = engine,
    code_reader: Callable[[str], str] = getpass.getpass,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    try:
        code = code_reader("Pairing code: ")
    except (EOFError, KeyboardInterrupt):
        print("First administrator bootstrap cancelled.", file=stderr)
        return 2

    try:
        bootstrap_first_admin_with_engine(database_engine, code=code)
    except (FirstAdminBootstrapError, FirstAdminBootstrapBusyError) as exc:
        print(f"First administrator bootstrap failed: {exc}", file=stderr)
        return 1
    except SQLAlchemyError:
        print("First administrator bootstrap failed: database operation failed", file=stderr)
        return 1

    print("First administrator initialized successfully.", file=stdout)
    return 0


def main() -> None:
    raise SystemExit(run_cli())


if __name__ == "__main__":
    main()
