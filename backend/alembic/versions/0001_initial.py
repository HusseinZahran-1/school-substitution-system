"""Create the original, pre-account schedule and substitution schema.

Keep this revision independent from application models so later model changes do
not silently alter the schema used by fresh installations.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

metadata = sa.MetaData()
teachers = sa.Table(
    "teachers", metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("name", sa.String(length=160), nullable=False),
    sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
)
sa.Index("ix_teachers_name", teachers.c.name, unique=True)

subjects = sa.Table(
    "subjects", metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("name", sa.String(length=120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
)
sa.Index("ix_subjects_name", subjects.c.name, unique=True)

classes = sa.Table(
    "classes", metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("name", sa.String(length=80), nullable=False),
    sa.Column("grade", sa.String(length=40)),
    sa.Column("section", sa.String(length=40)),
    sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
)
sa.Index("ix_classes_name", classes.c.name, unique=True)

teacher_subjects = sa.Table(
    "teacher_subjects", metadata,
    sa.Column("teacher_id", sa.Integer(), sa.ForeignKey("teachers.id", ondelete="CASCADE"), primary_key=True),
    sa.Column("subject_id", sa.Integer(), sa.ForeignKey("subjects.id", ondelete="CASCADE"), primary_key=True),
)

schedule_entries = sa.Table(
    "schedule_entries", metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("teacher_id", sa.Integer(), sa.ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False),
    sa.Column("day_of_week", sa.String(length=12), nullable=False),
    sa.Column("period_number", sa.Integer(), nullable=False),
    sa.Column("class_id", sa.Integer(), sa.ForeignKey("classes.id", ondelete="SET NULL")),
    sa.Column("subject_id", sa.Integer(), sa.ForeignKey("subjects.id", ondelete="SET NULL")),
    sa.Column("status", sa.String(length=12), nullable=False, server_default="FREE"),
    sa.Column("notes", sa.Text()),
    sa.UniqueConstraint("teacher_id", "day_of_week", "period_number", name="uq_schedule_teacher_day_period"),
    sa.CheckConstraint("period_number BETWEEN 1 AND 7", name="ck_schedule_period"),
)
sa.Index("ix_schedule_entries_teacher_id", schedule_entries.c.teacher_id)
sa.Index("ix_schedule_entries_day_of_week", schedule_entries.c.day_of_week)
sa.Index("ix_schedule_entries_class_id", schedule_entries.c.class_id)
sa.Index("ix_schedule_entries_subject_id", schedule_entries.c.subject_id)
sa.Index("ix_schedule_day_period_status", schedule_entries.c.day_of_week, schedule_entries.c.period_number, schedule_entries.c.status)

absences = sa.Table(
    "absences", metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("teacher_id", sa.Integer(), sa.ForeignKey("teachers.id", ondelete="RESTRICT"), nullable=False),
    sa.Column("date", sa.Date(), nullable=False),
    sa.Column("reason", sa.Text()),
    sa.Column("created_by", sa.String(length=160)),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
)
sa.Index("ix_absences_teacher_id", absences.c.teacher_id)
sa.Index("ix_absences_date", absences.c.date)
sa.Index("ix_absences_date_teacher", absences.c.date, absences.c.teacher_id)

absence_periods = sa.Table(
    "absence_periods", metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("absence_id", sa.Integer(), sa.ForeignKey("absences.id", ondelete="CASCADE"), nullable=False),
    sa.Column("period_number", sa.Integer(), nullable=False),
    sa.Column("class_id", sa.Integer(), sa.ForeignKey("classes.id", ondelete="SET NULL")),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.UniqueConstraint("absence_id", "period_number", name="uq_absence_period"),
    sa.CheckConstraint("period_number BETWEEN 1 AND 7", name="ck_absence_period"),
)
sa.Index("ix_absence_periods_absence_id", absence_periods.c.absence_id)

assignments = sa.Table(
    "substitution_assignments", metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("absence_period_id", sa.Integer(), sa.ForeignKey("absence_periods.id", ondelete="CASCADE"), nullable=False),
    sa.Column("absent_teacher_id", sa.Integer(), sa.ForeignKey("teachers.id", ondelete="RESTRICT"), nullable=False),
    sa.Column("substitute_teacher_id", sa.Integer(), sa.ForeignKey("teachers.id", ondelete="RESTRICT")),
    sa.Column("date", sa.Date(), nullable=False),
    sa.Column("period_number", sa.Integer(), nullable=False),
    sa.Column("class_id", sa.Integer(), sa.ForeignKey("classes.id", ondelete="SET NULL")),
    sa.Column("waiting_location", sa.String(length=160)),
    sa.Column("status", sa.String(length=16), nullable=False, server_default="SUGGESTED"),
    sa.Column("notes", sa.Text()),
    sa.Column("created_by", sa.String(length=160)),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.Column("approved_at", sa.DateTime(timezone=True)),
    sa.Column("approved_by", sa.String(length=160)),
    sa.Column("signature", sa.String(length=160)),
    sa.UniqueConstraint("date", "period_number", "substitute_teacher_id", name="uq_substitute_date_period_teacher"),
    sa.CheckConstraint("period_number BETWEEN 1 AND 7", name="ck_assignment_period"),
)
sa.Index("ix_substitution_assignments_absence_period_id", assignments.c.absence_period_id)
sa.Index("ix_substitution_assignments_absent_teacher_id", assignments.c.absent_teacher_id)
sa.Index("ix_substitution_assignments_substitute_teacher_id", assignments.c.substitute_teacher_id)
sa.Index("ix_substitution_assignments_date", assignments.c.date)
sa.Index("ix_substitution_assignments_status", assignments.c.status)
sa.Index("ix_assignment_date_period_status", assignments.c.date, assignments.c.period_number, assignments.c.status)

audit_logs = sa.Table(
    "audit_logs", metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("entity_type", sa.String(length=40), nullable=False),
    sa.Column("entity_id", sa.Integer(), nullable=False),
    sa.Column("action", sa.String(length=40), nullable=False),
    sa.Column("actor", sa.String(length=160)),
    sa.Column("detail", sa.Text()),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
)
sa.Index("ix_audit_logs_entity_type", audit_logs.c.entity_type)
sa.Index("ix_audit_logs_entity_id", audit_logs.c.entity_id)


def upgrade():
    metadata.create_all(bind=op.get_bind())


def downgrade():
    metadata.drop_all(bind=op.get_bind())
