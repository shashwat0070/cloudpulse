import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("CLOUDPULSE_DEMO_MODE", raising=False)
    app.state.failed = False

    with TestClient(app) as test_client:
        yield test_client

    app.state.failed = False


def test_service_starts_healthy(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_failure_and_reset(client, monkeypatch):
    monkeypatch.setenv("CLOUDPULSE_DEMO_MODE", "true")

    assert client.post("/demo/fail").status_code == 200

    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "unhealthy"

    assert client.post("/demo/reset").status_code == 200

    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.parametrize(
    "endpoint,initial_failure",
    [
        ("/demo/fail", False),
        ("/demo/reset", True),
    ],
)
def test_demo_controls_disabled_by_default(
    client, endpoint, initial_failure
):
    app.state.failed = initial_failure

    response = client.post(endpoint)

    assert response.status_code == 404
    assert app.state.failed == initial_failure