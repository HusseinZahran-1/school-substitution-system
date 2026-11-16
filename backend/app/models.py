"""Normalized persistence models for timetable and substitution workflow."""
from datetime import date as DateValue, datetime
from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Index, Integer, JSON, String, Table, Text, UniqueConstraint, event, func
from sqlalchemy.orm import Mapped, Session as OrmSession, mapped_column, relationship, with_loader_criteria
from .database import Base

teacher_subjects = Table(
    "teacher_subjects", Base.metadata,
    Column("teacher_id", ForeignKey("teachers.id", ondelete="CASCADE"), primary_key=True),
    Column("subject_id", ForeignKey("subjects.id", ondelete="CASCADE"), primary_key=True),
)

class School(Base):
    __tablename__ = "schools"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SchoolScoped:
    """Mixin for all school-owned records; request sessions are scoped centrally."""
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True, nullable=False)


class Teacher(SchoolScoped, Base):
    __tablename__ = "teachers"
    __table_args__ = (UniqueConstraint("school_id", "name", name="uq_teacher_school_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    subjects: Mapped[list["Subject"]] = relationship(secondary=teacher_subjects, back_populates="teachers")
    schedules: Mapped[list["ScheduleEntry"]] = relationship(back_populates="teacher", cascade="all, delete-orphan")

class Subject(SchoolScoped, Base):
    __tablename__ = "subjects"
    __table_args__ = (UniqueConstraint("school_id", "name", name="uq_subject_school_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    teachers: Mapped[list[Teacher]] = relationship(secondary=teacher_subjects, back_populates="subjects")

class SchoolClass(SchoolScoped, Base):
    __tablename__ = "classes"
    __table_args__ = (UniqueConstraint("school_id", "name", name="uq_class_school_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), index=True)
    grade: Mapped[str | None] = mapped_column(String(40))
    section: Mapped[str | None] = mapped_column(String(40))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

class ScheduleEntry(SchoolScoped, Base):
    __tablename__ = "schedule_entries"
    __table_args__ = (UniqueConstraint("school_id", "teacher_id", "day_of_week", "period_number", name="uq_schedule_teacher_day_period"), CheckConstraint("period_number BETWEEN 1 AND 7", name="ck_schedule_period"), Index("ix_schedule_day_period_status", "day_of_week", "period_number", "status"))
    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"), index=True)
    day_of_week: Mapped[str] = mapped_column(String(12), index=True)
    period_number: Mapped[int] = mapped_column(Integer)
    class_id: Mapped[int | None] = mapped_column(ForeignKey("classes.id", ondelete="SET NULL"), index=True)
    subject_id: Mapped[int | None] = mapped_column(ForeignKey("subjects.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(12), default="FREE", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    teacher: Mapped[Teacher] = relationship(back_populates="schedules")
    school_class: Mapped[SchoolClass | None] = relationship()
    subject: Mapped[Subject | None] = relationship()

class Absence(SchoolScoped, Base):
    __tablename__ = "absences"
    __table_args__ = (Index("ix_absences_date_teacher", "date", "teacher_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="RESTRICT"), index=True)
    date: Mapped[DateValue] = mapped_column(Date, index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    teacher: Mapped[Teacher] = relationship()
    periods: Mapped[list["AbsencePeriod"]] = relationship(back_populates="absence", cascade="all, delete-orphan")

class AbsencePeriod(SchoolScoped, Base):
    __tablename__ = "absence_periods"
    __table_args__ = (UniqueConstraint("absence_id", "period_number", name="uq_absence_period"), CheckConstraint("period_number BETWEEN 1 AND 7", name="ck_absence_period"))
    id: Mapped[int] = mapped_column(primary_key=True)
    absence_id: Mapped[int] = mapped_column(ForeignKey("absences.id", ondelete="CASCADE"), index=True)
    period_number: Mapped[int] = mapped_column(Integer)
    class_id: Mapped[int | None] = mapped_column(ForeignKey("classes.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    absence: Mapped[Absence] = relationship(back_populates="periods")
    school_class: Mapped[SchoolClass | None] = relationship()
    assignments: Mapped[list["SubstitutionAssignment"]] = relationship(back_populates="absence_period", cascade="all, delete-orphan")

class SubstitutionAssignment(SchoolScoped, Base):
    __tablename__ = "substitution_assignments"
    __table_args__ = (UniqueConstraint("school_id", "date", "period_number", "substitute_teacher_id", name="uq_substitute_date_period_teacher"), Index("ix_assignment_date_period_status", "date", "period_number", "status"), CheckConstraint("period_number BETWEEN 1 AND 7", name="ck_assignment_period"))
    id: Mapped[int] = mapped_column(primary_key=True)
    absence_period_id: Mapped[int] = mapped_column(ForeignKey("absence_periods.id", ondelete="CASCADE"), index=True)
    absent_teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="RESTRICT"), index=True)
    substitute_teacher_id: Mapped[int | None] = mapped_column(ForeignKey("teachers.id", ondelete="RESTRICT"), index=True)
    date: Mapped[DateValue] = mapped_column(Date, index=True)
    period_number: Mapped[int] = mapped_column(Integer)
    class_id: Mapped[int | None] = mapped_column(ForeignKey("classes.id", ondelete="SET NULL"))
    waiting_location: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(16), default="SUGGESTED", nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[str | None] = mapped_column(String(160))
    signature: Mapped[str | None] = mapped_column(String(160))
    absence_period: Mapped[AbsencePeriod] = relationship(back_populates="assignments")
    absent_teacher: Mapped[Teacher] = relationship(foreign_keys=[absent_teacher_id])
    substitute_teacher: Mapped[Teacher | None] = relationship(foreign_keys=[substitute_teacher_id])
    school_class: Mapped[SchoolClass | None] = relationship()

class AuditLog(SchoolScoped, Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str | None] = mapped_column(String(160))
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class AdminAccount(Base):
    __tablename__ = "admin_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    password_salt: Mapped[str] = mapped_column(String(64), nullable=False)
    session_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SchoolRole(SchoolScoped, Base):
    __tablename__ = "school_roles"
    __table_args__ = (UniqueConstraint("school_id", "name", name="uq_school_role_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class StaffAccount(SchoolScoped, Base):
    """Coordinator or teacher login owned by a school manager."""
    __tablename__ = "staff_accounts"
    __table_args__ = (
        UniqueConstraint("username", name="uq_staff_account_username"),
        UniqueConstraint("email", name="uq_staff_account_email"),
        UniqueConstraint("school_id", "teacher_id", name="uq_staff_account_teacher"),
        CheckConstraint("role IN ('COORDINATOR', 'TEACHER', 'CUSTOM')", name="ck_staff_account_role"),
        CheckConstraint("(role = 'CUSTOM' AND custom_role_id IS NOT NULL) OR (role <> 'CUSTOM' AND custom_role_id IS NULL)", name="ck_staff_custom_role"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    custom_role_id: Mapped[int | None] = mapped_column(ForeignKey("school_roles.id", ondelete="RESTRICT"), index=True)
    custom_role: Mapped[SchoolRole | None] = relationship()
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    session_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    invite_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    invite_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    teacher: Mapped[Teacher] = relationship()

class LicenseKey(Base):
    __tablename__ = "license_keys"
    __table_args__ = (
        CheckConstraint("status IN ('UNUSED', 'ACTIVATED')", name="ck_license_key_status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="UNUSED", index=True)
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("admin_accounts.id", ondelete="SET NULL"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class SchoolSettings(SchoolScoped, Base):
    __tablename__ = "school_settings"
    __table_args__ = (UniqueConstraint("school_id", name="uq_school_settings_school_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    school_name: Mapped[str] = mapped_column(String(160), default="المدرسة", nullable=False)
    school_logo_url: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


@event.listens_for(OrmSession, "do_orm_execute")
def _scope_school_queries(execute_state):
    school_id = execute_state.session.info.get("school_id")
    if school_id is not None and (execute_state.is_select or execute_state.is_update or execute_state.is_delete):
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(SchoolScoped, lambda model: model.school_id == school_id, include_aliases=True)
        )


@event.listens_for(OrmSession, "before_flush")
def _scope_school_writes(session, _flush_context, _instances):
    school_id = session.info.get("school_id")
    if school_id is None:
        return
    for record in session.new:
        if isinstance(record, SchoolScoped):
            if record.school_id is None:
                record.school_id = school_id
            elif record.school_id != school_id:
                raise ValueError("لا يمكن إنشاء بيانات لمدرسة أخرى")
    for record in session.dirty.union(session.deleted):
        if isinstance(record, SchoolScoped) and record.school_id != school_id:
            raise ValueError("لا يمكن تعديل بيانات مدرسة أخرى")
