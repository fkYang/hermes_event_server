from collections.abc import Callable
from time import sleep

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

MYSQL_RETRIABLE_TRANSACTION_ERRORS = frozenset({1205, 1213})


def mysql_error_code(exc: OperationalError) -> int | None:
    args = getattr(exc.orig, "args", ())
    return args[0] if args and isinstance(args[0], int) else None


def run_with_deadlock_retry[T](
    session_factory: sessionmaker[Session],
    operation: Callable[[Session], T],
    *,
    max_attempts: int = 3,
    base_delay_seconds: float = 0.05,
    sleep_fn: Callable[[float], None] = sleep,
) -> T:
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    for attempt in range(max_attempts):
        try:
            with session_factory() as session, session.begin():
                return operation(session)
        except OperationalError as exc:
            if (
                mysql_error_code(exc) not in MYSQL_RETRIABLE_TRANSACTION_ERRORS
                or attempt + 1 >= max_attempts
            ):
                raise
            sleep_fn(base_delay_seconds * (2**attempt))
    raise AssertionError("unreachable")
