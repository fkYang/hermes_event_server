"""Local administrator tool for onboarding or rotating external publishers."""

from __future__ import annotations

import argparse
import os
import re

from eventserver.auth.publisher import token_hash
from eventserver.db.models import EventPublisher
from eventserver.db.session import SessionLocal

PREFIX_RE = re.compile(r"^[a-z0-9]+(?:\.[a-z0-9_]+)*\.$")


def upsert(publisher_key: str, token: str, prefixes: list[str], description: str) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,63}", publisher_key):
        raise ValueError("publisher key has an invalid format")
    if len(token) < 32:
        raise ValueError("publisher token must contain at least 32 characters")
    if not prefixes or any(PREFIX_RE.fullmatch(prefix) is None for prefix in prefixes):
        raise ValueError(
            "each allowed prefix must end with a dot and contain only event-key syntax"
        )
    with SessionLocal() as session:
        row = session.get(EventPublisher, publisher_key)
        if row is None:
            row = EventPublisher(publisher_key=publisher_key, token_hash=token_hash(token))
            session.add(row)
        row.token_hash = token_hash(token)
        row.allowed_event_prefixes = sorted(set(prefixes))
        row.description = description
        row.enabled = True
        session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage EventServer external publishers")
    parser.add_argument("--publisher-key", required=True)
    parser.add_argument("--token-env", required=True)
    parser.add_argument("--allow-prefix", action="append", required=True)
    parser.add_argument("--description", default="")
    args = parser.parse_args()
    token = os.environ.get(args.token_env, "")
    if not token:
        raise SystemExit(f"token environment variable {args.token_env!r} is not set")
    upsert(args.publisher_key, token, args.allow_prefix, args.description)
    print("publisher configured")


if __name__ == "__main__":
    main()
