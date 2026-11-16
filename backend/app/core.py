
"""Application configuration and shared enums."""

from enum import StrEnum
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "نظام إدارة جدول الاحتياط المدرسي الآلي"
    app_env: str = "development"

    # Database
    database_url: str | None = None
    postgres_db: str = "school_substitution"
    postgres_user: str = "school_admin"
    postgres_password: str | None = None
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432

    # Application
    cors_origins: str = "*"
    school_timezone: str = "Asia/Amman"
    port: int = 8001

    # Security
    session_secret: str | None = None
    session_cookie_secure: bool = False
    license_hash_secret: str | None = None

    # Registration
    registration_enabled: bool = True
    public_app_url: str | None = None

    # Existing SMTP settings
    email_host: str | None = None
    email_port: int = 587
    email_username: str | None = None
    email_password: str | None = None
    email_from: str | None = None
    email_use_ssl: bool = False
    email_use_starttls: bool = True

    # Email provider: smtp or gmail_api
    email_provider: str = "smtp"

    # Gmail API OAuth2 settings
    gmail_client_id: str | None = None
    gmail_client_secret: str | None = None
    gmail_refresh_token: str | None = None

    # Discord notifications
    discord_webhook_url: str | None = None

    # Local AI / Ollama
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5-coder:7b"
    ollama_timeout_seconds: int = 180
    assistant_enabled: bool = False

    # Environment configuration
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        extra="ignore",
    )

    @model_validator(mode="after")
    def default_to_postgresql(self):
        if self.database_url:
            return self

        if not self.postgres_password:
            raise ValueError(
                "PostgreSQL is required: set DATABASE_URL "
                "or configure POSTGRES_PASSWORD in the root .env"
            )

        self.database_url = URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        ).render_as_string(hide_password=False)

        return self

    @model_validator(mode="after")
    def validate_production_configuration(self):

        # Validate email provider
        if self.email_provider not in {"smtp", "gmail_api"}:
            raise ValueError(
                "EMAIL_PROVIDER must be smtp or gmail_api"
            )

        # Validate Gmail API credentials when enabled
        if self.email_provider == "gmail_api":
            if not all((
                self.gmail_client_id,
                self.gmail_client_secret,
                self.gmail_refresh_token,
                self.email_from,
            )):
                raise ValueError(
                    "Gmail API requires GMAIL_CLIENT_ID, "
                    "GMAIL_CLIENT_SECRET, "
                    "GMAIL_REFRESH_TOKEN and EMAIL_FROM"
                )

        # Validate public URL
        if self.public_app_url:
            public_url = urlsplit(self.public_app_url)

            if (
                public_url.scheme not in {"http", "https"}
                or not public_url.netloc
                or public_url.username
                or public_url.password
            ):
                raise ValueError(
                    "PUBLIC_APP_URL must be a valid "
                    "HTTP or HTTPS origin or URL"
                )

        # Development mode
        if self.app_env.lower() != "production":
            return self

        # Production secrets
        secrets_to_check = {
            "POSTGRES_PASSWORD": self.postgres_password,
            "SESSION_SECRET": self.session_secret,
            "LICENSE_HASH_SECRET": self.license_hash_secret,
        }

        for name, value in secrets_to_check.items():
            if (
                not value
                or len(value) < 32
                or "replace_" in value.lower()
                or "change_me" in value.lower()
            ):
                raise ValueError(
                    f"{name} must be a unique secret "
                    "of at least 32 characters in production"
                )

        if self.session_secret == self.license_hash_secret:
            raise ValueError(
                "SESSION_SECRET and LICENSE_HASH_SECRET "
                "must be different"
            )

        if not self.session_cookie_secure:
            raise ValueError(
                "SESSION_COOKIE_SECURE must be true in production"
            )

        # CORS
        origins = [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]

        if not origins or any(
            origin == "*"
            or not origin.startswith("https://")
            for origin in origins
        ):
            raise ValueError(
                "CORS_ORIGINS must contain only "
                "explicit HTTPS origins in production"
            )

        # Email configuration
        if self.registration_enabled:

            if not self.email_from:
                raise ValueError(
                    "EMAIL_FROM is required when "
                    "registration is enabled in production"
                )

            if self.email_provider == "smtp":
                if not self.email_host:
                    raise ValueError(
                        "SMTP host is required when "
                        "registration is enabled in production"
                    )

        # Public URL must use HTTPS
        if (
            self.public_app_url
            and not self.public_app_url.startswith("https://")
        ):
            raise ValueError(
                "PUBLIC_APP_URL must use HTTPS in production"
            )

        return self


settings = Settings()


class Day(StrEnum):
    SUNDAY = "SUNDAY"
    MONDAY = "MONDAY"
    TUESDAY = "TUESDAY"
    WEDNESDAY = "WEDNESDAY"
    THURSDAY = "THURSDAY"


class CellStatus(StrEnum):
    TEACHING = "TEACHING"
    FREE = "FREE"
    DUTY = "DUTY"
    OTHER = "OTHER"


class AssignmentStatus(StrEnum):
    SUGGESTED = "SUGGESTED"
    ASSIGNED = "ASSIGNED"
    CONFIRMED = "CONFIRMED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
