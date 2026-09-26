"""Application configuration and shared enums."""
from enum import StrEnum
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "نظام إدارة جدول الاحتياط المدرسي الآلي"
    database_url: str = "sqlite:///./school.db"
    cors_origins: str = "*"
    school_timezone: str = "Asia/Amman"
    port: int = 8001
    session_secret: str | None = None
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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
