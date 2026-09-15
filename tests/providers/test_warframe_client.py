import json

import httpx

from eventserver.providers.warframe.client import WarframeWorldStateClient, WorldStateError


def test_client_sets_user_agent_and_parses_object() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/cdn/worldState.php"
        assert request.headers["User-Agent"].startswith("AutoQQ-EventServer/")
        return httpx.Response(200, json={"Events": []})

    client = WarframeWorldStateClient(transport=httpx.MockTransport(handler))
    assert client.fetch() == {"Events": []}


def test_client_limits_response_size_and_retries() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(200, content=json.dumps({"data": "x" * 100}).encode())

    client = WarframeWorldStateClient(
        max_response_bytes=20,
        max_attempts=2,
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _: None,
    )
    try:
        client.fetch()
    except WorldStateError:
        pass
    else:
        raise AssertionError("oversized response was accepted")
    assert attempts == 2
