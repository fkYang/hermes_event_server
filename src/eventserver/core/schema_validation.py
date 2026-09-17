"""Small, non-executable JSON Schema subset for dynamic event payloads.

The catalog is administrator managed.  This intentionally supports only structural
validation, never expressions, code, references, or remote schemas.
"""

from __future__ import annotations

import re
from typing import Any


class PayloadSchemaError(ValueError):
    pass


def validate_payload(schema: dict[str, Any], value: dict[str, Any]) -> None:
    if not schema:
        return
    _validate(schema, value, "$")


def _validate(schema: dict[str, Any], value: Any, path: str) -> None:
    if not isinstance(schema, dict):
        raise PayloadSchemaError("payload schema must be an object")
    schema_type = schema.get("type")
    if schema_type is not None and not _matches_type(schema_type, value):
        raise PayloadSchemaError(f"{path} must be {schema_type}")
    if "const" in schema and value != schema["const"]:
        raise PayloadSchemaError(f"{path} must equal the configured const")
    if "enum" in schema:
        options = schema["enum"]
        if not isinstance(options, list) or value not in options:
            raise PayloadSchemaError(f"{path} is not an allowed value")
    if isinstance(value, dict):
        _validate_object(schema, value, path)
    elif isinstance(value, list):
        _validate_array(schema, value, path)
    elif isinstance(value, str):
        _validate_string(schema, value, path)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        _validate_number(schema, value, path)


def _matches_type(schema_type: object, value: Any) -> bool:
    choices = schema_type if isinstance(schema_type, list) else [schema_type]
    if not all(isinstance(item, str) for item in choices):
        raise PayloadSchemaError("schema type must be a string or list of strings")
    return any(
        {
            "object": lambda: isinstance(value, dict),
            "array": lambda: isinstance(value, list),
            "string": lambda: isinstance(value, str),
            "number": lambda: isinstance(value, (int, float)) and not isinstance(value, bool),
            "integer": lambda: isinstance(value, int) and not isinstance(value, bool),
            "boolean": lambda: isinstance(value, bool),
            "null": lambda: value is None,
        }.get(choice, _unknown_type)()
        for choice in choices
    )


def _unknown_type() -> bool:
    raise PayloadSchemaError("unsupported schema type")


def _validate_object(schema: dict[str, Any], value: dict[str, Any], path: str) -> None:
    required = schema.get("required", [])
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        raise PayloadSchemaError("schema required must be a string list")
    missing = [item for item in required if item not in value]
    if missing:
        raise PayloadSchemaError(f"{path} is missing required fields: {', '.join(missing)}")
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise PayloadSchemaError("schema properties must be an object")
    if schema.get("additionalProperties") is False:
        unknown = set(value) - set(properties)
        if unknown:
            raise PayloadSchemaError(f"{path} has undeclared fields: {', '.join(sorted(unknown))}")
    for name, child_schema in properties.items():
        if name in value:
            _validate(child_schema, value[name], f"{path}.{name}")


def _validate_array(schema: dict[str, Any], value: list[Any], path: str) -> None:
    _bounded_length(schema, len(value), path)
    item_schema = schema.get("items")
    if item_schema is not None:
        for index, item in enumerate(value):
            _validate(item_schema, item, f"{path}[{index}]")


def _validate_string(schema: dict[str, Any], value: str, path: str) -> None:
    _bounded_length(schema, len(value), path)
    pattern = schema.get("pattern")
    if pattern is not None:
        if not isinstance(pattern, str) or len(pattern) > 256:
            raise PayloadSchemaError("schema pattern must be a string up to 256 characters")
        if re.search(pattern, value) is None:
            raise PayloadSchemaError(f"{path} does not match the configured pattern")


def _validate_number(schema: dict[str, Any], value: int | float, path: str) -> None:
    minimum = schema.get("minimum")
    maximum = schema.get("maximum")
    if minimum is not None and (not isinstance(minimum, (int, float)) or value < minimum):
        raise PayloadSchemaError(f"{path} is below the configured minimum")
    if maximum is not None and (not isinstance(maximum, (int, float)) or value > maximum):
        raise PayloadSchemaError(f"{path} exceeds the configured maximum")


def _bounded_length(schema: dict[str, Any], length: int, path: str) -> None:
    minimum = schema.get("minLength", schema.get("minItems"))
    maximum = schema.get("maxLength", schema.get("maxItems"))
    if minimum is not None and (not isinstance(minimum, int) or length < minimum):
        raise PayloadSchemaError(f"{path} is shorter than the configured minimum")
    if maximum is not None and (not isinstance(maximum, int) or length > maximum):
        raise PayloadSchemaError(f"{path} exceeds the configured maximum")
