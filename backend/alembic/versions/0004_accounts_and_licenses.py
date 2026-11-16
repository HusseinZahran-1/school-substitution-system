"""Add account email and one-use license keys."""
from alembic import op
import sqlalchemy as sa

revision = "0004_accounts_and_licenses"
down_revision = "0003_school_settings"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("admin_accounts", sa.Column("email", sa.String(length=320), nullable=True))
    op.execute("UPDATE admin_accounts SET email = 'legacy-' || id || '@invalid.local' WHERE email IS NULL")
    with op.batch_alter_table("admin_accounts") as batch:
        batch.alter_column("email", existing_type=sa.String(length=320), nullable=False)
        batch.create_index("ix_admin_accounts_email", ["email"], unique=True)

    op.create_table(
        "license_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="UNUSED"),
        sa.Column("assigned_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('UNUSED', 'ACTIVATED')", name="ck_license_key_status"),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["admin_accounts.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("key_hash"),
        sa.UniqueConstraint("assigned_user_id"),
    )
    op.create_index("ix_license_keys_status", "license_keys", ["status"], unique=False)


def downgrade():
    op.drop_index("ix_license_keys_status", table_name="license_keys")
    op.drop_table("license_keys")
    with op.batch_alter_table("admin_accounts") as batch:
        batch.drop_index("ix_admin_accounts_email")
        batch.drop_column("email")
