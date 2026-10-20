from fastapi.testclient import TestClient

from lumen.config import Settings
from lumen.main import create_app


def test_health_returns_ok() -> None:
    client = TestClient(create_app(Settings(environment="test")))

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]
