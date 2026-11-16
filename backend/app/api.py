"""REST endpoints for the school administration workflow."""
from collections import Counter
from datetime import date, datetime, timezone
import secrets
import smtplib
from datetime import timedelta
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from .database import get_db
from . import models as m
from .core import Day, AssignmentStatus, settings
from .engine import school_day, suggest_candidates
from .schemas import TeacherIn, SubjectIn, ClassIn, ScheduleIn, AbsenceIn, AssignIn, StatusIn, SuggestIn, SchoolSettingsIn, StaffAccountCreateIn, StaffAccountUpdateIn
from .security import _password_digest, _staff_invite_digest, require_school_scope, STAFF_INVITE_HOURS
from .schedule_import import parse_schedule_file
from .permissions import account_access
from .notifications import EmailDeliveryNotConfigured, send_staff_invitation_email

router = APIRouter(prefix="/api", dependencies=[Depends(require_school_scope)])

def _school_id(db: Session) -> int:
    school_id = db.info.get("school_id")
    if school_id is None:
        raise RuntimeError("School scope is missing from the request session")
    return school_id

def _commit(db: Session, message: str = "البيانات متعارضة أو مكررة"):
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, message) from exc

def _teacher(db: Session, teacher_id: int) -> m.Teacher:
    item = db.scalar(select(m.Teacher).options(selectinload(m.Teacher.subjects)).where(m.Teacher.id == teacher_id))
    if not item: raise HTTPException(404, "المعلم غير موجود")
    return item

def _audit(db: Session, entity: str, entity_id: int, action: str, actor: str | None, detail: str | None = None):
    db.add(m.AuditLog(entity_type=entity, entity_id=entity_id, action=action, actor=actor, detail=detail))

def _manager_only(account):
    if not isinstance(account, m.AdminAccount):
        raise HTTPException(403, "إدارة حسابات الموظفين متاحة لمدير المدرسة فقط")

def _staff_account_view(item: m.StaffAccount):
    return {"id": item.id, "teacher_id": item.teacher_id, "teacher_name": item.teacher.name,
            "username": item.username, "email": item.email, **account_access(item), "custom_role_id": item.custom_role_id,
            "is_active": item.is_active, "invite_expires_at": item.invite_expires_at}

def _assigned_role(db, payload):
    if payload.role != "CUSTOM":
        if payload.custom_role_id is not None:
            raise HTTPException(422, "اختر دورًا مخصصًا لإرفاق معرف الدور")
        return None
    role = db.scalar(select(m.SchoolRole).where(m.SchoolRole.id == payload.custom_role_id).with_for_update())
    if not role:
        raise HTTPException(404, "الدور المخصص غير موجود في مدرستك")
    return role

@router.get("/staff")
def list_staff_accounts(db: Session = Depends(get_db), admin: m.AdminAccount = Depends(require_school_scope)):
    _manager_only(admin)
    rows = db.scalars(select(m.StaffAccount).options(selectinload(m.StaffAccount.teacher)).order_by(m.StaffAccount.username)).all()
    return [_staff_account_view(row) for row in rows]

@router.post("/staff", status_code=201)
def create_staff_account(payload: StaffAccountCreateIn, request: Request, db: Session = Depends(get_db), admin: m.AdminAccount = Depends(require_school_scope)):
    _manager_only(admin)
    if not settings.email_host or not settings.email_from:
        raise HTTPException(503, "إعدادات البريد غير مكتملة؛ تعذر إرسال دعوة التفعيل")
    assigned_role = _assigned_role(db, payload)
    teacher = _teacher(db, payload.teacher_id)
    if not teacher.is_active:
        raise HTTPException(400, "فعّل المعلم قبل إنشاء حساب له")
    if db.scalar(select(m.AdminAccount.id).where(func.lower(m.AdminAccount.username) == payload.username)) or db.scalar(
        select(m.StaffAccount.id).where(func.lower(m.StaffAccount.username) == payload.username)
    ):
        raise HTTPException(409, "اسم المستخدم مستخدم مسبقًا")
    if db.scalar(select(m.AdminAccount.id).where(func.lower(m.AdminAccount.email) == payload.email)) or db.scalar(
        select(m.StaffAccount.id).where(func.lower(m.StaffAccount.email) == payload.email)
    ):
        raise HTTPException(409, "البريد الإلكتروني مستخدم مسبقًا")
    if not settings.public_app_url and settings.app_env.lower() == "production":
        raise HTTPException(503, "أضف PUBLIC_APP_URL في إعدادات التشغيل لإرسال رابط الدعوة")
    base_url = settings.public_app_url or str(request.base_url).rstrip("/")
    token = secrets.token_urlsafe(40)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=STAFF_INVITE_HOURS)
    item = m.StaffAccount(
        school_id=admin.school_id,
        teacher_id=teacher.id,
        username=payload.username,
        email=str(payload.email),
        role=payload.role,
        custom_role_id=assigned_role.id if assigned_role else None,
        password_hash=_password_digest(secrets.token_urlsafe(40)),
        is_active=False,
        invite_token_hash=_staff_invite_digest(token),
        invite_expires_at=expires_at,
    )
    db.add(item)
    try:
        db.flush()
        invite_link = f"{base_url.rstrip('/')}#staff_invite={token}"
        school = db.get(m.School, admin.school_id)
        send_staff_invitation_email(item.email, school.name if school else "المدرسة", teacher.name, account_access(item)["role_name"], invite_link)
        _audit(db, "staff_account", item.id, "INVITED", admin.username, f"teacher={teacher.id}; role={item.role}")
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "اسم المستخدم أو البريد الإلكتروني مستخدم مسبقًا") from exc
    except (EmailDeliveryNotConfigured, OSError, smtplib.SMTPException) as exc:
        db.rollback()
        raise HTTPException(503, "تعذر إرسال الدعوة؛ تحقق من إعدادات SMTP واتصال البريد الصادر") from exc
    db.refresh(item)
    return _staff_account_view(item)

@router.delete("/staff/{staff_id}", status_code=204)
def deactivate_staff_account(staff_id: int, db: Session = Depends(get_db), admin: m.AdminAccount = Depends(require_school_scope)):
    _manager_only(admin)
    item = db.get(m.StaffAccount, staff_id)
    if not item:
        raise HTTPException(404, "حساب الموظف غير موجود")
    item.is_active = False
    item.session_version += 1
    _audit(db, "staff_account", item.id, "DEACTIVATED", admin.username)
    item.invite_token_hash = None
    item.invite_expires_at = None
    _commit(db)

@router.put("/staff/{staff_id}")
def update_staff_account(staff_id: int, payload: StaffAccountUpdateIn, db: Session = Depends(get_db), admin: m.AdminAccount = Depends(require_school_scope)):
    _manager_only(admin)
    item = db.get(m.StaffAccount, staff_id)
    if not item:
        raise HTTPException(404, "حساب الموظف غير موجود")
    assigned_role = _assigned_role(db, payload)
    item.role = payload.role
    item.custom_role = assigned_role
    item.custom_role_id = assigned_role.id if assigned_role else None
    item.session_version += 1
    _audit(db, "staff_account", item.id, "UPDATED", admin.username, f"role={payload.role}; custom_role_id={item.custom_role_id}")
    _commit(db)
    return _staff_account_view(item)

@router.post("/staff/{staff_id}/resend-invite")
def resend_staff_invitation(staff_id: int, request: Request, db: Session = Depends(get_db), admin: m.AdminAccount = Depends(require_school_scope)):
    _manager_only(admin)
    if not settings.email_host or not settings.email_from:
        raise HTTPException(503, "إعدادات البريد غير مكتملة؛ تعذر إرسال دعوة التفعيل")
    item = db.scalar(select(m.StaffAccount).options(selectinload(m.StaffAccount.teacher)).where(m.StaffAccount.id == staff_id))
    if not item:
        raise HTTPException(404, "حساب الموظف غير موجود")
    if item.is_active:
        raise HTTPException(409, "الحساب مفعّل بالفعل")
    if not settings.public_app_url and settings.app_env.lower() == "production":
        raise HTTPException(503, "أضف PUBLIC_APP_URL في إعدادات التشغيل لإرسال رابط الدعوة")
    token = secrets.token_urlsafe(40)
    item.invite_token_hash = _staff_invite_digest(token)
    item.invite_expires_at = datetime.now(timezone.utc) + timedelta(hours=STAFF_INVITE_HOURS)
    base_url = settings.public_app_url or str(request.base_url).rstrip("/")
    school = db.get(m.School, admin.school_id)
    try:
        send_staff_invitation_email(item.email, school.name if school else "المدرسة", item.teacher.name, account_access(item)["role_name"],
                                    f"{base_url.rstrip('/')}#staff_invite={token}")
        _commit(db)
    except (EmailDeliveryNotConfigured, OSError, smtplib.SMTPException) as exc:
        db.rollback()
        raise HTTPException(503, "تعذر إرسال الدعوة؛ تحقق من إعدادات SMTP واتصال البريد الصادر") from exc
    return {"sent": True}

@router.get("/staff/me")
def staff_profile(admin: m.AdminAccount | m.StaffAccount = Depends(require_school_scope)):
    return {"username": admin.username, **account_access(admin),
            "teacher_id": getattr(admin, "teacher_id", None)}

@router.get("/staff/me/schedule")
def staff_own_schedule(day: Day | None = None, admin: m.AdminAccount | m.StaffAccount = Depends(require_school_scope), db: Session = Depends(get_db)):
    teacher_id = getattr(admin, "teacher_id", None)
    if teacher_id is None:
        return []
    query = select(m.ScheduleEntry).options(selectinload(m.ScheduleEntry.school_class), selectinload(m.ScheduleEntry.subject)).where(m.ScheduleEntry.teacher_id == teacher_id)
    if day:
        query = query.where(m.ScheduleEntry.day_of_week == day.value)
    return db.scalars(query.order_by(m.ScheduleEntry.day_of_week, m.ScheduleEntry.period_number)).all()

@router.get("/staff/me/assignments")
def staff_own_assignments(on_date: date | None = None, admin: m.AdminAccount | m.StaffAccount = Depends(require_school_scope), db: Session = Depends(get_db)):
    teacher_id = getattr(admin, "teacher_id", None)
    if teacher_id is None:
        return []
    query = select(m.SubstitutionAssignment).options(selectinload(m.SubstitutionAssignment.absent_teacher), selectinload(m.SubstitutionAssignment.school_class)).where(m.SubstitutionAssignment.substitute_teacher_id == teacher_id)
    if on_date:
        query = query.where(m.SubstitutionAssignment.date == on_date)
    return db.scalars(query.order_by(m.SubstitutionAssignment.date.desc(), m.SubstitutionAssignment.period_number)).all()

@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok", "database": "connected"}

@router.get("/school-settings")
def school_settings(db: Session = Depends(get_db)):
    item = db.scalar(select(m.SchoolSettings).where(m.SchoolSettings.school_id == _school_id(db)))
    school = db.get(m.School, _school_id(db))
    return {"school_name": item.school_name if item else (school.name if school else "المدرسة"), "school_logo_url": item.school_logo_url if item else None}

@router.put("/school-settings")
def update_school_settings(payload: SchoolSettingsIn, db: Session = Depends(get_db)):
    item = db.scalar(select(m.SchoolSettings).where(m.SchoolSettings.school_id == _school_id(db)))
    if item is None:
        item = m.SchoolSettings(school_id=_school_id(db), school_name=payload.school_name, school_logo_url=payload.school_logo_url)
        db.add(item)
    else:
        item.school_name = payload.school_name
        item.school_logo_url = payload.school_logo_url
    _commit(db)
    return item

@router.get("/teachers")
def teachers(active_only: bool = False, db: Session = Depends(get_db)):
    query = select(m.Teacher).options(selectinload(m.Teacher.subjects)).order_by(m.Teacher.name)
    if active_only: query = query.where(m.Teacher.is_active.is_(True))
    return db.scalars(query).all()

@router.post("/teachers", status_code=201)
def create_teacher(payload: TeacherIn, db: Session = Depends(get_db)):
    subjects = db.scalars(select(m.Subject).where(m.Subject.id.in_(payload.subject_ids))).all() if payload.subject_ids else []
    if len(subjects) != len(set(payload.subject_ids)): raise HTTPException(404, "أحد التخصصات غير موجود")
    item = m.Teacher(name=payload.name.strip(), is_active=payload.is_active, subjects=subjects)
    db.add(item); _commit(db, "اسم المعلم مستخدم مسبقًا")
    db.refresh(item); return item

@router.get("/teachers/{teacher_id}")
def get_teacher(teacher_id: int, db: Session = Depends(get_db)): return _teacher(db, teacher_id)

@router.put("/teachers/{teacher_id}")
def update_teacher(teacher_id: int, payload: TeacherIn, db: Session = Depends(get_db)):
    item = _teacher(db, teacher_id)
    subjects = db.scalars(select(m.Subject).where(m.Subject.id.in_(payload.subject_ids))).all() if payload.subject_ids else []
    if len(subjects) != len(set(payload.subject_ids)): raise HTTPException(404, "أحد التخصصات غير موجود")
    item.name = payload.name.strip(); item.is_active = payload.is_active; item.subjects = subjects
    _commit(db, "اسم المعلم مستخدم مسبقًا"); return item

@router.delete("/teachers/{teacher_id}", status_code=204)
def deactivate_teacher(teacher_id: int, db: Session = Depends(get_db)):
    item = _teacher(db, teacher_id); item.is_active = False; _commit(db)

@router.get("/subjects")
def subjects(db: Session = Depends(get_db)): return db.scalars(select(m.Subject).order_by(m.Subject.name)).all()

@router.post("/subjects", status_code=201)
def create_subject(payload: SubjectIn, db: Session = Depends(get_db)):
    item = m.Subject(name=payload.name.strip()); db.add(item); _commit(db, "اسم المادة موجود مسبقًا"); db.refresh(item); return item

@router.get("/classes")
def classes(db: Session = Depends(get_db)): return db.scalars(select(m.SchoolClass).order_by(m.SchoolClass.name)).all()

@router.post("/classes", status_code=201)
def create_class(payload: ClassIn, db: Session = Depends(get_db)):
    item = m.SchoolClass(**payload.model_dump()); db.add(item); _commit(db, "اسم الشعبة مستخدم مسبقًا"); db.refresh(item); return item

@router.get("/schedule")
def get_schedule(day: Day | None = None, teacher_id: int | None = None, db: Session = Depends(get_db)):
    query = select(m.ScheduleEntry).options(selectinload(m.ScheduleEntry.teacher), selectinload(m.ScheduleEntry.school_class), selectinload(m.ScheduleEntry.subject))
    if day: query = query.where(m.ScheduleEntry.day_of_week == day.value)
    if teacher_id: query = query.where(m.ScheduleEntry.teacher_id == teacher_id)
    return db.scalars(query.order_by(m.ScheduleEntry.day_of_week, m.ScheduleEntry.period_number, m.ScheduleEntry.teacher_id)).all()

@router.post("/schedule", status_code=201)
def create_schedule(payload: ScheduleIn, db: Session = Depends(get_db)):
    if not _teacher(db, payload.teacher_id).is_active: raise HTTPException(400, "المعلم غير نشط")
    if payload.class_id and not db.get(m.SchoolClass, payload.class_id): raise HTTPException(404, "الشعبة غير موجودة")
    if payload.subject_id and not db.get(m.Subject, payload.subject_id): raise HTTPException(404, "المادة غير موجودة")
    _check_schedule_assignment_conflict(db, payload.teacher_id, payload.day_of_week.value, payload.period_number, payload.status.value)
    item = m.ScheduleEntry(**payload.model_dump()); db.add(item); _commit(db, "يوجد إدخال لهذا المعلم في اليوم والحصة نفسها"); db.refresh(item); return item

@router.put("/schedule/{entry_id}")
def update_schedule(entry_id: int, payload: ScheduleIn, db: Session = Depends(get_db)):
    item = db.get(m.ScheduleEntry, entry_id)
    if not item: raise HTTPException(404, "خلية الجدول غير موجودة")
    if not db.get(m.Teacher, payload.teacher_id): raise HTTPException(404, "المعلم غير موجود")
    if payload.class_id and not db.get(m.SchoolClass, payload.class_id): raise HTTPException(404, "الشعبة غير موجودة")
    if payload.subject_id and not db.get(m.Subject, payload.subject_id): raise HTTPException(404, "المادة غير موجودة")
    _check_schedule_assignment_conflict(db, payload.teacher_id, payload.day_of_week.value, payload.period_number, payload.status.value)
    for key, value in payload.model_dump().items(): setattr(item, key, value)
    _commit(db, "يوجد إدخال لهذا المعلم في اليوم والحصة نفسها"); return item

@router.delete("/schedule/{entry_id}", status_code=204)
def delete_schedule(entry_id: int, db: Session = Depends(get_db)):
    item = db.get(m.ScheduleEntry, entry_id)
    if not item: raise HTTPException(404, "خلية الجدول غير موجودة")
    db.delete(item); _commit(db)

def _check_schedule_assignment_conflict(db: Session, teacher_id: int, day: str, period: int, status: str):
    """Keep timetable edits from making already-issued coverage assignments impossible."""
    if status == "FREE": return
    rows = db.scalars(select(m.SubstitutionAssignment).where(
        m.SubstitutionAssignment.substitute_teacher_id == teacher_id,
        m.SubstitutionAssignment.period_number == period,
        m.SubstitutionAssignment.status.in_(["ASSIGNED", "CONFIRMED", "COMPLETED"]),
    )).all()
    if any(school_day(row.date) == day for row in rows):
        raise HTTPException(409, "لا يمكن وضع تدريس أو مناوبة في فترة لديها تكليف احتياط قائم")

@router.post("/schedule/import-csv", include_in_schema=False)
@router.post("/schedule/import-file")
async def import_schedule_file(
    file: UploadFile = File(...),
    replace_existing: bool = False,
    db: Session = Depends(get_db),
    admin: m.AdminAccount = Depends(require_school_scope),
):
    """Auto-create teachers, subjects and classes, then import DOCX/CSV/XLSX cells atomically."""
    max_upload_bytes = 10 * 1024 * 1024
    content = await file.read(max_upload_bytes + 1)
    if len(content) > max_upload_bytes:
        raise HTTPException(413, "حجم ملف الجدول يجب ألا يتجاوز 10 ميغابايت")
    cells, layout = parse_schedule_file(file.filename or "schedule.csv", content)
    normalized_name = lambda name: " ".join(name.split())
    deduped = {}
    unique_cells = []
    duplicate_errors = []
    for number, cell in enumerate(cells, start=1):
        teacher_name = normalized_name(cell.teacher)
        class_name = normalized_name(cell.class_name) if cell.class_name else None
        key = (teacher_name, cell.day, cell.period)
        value = (cell.status, class_name, cell.subject, cell.notes)
        if key in deduped:
            if deduped[key] != value:
                duplicate_errors.append({"teacher": teacher_name, "day": cell.day, "period": cell.period,
                                        "issue": "للمعلم أكثر من قيمة مختلفة في الحصة نفسها"})
            continue
        deduped[key] = value
        unique_cells.append(cell)
    if duplicate_errors:
        raise HTTPException(400, {"message": "لم يتم الاستيراد؛ راجع خانات المعلم المكررة", "errors": duplicate_errors[:100]})
    cells = [
        type(cell)(normalized_name(cell.teacher), cell.day, cell.period, cell.status,
                   normalized_name(cell.class_name) if cell.class_name else None,
                   normalized_name(cell.subject) if cell.subject else None, cell.notes, cell.declared_load)
        for cell in unique_cells
    ]
    declared_loads = {cell.teacher: cell.declared_load for cell in cells if cell.declared_load is not None}
    actual_loads = Counter(cell.teacher for cell in cells if cell.status == "TEACHING")
    load_warnings = [
        {"teacher": teacher, "declared": declared, "found": actual_loads[teacher]}
        for teacher, declared in declared_loads.items() if actual_loads[teacher] != declared
    ]
    teachers_by_name = {t.name.strip(): t for t in db.scalars(select(m.Teacher)).all()}
    subjects_by_name = {s.name.strip(): s for s in db.scalars(select(m.Subject)).all()}
    classes_by_name = {c.name.strip(): c for c in db.scalars(select(m.SchoolClass)).all()}
    if not replace_existing:
        existing_names = {c.teacher for c in cells}
        existing_ids = {t.id for t in teachers_by_name.values() if t.name.strip() in existing_names}
        existing_cells = db.scalars(select(m.ScheduleEntry).where(m.ScheduleEntry.teacher_id.in_(existing_ids))).all() if existing_ids else []
        occupied = {(e.teacher_id, e.day_of_week, e.period_number) for e in existing_cells}
        conflicts = [c for c in cells if c.teacher in teachers_by_name and
                     (teachers_by_name[c.teacher].id, c.day, c.period) in occupied]
        if conflicts:
            raise HTTPException(409, {"message": "يوجد جدول سابق لبعض المعلمين؛ فعّل خيار استبدال الجدول أو امسح الخلايا المتعارضة.",
                                      "conflicts": [{"teacher": c.teacher, "day": c.day, "period": c.period} for c in conflicts[:100]]})
    try:
        if replace_existing:
            db.query(m.ScheduleEntry).delete(synchronize_session=False)
            incoming_names = {cell.teacher for cell in cells}
            for teacher in list(teachers_by_name.values()):
                teacher.subjects.clear()
                if teacher.name.strip() not in incoming_names:
                    has_history = bool(db.scalar(select(m.Absence.id).where(m.Absence.teacher_id == teacher.id).limit(1)))
                    has_assignment = bool(db.scalar(select(m.SubstitutionAssignment.id).where(
                        (m.SubstitutionAssignment.absent_teacher_id == teacher.id) |
                        (m.SubstitutionAssignment.substitute_teacher_id == teacher.id)).limit(1)))
                    if has_history or has_assignment:
                        teacher.is_active = False
                    else:
                        db.delete(teacher)
            for class_item in list(classes_by_name.values()):
                # Retain classes that are referenced by absence history; the FK nulls the old class on delete otherwise.
                used = bool(db.scalar(select(m.AbsencePeriod.id).where(m.AbsencePeriod.class_id == class_item.id).limit(1)))
                used = used or bool(db.scalar(select(m.SubstitutionAssignment.id).where(m.SubstitutionAssignment.class_id == class_item.id).limit(1)))
                if not used:
                    db.delete(class_item)
            db.flush()
            teachers_by_name = {t.name.strip(): t for t in db.scalars(select(m.Teacher)).all()}
            classes_by_name = {c.name.strip(): c for c in db.scalars(select(m.SchoolClass)).all()}
        # Build lookups/upserts from the whole file before creating schedule records.
        incoming_subjects = {c.subject for c in cells if c.subject}
        if replace_existing:
            for subject_name, subject_item in list(subjects_by_name.items()):
                if subject_name not in incoming_subjects:
                    db.delete(subject_item)
            db.flush()
            subjects_by_name = {s.name.strip(): s for s in db.scalars(select(m.Subject)).all()}
        for subject_name in incoming_subjects:
            if subject_name not in subjects_by_name:
                subject = m.Subject(name=subject_name)
                db.add(subject); db.flush(); subjects_by_name[subject_name] = subject
        incoming_teachers = {c.teacher for c in cells}
        for teacher_name in incoming_teachers:
            teacher = teachers_by_name.get(teacher_name)
            if teacher is None:
                teacher = m.Teacher(name=teacher_name)
                db.add(teacher); db.flush(); teachers_by_name[teacher_name] = teacher
            teacher.is_active = True
        incoming_classes = {c.class_name for c in cells if c.class_name}
        for class_name in incoming_classes:
            if class_name not in classes_by_name:
                item = m.SchoolClass(name=class_name)
                db.add(item); db.flush(); classes_by_name[class_name] = item
        for cell in cells:
            if cell.subject:
                subject = subjects_by_name[cell.subject]
                teacher = teachers_by_name[cell.teacher]
                if subject not in teacher.subjects:
                    teacher.subjects.append(subject)
        for cell in cells:
            teacher = teachers_by_name[cell.teacher]
            db.add(m.ScheduleEntry(
                teacher_id=teacher.id, day_of_week=cell.day, period_number=cell.period,
                status=cell.status, class_id=classes_by_name[cell.class_name].id if cell.class_name else None,
                subject_id=subjects_by_name[cell.subject].id if cell.subject else None, notes=cell.notes,
            ))
        _audit(db, "schedule", 0, "IMPORTED", admin.username,
               f"{len(cells)} cells; {len(incoming_teachers)} teachers; replace={replace_existing}")
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "تعذر الحفظ بسبب أسماء أو خانات مكررة؛ لم تُحفظ أي تغييرات") from exc
    except Exception:
        db.rollback()
        raise
    reserve_slots = sum(1 for cell in cells if (cell.notes or "").startswith("RESERVE_PRIORITY:"))
    return {"imported": len(cells), "layout": layout, "teachers": len(incoming_teachers),
            "subjects": len(incoming_subjects), "classes": len(incoming_classes), "replaced": replace_existing,
            "reserve_slots": reserve_slots, "load_warnings": load_warnings,
            "message": "تمت قراءة الملف وإنشاء المعلمين والتخصصات والشعب والحصص تلقائيًا."}

@router.post("/absences", status_code=201)
def create_absence(payload: AbsenceIn, db: Session = Depends(get_db), admin: m.AdminAccount = Depends(require_school_scope)):
    teacher = _teacher(db, payload.teacher_id)
    if not teacher.is_active: raise HTTPException(400, "المعلم غير نشط")
    try: day = school_day(payload.date)
    except ValueError as exc: raise HTTPException(400, str(exc)) from exc
    absence = m.Absence(teacher_id=teacher.id, date=payload.date, reason=payload.reason, created_by=admin.username)
    db.add(absence); db.flush()
    results = []
    for period_data in payload.periods:
        period = period_data.period_number
        absent_entry = db.scalar(select(m.ScheduleEntry).options(selectinload(m.ScheduleEntry.school_class), selectinload(m.ScheduleEntry.subject)).where(
            m.ScheduleEntry.teacher_id == teacher.id, m.ScheduleEntry.day_of_week == day, m.ScheduleEntry.period_number == period))
        class_id = period_data.class_id or (absent_entry.class_id if absent_entry else None)
        if period_data.class_id and not db.get(m.SchoolClass, period_data.class_id): db.rollback(); raise HTTPException(404, "الشعبة غير موجودة")
        if absent_entry and absent_entry.status != "TEACHING" and not period_data.class_id: db.rollback(); raise HTTPException(400, f"المعلم ليس لديه حصة تدريسية في الحصة {period}؛ اختر الشعبة يدويًا إذا كان هناك تكليف مختلف عن الجدول")
        if not absent_entry and not period_data.class_id: db.rollback(); raise HTTPException(400, f"لا توجد حصة مسجلة للمعلم في الحصة {period}؛ حدد الشعبة يدويًا أو أدخل الجدول أولًا")
        ap = m.AbsencePeriod(absence_id=absence.id, period_number=period, class_id=class_id); db.add(ap); db.flush()
        assignment = m.SubstitutionAssignment(absence_period_id=ap.id, absent_teacher_id=teacher.id, date=payload.date, period_number=period,
            class_id=class_id, created_by=admin.username)
        db.add(assignment); db.flush()
        subject_id = absent_entry.subject_id if absent_entry else None
        candidates = suggest_candidates(db, absent_teacher=teacher, on_date=payload.date, period=period, subject_id=subject_id)
        selected_class = db.get(m.SchoolClass, class_id) if class_id else None
        results.append({"assignment_id": assignment.id, "period": period, "class": selected_class.name if selected_class else None,
                        "subject": absent_entry.subject.name if absent_entry and absent_entry.subject else None,
                        "status": "SUGGESTED", "recommended_substitute": candidates[0] if candidates else None, "candidates": candidates})
    _audit(db, "absence", absence.id, "CREATED", admin.username, f"{len(results)} حصص")
    _commit(db)
    return {"absence_id": absence.id, "absent_teacher": {"id": teacher.id, "name": teacher.name}, "date": payload.date, "day": day, "periods": results}

@router.get("/absences")
def list_absences(from_date: date | None = None, to_date: date | None = None, db: Session = Depends(get_db)):
    query = select(m.Absence).options(selectinload(m.Absence.teacher), selectinload(m.Absence.periods)).order_by(m.Absence.date.desc())
    if from_date: query = query.where(m.Absence.date >= from_date)
    if to_date: query = query.where(m.Absence.date <= to_date)
    return db.scalars(query).all()

@router.get("/absences/{absence_id}")
def get_absence(absence_id: int, db: Session = Depends(get_db)):
    item = db.scalar(select(m.Absence).options(selectinload(m.Absence.teacher), selectinload(m.Absence.periods)).where(m.Absence.id == absence_id))
    if not item: raise HTTPException(404, "سجل الغياب غير موجود")
    return item

@router.post("/substitutions/suggest")
def suggest_substitution(payload: SuggestIn, db: Session = Depends(get_db)):
    teacher = _teacher(db, payload.teacher_id)
    if not teacher.is_active: raise HTTPException(400, "المعلم غير نشط")
    try: day = school_day(payload.date)
    except ValueError as exc: raise HTTPException(400, str(exc)) from exc
    entry = db.scalar(select(m.ScheduleEntry).options(selectinload(m.ScheduleEntry.school_class), selectinload(m.ScheduleEntry.subject)).where(
        m.ScheduleEntry.teacher_id == teacher.id, m.ScheduleEntry.day_of_week == day, m.ScheduleEntry.period_number == payload.period_number))
    class_id = payload.class_id or (entry.class_id if entry else None)
    if entry and entry.status != "TEACHING": raise HTTPException(400, "المعلم ليس لديه حصة تدريسية في الفترة المحددة")
    if not entry and not class_id: raise HTTPException(400, "لا توجد حصة في الجدول؛ حدد الشعبة أو أدخل الجدول أولًا")
    if class_id and not db.get(m.SchoolClass, class_id): raise HTTPException(404, "الشعبة غير موجودة")
    candidates = suggest_candidates(db, absent_teacher=teacher, on_date=payload.date, period=payload.period_number, subject_id=entry.subject_id if entry else None)
    return {"absent_teacher": {"id": teacher.id, "name": teacher.name}, "date": payload.date, "day": day, "period": payload.period_number,
            "class": entry.school_class.name if entry and entry.school_class else (db.get(m.SchoolClass, class_id).name if class_id else None),
            "recommended_substitute": candidates[0] if candidates else None, "alternative_candidates": candidates[1:], "candidates": candidates,
            "result": "recommended" if candidates else "no_available_substitute"}

@router.get("/substitutions")
def substitutions(on_date: date | None = None, db: Session = Depends(get_db)):
    query = select(m.SubstitutionAssignment).options(selectinload(m.SubstitutionAssignment.absent_teacher), selectinload(m.SubstitutionAssignment.substitute_teacher), selectinload(m.SubstitutionAssignment.school_class))
    if on_date: query = query.where(m.SubstitutionAssignment.date == on_date)
    return db.scalars(query.order_by(m.SubstitutionAssignment.date.desc(), m.SubstitutionAssignment.period_number)).all()

@router.post("/substitutions/{assignment_id}/assign")
def assign_substitute(assignment_id: int, payload: AssignIn, db: Session = Depends(get_db), admin: m.AdminAccount = Depends(require_school_scope)):
    assignment = db.get(m.SubstitutionAssignment, assignment_id)
    if not assignment: raise HTTPException(404, "تكليف الاحتياط غير موجود")
    if assignment.status in ("CANCELLED", "COMPLETED"): raise HTTPException(409, "لا يمكن تغيير تكليف ملغى أو مكتمل")
    candidate = _teacher(db, payload.substitute_teacher_id)
    if not candidate.is_active: raise HTTPException(400, "المعلم غير نشط")
    absent = _teacher(db, assignment.absent_teacher_id)
    candidates = suggest_candidates(db, absent_teacher=absent, on_date=assignment.date, period=assignment.period_number,
        subject_id=None)
    if candidate.id not in {c["id"] for c in candidates} and candidate.id != assignment.substitute_teacher_id:
        raise HTTPException(409, "المعلم غير متاح في هذه الحصة أو لديه تعارض")
    assignment.substitute_teacher_id = candidate.id; assignment.waiting_location = payload.waiting_location
    assignment.notes = payload.notes; assignment.status = "ASSIGNED"; assignment.approved_by = admin.username
    assignment.approved_at = datetime.now(timezone.utc)
    _audit(db, "substitution", assignment.id, "ASSIGNED", admin.username, f"substitute={candidate.id}")
    _commit(db, "هذا المعلم مكلف باحتياط آخر في الحصة نفسها"); return assignment

@router.post("/substitutions/{assignment_id}/confirm")
def confirm_substitute(assignment_id: int, payload: StatusIn, db: Session = Depends(get_db), admin: m.AdminAccount = Depends(require_school_scope)):
    item = db.get(m.SubstitutionAssignment, assignment_id)
    if not item: raise HTTPException(404, "تكليف الاحتياط غير موجود")
    if not item.substitute_teacher_id or item.status not in ("ASSIGNED", "CONFIRMED"): raise HTTPException(409, "يجب تعيين معلم قبل التأكيد")
    item.status = "CONFIRMED"; item.signature = admin.username
    _audit(db, "substitution", item.id, "CONFIRMED", admin.username); _commit(db); return item

@router.post("/substitutions/{assignment_id}/complete")
def complete_substitute(assignment_id: int, payload: StatusIn, db: Session = Depends(get_db), admin: m.AdminAccount = Depends(require_school_scope)):
    item = db.get(m.SubstitutionAssignment, assignment_id)
    if not item: raise HTTPException(404, "تكليف الاحتياط غير موجود")
    if item.status not in ("ASSIGNED", "CONFIRMED"): raise HTTPException(409, "التكليف غير مسند")
    item.status = "COMPLETED"; _audit(db, "substitution", item.id, "COMPLETED", admin.username); _commit(db); return item

@router.post("/substitutions/{assignment_id}/cancel")
def cancel_substitute(assignment_id: int, payload: StatusIn, db: Session = Depends(get_db), admin: m.AdminAccount = Depends(require_school_scope)):
    item = db.get(m.SubstitutionAssignment, assignment_id)
    if not item: raise HTTPException(404, "تكليف الاحتياط غير موجود")
    former_substitute = item.substitute_teacher_id
    item.status = "CANCELLED"; item.substitute_teacher_id = None
    _audit(db, "substitution", item.id, "CANCELLED", admin.username, f"former_substitute={former_substitute}"); _commit(db); return item

@router.get("/dashboard/today")
def dashboard(on_date: date | None = None, db: Session = Depends(get_db)):
    target = on_date or datetime.now(ZoneInfo(settings.school_timezone)).date()
    rows = db.scalars(select(m.SubstitutionAssignment).options(selectinload(m.SubstitutionAssignment.absent_teacher), selectinload(m.SubstitutionAssignment.substitute_teacher), selectinload(m.SubstitutionAssignment.school_class)).where(m.SubstitutionAssignment.date == target).order_by(m.SubstitutionAssignment.period_number)).all()
    workloads = db.execute(select(m.Teacher.name, func.count(m.SubstitutionAssignment.id)).join(m.SubstitutionAssignment, m.SubstitutionAssignment.substitute_teacher_id == m.Teacher.id).where(m.SubstitutionAssignment.date == target, m.SubstitutionAssignment.status.in_(["ASSIGNED", "CONFIRMED", "COMPLETED"])).group_by(m.Teacher.id, m.Teacher.name).order_by(func.count(m.SubstitutionAssignment.id).desc())).all()
    return {"date": target, "total_absent_teachers": len({r.absent_teacher_id for r in rows}), "affected_periods": len(rows), "substitutions_required": len(rows),
        "assigned": sum(r.status in ("ASSIGNED", "CONFIRMED", "COMPLETED") for r in rows), "pending": sum(r.status == "SUGGESTED" for r in rows),
        "unassigned": sum(r.status == "SUGGESTED" for r in rows), "workload": [{"teacher": name, "assignments": count} for name, count in workloads], "assignments": rows}

@router.get("/dashboard/overview")
def dashboard_overview(db: Session = Depends(get_db)):
    """Return a compact readiness summary without loading the full timetable."""
    active_teachers = db.scalar(select(func.count(m.Teacher.id)).where(m.Teacher.is_active.is_(True))) or 0
    subject_count = db.scalar(select(func.count(m.Subject.id))) or 0
    class_count = db.scalar(select(func.count(m.SchoolClass.id)).where(m.SchoolClass.is_active.is_(True))) or 0
    status_counts = db.execute(
        select(m.ScheduleEntry.status, func.count(m.ScheduleEntry.id))
        .join(m.Teacher, m.Teacher.id == m.ScheduleEntry.teacher_id)
        .where(m.Teacher.is_active.is_(True))
        .group_by(m.ScheduleEntry.status)
    ).all()
    counts = {status: count for status, count in status_counts}
    configured = sum(counts.values())
    day_periods = db.execute(
        select(m.ScheduleEntry.day_of_week, func.max(m.ScheduleEntry.period_number))
        .join(m.Teacher, m.Teacher.id == m.ScheduleEntry.teacher_id)
        .where(m.Teacher.is_active.is_(True))
        .group_by(m.ScheduleEntry.day_of_week)
    ).all()
    # Some school timetables have fewer periods on particular days. Once all
    # five school days are represented, use their actual period counts; for a
    # partial or empty import retain the standard 5×7 readiness target.
    periods_per_week = sum(max_period for _, max_period in day_periods) if len(day_periods) == 5 else 5 * 7
    expected = active_teachers * periods_per_week
    missing = max(0, expected - configured)
    return {
        "active_teachers": active_teachers,
        "subjects": subject_count,
        "classes": class_count,
        "configured_slots": configured,
        "expected_slots": expected,
        "missing_slots": missing,
        "completion_percent": round(configured * 100 / expected) if expected else 0,
        "teaching_slots": counts.get("TEACHING", 0),
        "free_slots": counts.get("FREE", 0),
        "duty_slots": counts.get("DUTY", 0),
        "other_slots": counts.get("OTHER", 0),
    }

@router.get("/reports/daily-substitutions")
def daily_report(on_date: date, db: Session = Depends(get_db)):
    # Reports can be opened for any calendar date, including days without classes.
    day = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")[on_date.weekday()]
    rows = db.scalars(select(m.SubstitutionAssignment).options(selectinload(m.SubstitutionAssignment.absent_teacher), selectinload(m.SubstitutionAssignment.substitute_teacher), selectinload(m.SubstitutionAssignment.school_class)).where(m.SubstitutionAssignment.date == on_date).order_by(m.SubstitutionAssignment.period_number)).all()
    branding = db.scalar(select(m.SchoolSettings).where(m.SchoolSettings.school_id == _school_id(db)))
    school = db.get(m.School, _school_id(db))
    return {"date": on_date, "day": day, "school_name": branding.school_name if branding else (school.name if school else "المدرسة"), "assignments": rows}

@router.get("/audit")
def audit_log(entity_type: str | None = None, db: Session = Depends(get_db)):
    query = select(m.AuditLog).order_by(m.AuditLog.created_at.desc())
    if entity_type: query = query.where(m.AuditLog.entity_type == entity_type)
    return db.scalars(query.limit(500)).all()
