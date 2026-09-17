"""Local administrator tool for DB-backed event catalog entries.

This is deliberately a local deployment operation: normal users and publishers
cannot create event types or upload executable rules.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from eventserver.core.schema_validation import PayloadSchemaError, validate_payload
from eventserver.db.models import EventType
from eventserver.db.session import SessionLocal


class MatchKeyOption(BaseModel):
    key: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,64}$", max_length=64)
    label: str = Field(min_length=1, max_length=100)


class CatalogEntry(BaseModel):
    event_key: str = Field(pattern=r"^[a-z0-9]+(?:\.[a-z0-9_]+){2,}$", max_length=128)
    display_name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    schema_version: int = Field(default=1, ge=1)
    payload_schema: dict[str, object] = Field(default_factory=dict)
    subscribable: bool = True
    match_key_field: str | None = Field(default=None, pattern=r"^[a-z0-9_]{1,64}$", max_length=64)
    match_key_options: list[MatchKeyOption] = Field(default_factory=list, max_length=64)
    match_keys_required: bool = False

    @model_validator(mode="after")
    def validate_match_keys(self) -> CatalogEntry:
        keys = [option.key for option in self.match_key_options]
        if len(keys) != len(set(keys)):
            raise ValueError("match_key_options keys must be unique")
        if self.match_key_options and not self.match_key_field:
            raise ValueError("match_key_options require match_key_field")
        if self.match_key_field and not self.match_key_options:
            raise ValueError("match_key_field requires match_key_options")
        if self.match_keys_required and not self.match_key_field:
            raise ValueError("match_keys_required requires match_key_field")
        if self.match_keys_required and not self.match_key_options:
            raise ValueError("match_keys_required requires match_key_options")
        return self


def register(entry: CatalogEntry) -> None:
    try:
        validate_payload(entry.payload_schema, {})
    except PayloadSchemaError as exc:
        if "missing required fields" not in str(exc):
            raise ValueError(f"invalid payload schema: {exc}") from exc
    with SessionLocal() as session:
        existing = session.get(EventType, entry.event_key)
        if existing is not None and existing.schema_version != entry.schema_version:
            raise ValueError(
                "schema_version changes require a new event key or an explicit migration"
            )
        if existing is None:
            existing = EventType(event_key=entry.event_key, display_name=entry.display_name)
            session.add(existing)
        existing.display_name = entry.display_name
        existing.description = entry.description
        existing.schema_version = entry.schema_version
        existing.payload_schema = entry.payload_schema
        existing.subscribable = entry.subscribable
        existing.match_key_field = entry.match_key_field
        existing.match_key_options = [option.model_dump() for option in entry.match_key_options]
        existing.match_keys_required = entry.match_keys_required
        existing.enabled = True
        existing.deprecated_at = None
        session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the EventServer event catalog")
    subparsers = parser.add_subparsers(dest="command", required=True)
    register_parser = subparsers.add_parser("register")
    register_parser.add_argument("--file", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "register":
        payload = json.loads(args.file.read_text(encoding="utf-8"))
        register(CatalogEntry.model_validate(payload))
        print("event catalog entry registered")


if __name__ == "__main__":
    main()
