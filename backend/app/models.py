"""Normalized persistence models for timetable and substitution workflow."""
from datetime import date as DateValue, datetime
from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Index, Integer, String, Table, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

teacher_subjects = Table(
    "teacher_subjects", Base.metadata,
    Column("teacher_id", ForeignKey("teachers.id", ondelete="CASCADE"), primary_key=True),
    Column("subject_id", ForeignKey("subjects.id", ondelete="CASCADE"), primary_key=True),
)

class Teacher(Base):
    __tablename__ = "teachers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    subjects: Mapped[list["Subject"]] = relationship(secondary=teacher_subjects, back_populates="teachers")
    schedules: Mapped[list["ScheduleEntry"]] = relationship(back_populates="teacher", cascade="all, delete-orphan")

class Subject(Base):
    __tablename__ = "subjects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    teachers: Mapped[list[Teacher]] = relationship(secondary=teacher_subjects, back_populates="subjects")

class SchoolClass(Base):
    __tablename__ = "classes"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    grade: Mapped[str | None] = mapped_column(String(40))
    section: Mapped[str | None] = mapped_column(String(40))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

class ScheduleEntry(Base):
    __tablename__ = "schedule_entries"
    __table_args__ = (UniqueConstraint("teacher_id", "day_of_week", "period_number", name="uq_schedule_teacher_day_period"), CheckConstraint("period_number BETWEEN 1 AND 7", name="ck_schedule_period"), Index("ix_schedule_day_period_status", "day_of_week", "period_number", "status"))
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

class Absence(Base):
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

class AbsencePeriod(Base):
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

class SubstitutionAssignment(Base):
    __tablename__ = "substitution_assignments"
    __table_args__ = (UniqueConstraint("date", "period_number", "substitute_teacher_id", name="uq_substitute_date_period_teacher"), Index("ix_assignment_date_period_status", "date", "period_number", "status"), CheckConstraint("period_number BETWEEN 1 AND 7", name="ck_assignment_period"))
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

class AuditLog(Base):
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
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    password_salt: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
