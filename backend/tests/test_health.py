"""Tests for FastAPI backend application health endpoint and startup initialization."""

from pathlib import Path
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import ensure_workspace_directories, SESSIONS_DIR


def test_health_endpoint():
    """Verify that GET /health returns HTTP 200 with status ok."""
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_workspace_directories_creation(tmp_path: Path):
    """Verify that ensure_workspace_directories creates the required storage folders."""
    custom_dir = tmp_path / "test_workspace"
    sessions_path = ensure_workspace_directories(base_dir=custom_dir)
    assert sessions_path.exists()
    assert sessions_path.is_dir()
    assert sessions_path.name == "sessions"


def test_startup_creates_default_sessions_dir():
    """Verify default sessions directory is created on app startup."""
    with TestClient(app):
        assert SESSIONS_DIR.exists()
        assert SESSIONS_DIR.is_dir()
