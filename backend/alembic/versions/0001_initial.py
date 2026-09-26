"""Create normalized schedule and substitution tables."""
from alembic import op
from app.database import Base
from app import models  # noqa: F401

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # This revision predates admin_accounts. Keep it pinned to the original
    # schema so a fresh install does not create that table before 0002 runs.
    tables = [table for table in Base.metadata.sorted_tables if table.name != "admin_accounts"]
    Base.metadata.create_all(bind=op.get_bind(), tables=tables)

def downgrade():
    tables = [table for table in Base.metadata.sorted_tables if table.name != "admin_accounts"]
    Base.metadata.drop_all(bind=op.get_bind(), tables=tables)
