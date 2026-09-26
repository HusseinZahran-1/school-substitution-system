from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.main import app


def test_first_admin_setup_logout_and_login(db: Session):
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        status = client.get("/api/auth/status")
        assert status.status_code == 200
        assert status.json()["setup_required"] is True

        setup = client.post("/api/auth/setup", json={
            "username": "school-admin",
            "password": "test-password-123",
            "confirm_password": "test-password-123",
        })
        assert setup.status_code == 201, setup.text
        assert client.get("/api/auth/status").json()["authenticated"] is True

        assert client.post("/api/auth/logout").status_code == 200
        assert client.get("/api/auth/status").json()["authenticated"] is False

        login = client.post("/api/auth/login", json={
            "username": "school-admin",
            "password": "test-password-123",
        })
        assert login.status_code == 200, login.text
        assert client.get("/api/auth/status").json()["authenticated"] is True
    finally:
        app.dependency_overrides.clear()
