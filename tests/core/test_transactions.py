from sqlalchemy.exc import OperationalError

from eventserver.db.transactions import run_with_deadlock_retry


def test_deadlock_is_retried_with_a_fresh_transaction(session_factory) -> None:
    attempts = 0
    delays: list[float] = []

    def operation(session):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OperationalError("SELECT 1", {}, Exception(1213, "deadlock"))
        return session.execute

    result = run_with_deadlock_retry(
        session_factory,
        operation,
        max_attempts=3,
        base_delay_seconds=0.01,
        sleep_fn=delays.append,
    )
    assert result is not None
    assert attempts == 2
    assert delays == [0.01]


def test_non_retriable_database_error_is_not_repeated(session_factory) -> None:
    attempts = 0

    def operation(session):
        nonlocal attempts
        attempts += 1
        raise OperationalError("SELECT 1", {}, Exception(1045, "access denied"))

    try:
        run_with_deadlock_retry(session_factory, operation, sleep_fn=lambda _: None)
    except OperationalError:
        pass
    else:
        raise AssertionError("non-retriable error was swallowed")
    assert attempts == 1
