"""Give each newly registered account an isolated school data space."""
from alembic import op
import sqlalchemy as sa

revision = "0006_school_tenants"
down_revision = "0005_legacy_licenses"
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "teachers", "subjects", "classes", "schedule_entries", "absences",
    "absence_periods", "substitution_assignments", "audit_logs", "school_settings",
)


def _columns(inspector, table):
    return {column["name"] for column in inspector.get_columns(table)}


def _table_names(inspector):
    return set(inspector.get_table_names())


def _school_id(connection, schools):
    result = connection.execute(sa.insert(schools).values(name="المدرسة الحالية"))
    return result.inserted_primary_key[0]


def upgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = _table_names(inspector)
    if "schools" not in tables:
        op.create_table(
            "schools",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    schools = sa.Table("schools", sa.MetaData(), autoload_with=connection)

    legacy_name = "المدرسة الحالية"
    if "school_settings" in tables and "school_name" in _columns(inspector, "school_settings"):
        legacy_name = connection.execute(sa.text("SELECT school_name FROM school_settings ORDER BY id LIMIT 1")).scalar() or legacy_name
    legacy_id = _school_id(connection, schools)
    connection.execute(sa.update(schools).where(schools.c.id == legacy_id).values(name=legacy_name))

    # Add nullable columns first, then place all historical rows in one preserved
    # legacy school before making tenant ownership mandatory.
    for table in (*TENANT_TABLES, "admin_accounts"):
        if table not in tables:
            continue
        if "school_id" not in _columns(inspector, table):
            tenant_column = sa.Column(
                "school_id", sa.Integer(),
                sa.ForeignKey(
                    "schools.id", name=f"fk_{table}_school_id_schools",
                    ondelete="RESTRICT" if table == "admin_accounts" else "CASCADE",
                ),
                nullable=True,
            )
            if connection.dialect.name == "sqlite":
                with op.batch_alter_table(table) as batch:
                    batch.add_column(tenant_column)
            else:
                op.add_column(table, tenant_column)
        connection.execute(sa.text(f'UPDATE "{table}" SET school_id = :school_id WHERE school_id IS NULL'), {"school_id": legacy_id})

        # SQLite needs a batch table rebuild to alter nullability; PostgreSQL uses
        # the same operation as ALTER COLUMN SET NOT NULL.
        if "school_id" not in _columns(sa.inspect(connection), table) or any(
            col["name"] == "school_id" and col["nullable"] for col in sa.inspect(connection).get_columns(table)
        ):
            with op.batch_alter_table(table) as batch:
                batch.alter_column("school_id", existing_type=sa.Integer(), nullable=False)

        current_indexes = {index["name"] for index in sa.inspect(connection).get_indexes(table)}
        tenant_index = f"ix_{table}_school_id"
        if tenant_index not in current_indexes:
            op.create_index(tenant_index, table, ["school_id"], unique=False)

    # Replace global name uniqueness with uniqueness inside each school.
    for table, old_index, constraint, columns in (
        ("teachers", "ix_teachers_name", "uq_teacher_school_name", ["school_id", "name"]),
        ("subjects", "ix_subjects_name", "uq_subject_school_name", ["school_id", "name"]),
        ("classes", "ix_classes_name", "uq_class_school_name", ["school_id", "name"]),
    ):
        if table not in _table_names(sa.inspect(connection)):
            continue
        indexes = {item["name"]: item for item in sa.inspect(connection).get_indexes(table)}
        if old_index in indexes and indexes[old_index].get("unique"):
            op.drop_index(old_index, table_name=table)
        uniques = sa.inspect(connection).get_unique_constraints(table)
        if not any(item.get("name") == constraint for item in uniques):
            with op.batch_alter_table(table) as batch:
                batch.create_unique_constraint(constraint, columns)

    for table, constraint, scoped_columns in (
        ("schedule_entries", "uq_schedule_teacher_day_period", ["school_id", "teacher_id", "day_of_week", "period_number"]),
        ("substitution_assignments", "uq_substitute_date_period_teacher", ["school_id", "date", "period_number", "substitute_teacher_id"]),
    ):
        uniques = sa.inspect(connection).get_unique_constraints(table)
        found = next((item for item in uniques if item.get("name") == constraint), None)
        if found and found.get("column_names") != scoped_columns:
            with op.batch_alter_table(table) as batch:
                batch.drop_constraint(constraint, type_="unique")
                batch.create_unique_constraint(constraint, scoped_columns)
        elif not found:
            with op.batch_alter_table(table) as batch:
                batch.create_unique_constraint(constraint, scoped_columns)

    settings_uniques = sa.inspect(connection).get_unique_constraints("school_settings")
    if not any(item.get("name") == "uq_school_settings_school_id" for item in settings_uniques):
        with op.batch_alter_table("school_settings") as batch:
            batch.create_unique_constraint("uq_school_settings_school_id", ["school_id"])


def downgrade():
    # Tenant isolation must not be removed from a database that may contain
    # multiple schools. Downgrades are intentionally unsupported.
    raise RuntimeError("Downgrading school isolation is unsafe")
