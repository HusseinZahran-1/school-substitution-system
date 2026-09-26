"""Validated request and response contracts."""
from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from .core import Day, CellStatus

class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

class SubjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def subject_name_not_blank(cls, name: str) -> str:
        name = name.strip()
        if not name: raise ValueError("اسم المادة مطلوب")
        return name

class SubjectOut(ORMModel):
    id: int
    name: str

class TeacherIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    subject_ids: list[int] = Field(default_factory=list)
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def teacher_name_not_blank(cls, name: str) -> str:
        name = name.strip()
        if not name: raise ValueError("اسم المعلم مطلوب")
        return name

class TeacherOut(ORMModel):
    id: int
    name: str
    is_active: bool
    subjects: list[SubjectOut]

class ClassIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    grade: str | None = None
    section: str | None = None
    is_active: bool = True

class ClassOut(ORMModel):
    id: int
    name: str
    grade: str | None
    section: str | None
    is_active: bool

class ScheduleIn(BaseModel):
    teacher_id: int
    day_of_week: Day
    period_number: int = Field(ge=1, le=7)
    class_id: int | None = None
    subject_id: int | None = None
    status: CellStatus
    notes: str | None = None

class ScheduleOut(ORMModel):
    id: int
    teacher_id: int
    day_of_week: str
    period_number: int
    class_id: int | None
    subject_id: int | None
    status: str
    notes: str | None

class AbsencePeriodIn(BaseModel):
    period_number: int = Field(ge=1, le=7)
    class_id: int | None = None

class AbsenceIn(BaseModel):
    teacher_id: int
    date: date
    reason: str | None = None
    created_by: str | None = "مدير النظام"
    periods: list[AbsencePeriodIn] = Field(min_length=1)

    @field_validator("periods")
    @classmethod
    def unique_periods(cls, periods):
        numbers = [p.period_number for p in periods]
        if len(numbers) != len(set(numbers)):
            raise ValueError("لا يمكن تكرار الحصة في الغياب نفسه")
        return periods

class AssignIn(BaseModel):
    substitute_teacher_id: int
    waiting_location: str | None = None
    notes: str | None = None
    approved_by: str | None = "مدير النظام"

class SuggestIn(BaseModel):
    teacher_id: int
    date: date
    period_number: int = Field(ge=1, le=7)
    class_id: int | None = None

class StatusIn(BaseModel):
    actor: str | None = "مدير النظام"
    signature: str | None = None

class AdminSetupIn(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=10, max_length=256)
    confirm_password: str = Field(min_length=10, max_length=256)

    @field_validator("username")
    @classmethod
    def username_not_blank(cls, username: str) -> str:
        username = username.strip()
        if not username:
            raise ValueError("اسم المستخدم مطلوب")
        return username

class AdminLoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)
