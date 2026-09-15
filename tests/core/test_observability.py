import json
import logging

from eventserver.observability import JsonFormatter, redact_text


def test_redaction_removes_common_secret_values() -> None:
    text = 'Authorization: Bearer abc.def token="value" password="p@ss"'
    redacted = redact_text(text)
    assert "abc.def" not in redacted
    assert 'token="value"' not in redacted
    assert 'password="p@ss"' not in redacted


def test_json_formatter_keeps_structured_request_context() -> None:
    record = logging.LogRecord("eventserver", logging.INFO, __file__, 1, "done", (), None)
    record.request_id = "request-1"
    record.route = "/v1/users/{openid}/permission"
    output = json.loads(JsonFormatter().format(record))
    assert output["request_id"] == "request-1"
    assert output["route"] == "/v1/users/{openid}/permission"
