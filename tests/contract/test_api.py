from fastapi.testclient import TestClient

from eventserver.config import Settings
from eventserver.main import create_app


def test_health_is_public_and_versioned(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "request-123"})
    assert response.status_code == 200
    assert response.json()["status"] == "alive"
    assert response.headers["X-Request-ID"] == "request-123"


def test_unknown_user_has_explicit_closed_permissions(client: TestClient) -> None:
    response = client.get("/v1/users/unknown/permission")
    assert response.status_code == 200
    assert response.json() == {
        "platform": "qqbot",
        "openid": "unknown",
        "account_status": "unknown",
        "role": "user",
        "permissions": {"chat": False, "command": False},
    }


def test_validation_errors_have_stable_shape(client: TestClient) -> None:
    response = client.post(
        "/v1/deliveries/claim",
        json={"worker_id": "", "platform": "qqbot", "limit": 0},
    )
    assert response.status_code == 422
    assert set(response.json()) == {"code", "message", "request_id"}


def test_internal_endpoint_rejects_missing_service_token() -> None:
    app = create_app(Settings(internal_api_token="a" * 32))
    with TestClient(app) as unauthenticated:
        response = unauthenticated.get("/v1/events")
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
