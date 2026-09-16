from datetime import timedelta
from io import StringIO

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from eventserver.bootstrap_admin import run_cli
from eventserver.core.models import utc_now
from eventserver.db.models import AuditLog, PairingCode, User, UserPermission
from eventserver.services.bootstrap_admin import (
    FirstAdminBootstrapError,
    bootstrap_first_admin,
)
from eventserver.services.pairing import create_pairing_code


def create_code(
    session_factory: sessionmaker[Session], *, openid: str = "first-admin-openid"
) -> str:
    with session_factory.begin() as session:
        code, _ = create_pairing_code(session, "qqbot", openid)
        return code


def test_bootstrap_first_admin_consumes_code_and_audits(
    session_factory: sessionmaker[Session],
) -> None:
    code = create_code(session_factory)

    with session_factory.begin() as session:
        snapshot = bootstrap_first_admin(session, code=code)

    assert snapshot.account_status == "active"
    assert snapshot.role == "admin"
    assert snapshot.chat is True
    assert snapshot.command is True

    with session_factory() as session:
        pairing = session.scalar(select(PairingCode))
        assert pairing is not None
        assert pairing.consumed_at is not None
        assert pairing.approved_at is not None
        assert pairing.approved_by == "bootstrap"
        audit = session.scalar(select(AuditLog))
        assert audit is not None
        assert audit.action == "bootstrap_first_admin"
        assert audit.target_id_masked == "fir***nid"
        assert code not in str(audit.details)


def test_bootstrap_rejects_invalid_expired_and_consumed_codes(
    session_factory: sessionmaker[Session],
) -> None:
    for state in ("invalid", "expired", "consumed"):
        code = "BAD-CODE"
        if state != "invalid":
            code = create_code(session_factory, openid=f"{state}-openid")
            with session_factory.begin() as session:
                pairing = session.scalar(
                    select(PairingCode).where(PairingCode.openid == f"{state}-openid")
                )
                assert pairing is not None
                if state == "expired":
                    pairing.expires_at = utc_now() - timedelta(seconds=1)
                else:
                    pairing.consumed_at = utc_now()

        with session_factory.begin() as session:
            try:
                bootstrap_first_admin(session, code=code)
            except FirstAdminBootstrapError as exc:
                assert "invalid, expired, or already consumed" in str(exc)
            else:
                raise AssertionError(f"{state} pairing code was accepted")


def test_bootstrap_refuses_when_effective_admin_exists(
    session_factory: sessionmaker[Session],
) -> None:
    code = create_code(session_factory)
    with session_factory.begin() as session:
        session.add(User(platform="qqbot", openid="existing-admin", role="admin"))
        session.add(
            UserPermission(
                platform="qqbot",
                openid="existing-admin",
                permission_key="command",
                granted=True,
            )
        )

    with session_factory.begin() as session:
        try:
            bootstrap_first_admin(session, code=code)
        except FirstAdminBootstrapError as exc:
            assert str(exc) == "an active administrator already exists"
        else:
            raise AssertionError("a second effective administrator was bootstrapped")

    with session_factory() as session:
        pairing = session.scalar(
            select(PairingCode).where(PairingCode.openid == "first-admin-openid")
        )
        assert pairing is not None
        assert pairing.consumed_at is None


def test_bootstrap_rejects_blocked_pairing_target(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory.begin() as session:
        session.add(User(platform="qqbot", openid="blocked-openid", account_status="blocked"))
    code = create_code(session_factory, openid="blocked-openid")

    with session_factory.begin() as session:
        try:
            bootstrap_first_admin(session, code=code)
        except FirstAdminBootstrapError as exc:
            assert str(exc) == "the pairing target is blocked"
        else:
            raise AssertionError("a blocked user was bootstrapped")

    with session_factory() as session:
        user = session.get(User, ("qqbot", "blocked-openid"))
        pairing = session.scalar(select(PairingCode).where(PairingCode.openid == "blocked-openid"))
        assert user is not None and user.account_status == "blocked"
        assert pairing is not None and pairing.consumed_at is None


def test_cli_reads_code_interactively_without_echoing_secrets(
    session_factory: sessionmaker[Session],
) -> None:
    openid = "private-first-admin-openid"
    code = create_code(session_factory, openid=openid)
    stdout = StringIO()
    stderr = StringIO()
    database_engine = session_factory.kw["bind"]

    result = run_cli(
        database_engine=database_engine,
        code_reader=lambda prompt: code,
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    output = stdout.getvalue() + stderr.getvalue()
    assert "initialized successfully" in output
    assert code not in output
    assert openid not in output


def test_cli_failure_does_not_echo_the_submitted_code(
    session_factory: sessionmaker[Session],
) -> None:
    code = "ABCDEFGH"
    stdout = StringIO()
    stderr = StringIO()

    result = run_cli(
        database_engine=session_factory.kw["bind"],
        code_reader=lambda prompt: code,
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 1
    output = stdout.getvalue() + stderr.getvalue()
    assert "invalid, expired, or already consumed" in output
    assert code not in output
