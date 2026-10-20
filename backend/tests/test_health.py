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


def test_relative_upload_dir_is_resolved_from_backend() -> None:
    from lumen.config import BACKEND_DIR, REPO_DIR

    relative = Settings(_env_file=None, upload_dir="../data/uploads")  # type: ignore[arg-type]

    assert relative.upload_dir == REPO_DIR / "data" / "uploads"
    assert Settings(_env_file=None).upload_dir == REPO_DIR / "data" / "uploads"
    assert BACKEND_DIR.name == "backend"
