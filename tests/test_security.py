import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app import models, security
from backend.app.database import get_db
from backend.app.main import app


@pytest.fixture(autouse=True)
def clear_auth_rate_limits():
    with security._RATE_LOCK:
        security._RATE_ATTEMPTS.clear()
    yield
    with security._RATE_LOCK:
        security._RATE_ATTEMPTS.clear()


@pytest.fixture
def auth_client(db: Session):
    def override_db():
        # A real request gets a fresh Session; clear the tenant context when this
        # fixture reuses one Session across multiple HTTP requests.
        db.info.pop("school_id", None)
        yield db

    app.dependency_overrides.pop(security.require_admin, None)
    app.dependency_overrides[get_db] = override_db
    try:
        yield TestClient(app, headers={"Origin": "http://testserver"})
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_register_email_license_activation_and_normal_login(auth_client, db, monkeypatch):
    delivered = []
    notifications = []
    monkeypatch.setattr(security.settings, "email_host", "smtp.example.test")
    monkeypatch.setattr(security.settings, "email_from", "noreply@example.test")
    monkeypatch.setattr(security, "send_activation_email", lambda email, key: delivered.append((email, key)))
    monkeypatch.setattr(security, "_notify_discord", notifications.append)

    status = auth_client.get("/api/auth/status").json()
    assert status["registration_available"] is True
    assert status["setup_required"] is True

    payload = {
        "username": "Hussein_1",
        "email": "Hussein@example.com",
        "password": "strong-password-123",
        "confirm_password": "strong-password-123",
    }
    registered = auth_client.post("/api/auth/register", json=payload)
    assert registered.status_code == 201, registered.text
    assert registered.json()["activation_required"] is True
    assert "license" not in registered.text.lower()
    assert len(delivered) == 1
    delivered_email, activation_key = delivered[0]
    assert delivered_email == "hussein@example.com"
    assert activation_key.count("-") == 3

    user = db.scalar(select(models.AdminAccount).where(models.AdminAccount.username == "hussein_1"))
    license_row = db.scalar(select(models.LicenseKey))
    assert user and user.email == "hussein@example.com"
    assert user.password_hash.startswith("$argon2id$")
    assert activation_key.replace("-", "") not in user.password_hash
    assert license_row and license_row.status == "UNUSED"
    assert license_row.key_hash != activation_key
    assert activation_key not in registered.text
    assert activation_key in notifications[0]

    duplicate_username = auth_client.post("/api/auth/register", json={**payload, "email": "second@example.com"})
    assert duplicate_username.status_code == 409
    duplicate_email = auth_client.post("/api/auth/register", json={**payload, "username": "second_user"})
    assert duplicate_email.status_code == 409
    whitespace_username = auth_client.post("/api/auth/register", json={**payload, "username": "hus sein"})
    assert whitespace_username.status_code == 422

    bad_login = auth_client.post("/api/auth/login", json={"username": "hussein_1", "password": "incorrect123"})
    assert bad_login.status_code == 401
    login = auth_client.post("/api/auth/login", json={"username": "HUSSEIN_1", "password": payload["password"]})
    assert login.status_code == 200
    assert login.json()["activation_required"] is True
    assert auth_client.get("/api/auth/status").json()["activation_required"] is True
    assert auth_client.get("/api/teachers").status_code == 401

    wrong_key = auth_client.post("/api/auth/activate-license", json={"license_key": "AAAA-AAAA-AAAA-AAAA"})
    assert wrong_key.status_code == 400
    activated = auth_client.post("/api/auth/activate-license", json={"license_key": activation_key.lower()})
    assert activated.status_code == 200, activated.text
    assert activated.json()["authenticated"] is True
    db.refresh(license_row)
    assert license_row.status == "ACTIVATED"
    assert license_row.assigned_user_id == user.id
    assert license_row.activated_at is not None
    assert auth_client.get("/api/auth/status").json()["authenticated"] is True
    assert auth_client.get("/api/teachers").status_code == 200
    assert notifications[-1].startswith("🔐 License Activated")

    assert auth_client.post("/api/auth/logout").status_code == 200
    relogin = auth_client.post("/api/auth/login", json={"username": "hussein_1", "password": payload["password"]})
    assert relogin.status_code == 200
    assert relogin.json()["authenticated"] is True

    second_payload = {
        "school_name": "مدرسة المستقبل",
        "username": "another_user",
        "email": "another@example.com",
        "password": "another-strong-123",
        "confirm_password": "another-strong-123",
    }
    second_registration = auth_client.post("/api/auth/register", json=second_payload)
    assert second_registration.status_code == 201
    first_school_id = db.scalar(select(models.AdminAccount.school_id).where(models.AdminAccount.username == "hussein_1"))
    second_school_id = db.scalar(select(models.AdminAccount.school_id).where(models.AdminAccount.username == "another_user"))
    assert first_school_id != second_school_id
    assert db.scalar(select(models.School.name).where(models.School.id == second_school_id)) == "مدرسة المستقبل"
    assert db.scalar(select(models.SchoolSettings.school_name).where(models.SchoolSettings.school_id == second_school_id)) == "مدرسة المستقبل"
    second_key = delivered[1][1]
    second_login = auth_client.post("/api/auth/login", json={"username": "another_user", "password": second_payload["password"]})
    assert second_login.json()["activation_required"] is True
    reused_key = auth_client.post("/api/auth/activate-license", json={"license_key": activation_key})
    assert reused_key.status_code == 400
    second_activation = auth_client.post("/api/auth/activate-license", json={"license_key": second_key})
    assert second_activation.status_code == 200
    assert len({license_row.assigned_user_id for license_row in db.scalars(select(models.LicenseKey)).all()}) == 2


def test_registration_validation_and_email_configuration(auth_client, db, monkeypatch):
    monkeypatch.setattr(security.settings, "email_host", None)
    monkeypatch.setattr(security.settings, "email_from", None)
    base = {
        "username": "school_admin",
        "email": "admin@example.com",
        "password": "strong-password-123",
        "confirm_password": "strong-password-123",
    }
    assert auth_client.post("/api/auth/register", json={**base, "username": "school admin"}).status_code == 422
    assert auth_client.post("/api/auth/login", json={"username": "school admin", "password": "strong-password-123"}).status_code == 422
    assert auth_client.post("/api/auth/register", json={**base, "email": "not-an-email"}).status_code == 422
    assert auth_client.post("/api/auth/register", json={**base, "password": "alllettersxx", "confirm_password": "alllettersxx"}).status_code == 422
    assert auth_client.post("/api/auth/register", json={**base, "confirm_password": "different-password-1"}).status_code == 400

    unavailable = auth_client.post("/api/auth/register", json=base)
    assert unavailable.status_code == 503
    assert db.scalar(select(models.AdminAccount.id)) is None
    assert db.scalar(select(models.LicenseKey.id)) is None
