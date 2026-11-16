"""Persist school name and uploaded logo for print branding."""
from alembic import op
import sqlalchemy as sa

revision = "0003_school_settings"
down_revision = "0002_admin_accounts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "school_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("school_name", sa.String(length=160), nullable=False, server_default="المدرسة"),
        sa.Column("school_logo_url", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("school_settings")
