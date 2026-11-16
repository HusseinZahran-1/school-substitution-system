"""Validated request and response contracts."""
from datetime import date
import base64
import binascii
from typing import Literal
from urllib.parse import urlparse
import re
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
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

class AssistantTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1200)


class AssistantQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=240)
    history: list[AssistantTurn] = Field(default_factory=list, max_length=12)

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, question: str) -> str:
        question = question.strip()
        if not question:
            raise ValueError("اكتب سؤالك أولاً")
        return question

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

class SchoolSettingsIn(BaseModel):
    school_name: str = Field(min_length=1, max_length=160)
    school_logo_url: str | None = Field(default=None, max_length=2_800_000)

    @field_validator("school_name")
    @classmethod
    def school_name_not_blank(cls, name: str) -> str:
        name = name.strip()
        if not name:
            raise ValueError("اسم المدرسة مطلوب")
        return name

    @field_validator("school_logo_url")
    @classmethod
    def valid_logo_reference(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip()
        if value.startswith("data:"):
            try:
                header, encoded = value.split(",", 1)
                mime = header.removeprefix("data:").removesuffix(";base64")
                if mime not in {"image/png", "image/jpeg", "image/webp"} or not header.endswith(";base64"):
                    raise ValueError("صيغة شعار المدرسة غير مدعومة")
                if len(base64.b64decode(encoded, validate=True)) > 2_000_000:
                    raise ValueError("حجم شعار المدرسة يجب ألا يتجاوز 2 ميغابايت")
            except (ValueError, binascii.Error) as exc:
                raise ValueError("ارفع صورة PNG أو JPG أو WebP صالحة بحجم لا يتجاوز 2 ميغابايت") from exc
            return value
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("رابط الشعار يجب أن يبدأ بـ http:// أو https://")
        return value

class AdminRegisterIn(BaseModel):
    school_name: str = Field(default="", max_length=160)
    username: str = Field(min_length=3, max_length=80)
    email: EmailStr
    password: str = Field(min_length=10, max_length=256)
    confirm_password: str = Field(min_length=10, max_length=256)

    @field_validator("school_name")
    @classmethod
    def normalize_school_name(cls, name: str) -> str:
        return name.strip()

    @field_validator("username")
    @classmethod
    def username_not_blank(cls, username: str) -> str:
        if any(char.isspace() for char in username):
            raise ValueError("اسم المستخدم لا يقبل أي مسافات أو فراغات")
        if not username.strip():
            raise ValueError("اسم المستخدم مطلوب")
        return username.casefold()

    @field_validator("email")
    @classmethod
    def normalize_email(cls, email: EmailStr) -> str:
        return str(email).strip().casefold()

    @field_validator("password")
    @classmethod
    def strong_password(cls, password: str) -> str:
        if not any(char.isalpha() for char in password) or not any(char.isdigit() for char in password):
            raise ValueError("كلمة المرور يجب أن تحتوي على حرف ورقم على الأقل")
        return password

class AdminLoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("username")
    @classmethod
    def normalized_username(cls, username: str) -> str:
        if any(char.isspace() for char in username):
            raise ValueError("اسم المستخدم لا يقبل أي مسافات أو فراغات")
        return username.casefold()


class LicenseActivationIn(BaseModel):
    license_key: str = Field(min_length=16, max_length=19)

    @field_validator("license_key")
    @classmethod
    def normalize_license_key(cls, license_key: str) -> str:
        normalized = license_key.strip().upper().replace("-", "")
        if not re.fullmatch(r"[23456789ABCDEFGHJKLMNPQRSTUVWXYZ]{16}", normalized):
            raise ValueError("صيغة مفتاح التفعيل غير صحيحة")
        return normalized


class StaffAccountCreateIn(BaseModel):
    teacher_id: int
    username: str = Field(min_length=3, max_length=80)
    email: EmailStr
    role: Literal["COORDINATOR", "TEACHER", "CUSTOM"]
    custom_role_id: int | None = Field(default=None, gt=0)

    @field_validator("username")
    @classmethod
    def normalize_staff_username(cls, username: str) -> str:
        if any(char.isspace() for char in username) or not username.strip():
            raise ValueError("اسم المستخدم لا يقبل المسافات")
        return username.casefold()

    @field_validator("email")
    @classmethod
    def normalize_staff_email(cls, email: EmailStr) -> str:
        return str(email).strip().casefold()


class StaffInviteAcceptIn(BaseModel):
    token: str = Field(min_length=32, max_length=128)
    password: str = Field(min_length=10, max_length=256)
    confirm_password: str = Field(min_length=10, max_length=256)

    @field_validator("password")
    @classmethod
    def strong_staff_password(cls, password: str) -> str:
        if not any(char.isalpha() for char in password) or not any(char.isdigit() for char in password):
            raise ValueError("كلمة المرور يجب أن تحتوي على حرف ورقم على الأقل")
        return password


class StaffAccountUpdateIn(BaseModel):
    role: Literal["COORDINATOR", "TEACHER", "CUSTOM"]
    custom_role_id: int | None = Field(default=None, gt=0)


class SchoolRoleIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)
    permissions: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("name")
    @classmethod
    def normalize_role_name(cls, value):
        value = " ".join(value.split())
        if not value or value.casefold() in {"manager", "teacher", "coordinator", "مدير", "مدير المدرسة", "معلم", "منسق"}:
            raise ValueError("اختر اسمًا مميزًا للدور المخصص")
        return value

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, values):
        from .permissions import PERMISSION_KEYS, expand_permissions
        if set(values) - PERMISSION_KEYS:
            raise ValueError("توجد صلاحيات غير معروفة أو غير قابلة للتفويض")
        return expand_permissions(values)
