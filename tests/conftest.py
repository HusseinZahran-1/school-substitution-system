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
        yield session
    Base.metadata.drop_all(engine)

@pytest.fixture(autouse=True)
def authenticated_admin():
    """API route tests exercise business behavior behind the login boundary."""
    admin = models.AdminAccount(id=1, username="test-admin")
    app.dependency_overrides[require_admin] = lambda: admin
    yield
    app.dependency_overrides.pop(require_admin, None)
