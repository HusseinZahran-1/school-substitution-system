"""School-owned roles and granular staff permissions; retain existing roles."""
from alembic import op
import sqlalchemy as sa

revision = "0009_custom_roles"
down_revision = "0008_revocable_sessions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "school_roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("school_id", sa.Integer(), sa.ForeignKey("schools.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.String(300), nullable=False, server_default=""),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("school_id", "name", name="uq_school_role_name"),
    )
    op.create_index("ix_school_roles_school_id", "school_roles", ["school_id"])
    with op.batch_alter_table("staff_accounts") as batch:
        batch.add_column(sa.Column("custom_role_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_staff_custom_role", "school_roles", ["custom_role_id"], ["id"], ondelete="RESTRICT")
        batch.create_index("ix_staff_accounts_custom_role_id", ["custom_role_id"])
        batch.drop_constraint("ck_staff_account_role", type_="check")
        batch.create_check_constraint("ck_staff_account_role", "role IN ('COORDINATOR', 'TEACHER', 'CUSTOM')")
        batch.create_check_constraint("ck_staff_custom_role", "(role = 'CUSTOM' AND custom_role_id IS NOT NULL) OR (role <> 'CUSTOM' AND custom_role_id IS NULL)")


def downgrade():
    # Fall back to personal access only when reverting custom roles.
    op.execute("UPDATE staff_accounts SET role = 'TEACHER', custom_role_id = NULL, session_version = session_version + 1 WHERE role = 'CUSTOM'")
    with op.batch_alter_table("staff_accounts") as batch:
        batch.drop_constraint("ck_staff_custom_role", type_="check")
        batch.drop_constraint("ck_staff_account_role", type_="check")
        batch.create_check_constraint("ck_staff_account_role", "role IN ('COORDINATOR', 'TEACHER')")
        batch.drop_index("ix_staff_accounts_custom_role_id")
        batch.drop_constraint("fk_staff_custom_role", type_="foreignkey")
        batch.drop_column("custom_role_id")
    op.drop_table("school_roles")
