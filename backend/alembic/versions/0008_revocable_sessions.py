"""Allow logout and staff deactivation to invalidate signed sessions."""
from alembic import op
import sqlalchemy as sa

revision = "0008_revocable_sessions"
down_revision = "0007_staff_accounts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("admin_accounts", sa.Column("session_version", sa.Integer(), server_default="0", nullable=False))
    op.add_column("staff_accounts", sa.Column("session_version", sa.Integer(), server_default="0", nullable=False))


def downgrade():
    op.drop_column("staff_accounts", "session_version")
    op.drop_column("admin_accounts", "session_version")
