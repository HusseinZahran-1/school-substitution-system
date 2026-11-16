import pytest
from pydantic import ValidationError

from backend.app.core import Settings


def production_settings(**overrides):
    values = {
        "app_env": "production",
        "database_url": "postgresql+psycopg://school:password@db:5432/school",
        "postgres_password": "0" * 64,
        "session_secret": "1" * 64,
        "license_hash_secret": "2" * 64,
        "session_cookie_secure": True,
        "cors_origins": "https://school.example.com",
        "registration_enabled": False,
        "email_host": None,
        "email_from": None,
    }
    values.update(overrides)
    return Settings(**values)


def test_accepts_closed_registration_with_strong_secrets():
    settings = production_settings()
    assert settings.app_env == "production"
    assert settings.registration_enabled is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"session_secret": "replace_with_a_long_random_secret"},
        {"license_hash_secret": "1" * 64},
        {"session_cookie_secure": False},
        {"cors_origins": "*"},
        {"cors_origins": "http://school.example.com"},
    ],
)
def test_rejects_insecure_production_settings(overrides):
    with pytest.raises(ValidationError):
        production_settings(**overrides)


def test_requires_smtp_before_public_registration():
    with pytest.raises(ValidationError, match="SMTP host and sender"):
        production_settings(registration_enabled=True)


def test_accepts_public_registration_when_smtp_is_configured():
    settings = production_settings(
        registration_enabled=True,
        email_host="smtp.example.com",
        email_from="school@example.com",
    )
    assert settings.registration_enabled is True
