"""Add school-owned coordinator and teacher accounts with one-time invitations."""
from alembic import op
import sqlalchemy as sa

revision = "0007_staff_accounts"
down_revision = "0006_school_tenants"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "staff_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("school_id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("password_hash", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("invite_token_hash", sa.String(length=64), nullable=True),
        sa.Column("invite_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role IN ('COORDINATOR', 'TEACHER')", name="ck_staff_account_role"),
        sa.ForeignKeyConstraint(["school_id"], ["schools.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["teacher_id"], ["teachers.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("username", name="uq_staff_account_username"),
        sa.UniqueConstraint("email", name="uq_staff_account_email"),
        sa.UniqueConstraint("school_id", "teacher_id", name="uq_staff_account_teacher"),
        sa.UniqueConstraint("invite_token_hash", name="uq_staff_account_invite_token_hash"),
    )
    op.create_index("ix_staff_accounts_school_id", "staff_accounts", ["school_id"])
    op.create_index("ix_staff_accounts_teacher_id", "staff_accounts", ["teacher_id"])
    op.create_index("ix_staff_accounts_username", "staff_accounts", ["username"])
    op.create_index("ix_staff_accounts_email", "staff_accounts", ["email"])


def downgrade():
    op.drop_index("ix_staff_accounts_email", table_name="staff_accounts")
    op.drop_index("ix_staff_accounts_username", table_name="staff_accounts")
    op.drop_index("ix_staff_accounts_teacher_id", table_name="staff_accounts")
    op.drop_index("ix_staff_accounts_school_id", table_name="staff_accounts")
    op.drop_table("staff_accounts")
