import os

# Unit tests use an isolated in-memory SQLite database. Application runs use
# the PostgreSQL URL configured in the root .env or DATABASE_URL.
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from backend.app.database import Base
from backend.app import models  # noqa: F401
from backend.app.main import app
from backend.app.security import require_admin

@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        session.add(models.School(id=1, name="مدرسة الاختبار"))
        session.commit()
        session.info["school_id"] = 1
        yield session
    Base.metadata.drop_all(engine)

@pytest.fixture(autouse=True)
def authenticated_admin():
    """API route tests exercise business behavior behind the login boundary."""
    admin = models.AdminAccount(id=1, school_id=1, username="test-admin", email="test-admin@example.com")
    app.dependency_overrides[require_admin] = lambda: admin
    yield
    app.dependency_overrides.pop(require_admin, None)
