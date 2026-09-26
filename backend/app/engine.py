"""Explainable database-backed substitute candidate selection."""
from collections import defaultdict
from datetime import date
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, selectinload
from .models import Teacher, ScheduleEntry, SubstitutionAssignment
from .core import AssignmentStatus

WEEKDAY_TO_DAY = {6: "SUNDAY", 0: "MONDAY", 1: "TUESDAY", 2: "WEDNESDAY", 3: "THURSDAY"}

def school_day(value: date) -> str:
    """Convert ISO weekday to the school's Sunday-Thursday calendar."""
    try:
        return WEEKDAY_TO_DAY[value.weekday()]
    except KeyError as exc:
        raise ValueError("لا توجد حصص مجدولة يوم الجمعة أو السبت") from exc

def suggest_candidates(db: Session, *, absent_teacher: Teacher, on_date: date, period: int, subject_id: int | None) -> list[dict]:
    """Filter candidates in SQL, then rank by subject fit, workload, and ID."""
    day = school_day(on_date)
    scheduled = select(ScheduleEntry.teacher_id).where(
        ScheduleEntry.day_of_week == day,
        ScheduleEntry.period_number == period,
        ScheduleEntry.status != "FREE",
    )
    assigned = select(SubstitutionAssignment.substitute_teacher_id).where(
        SubstitutionAssignment.date == on_date,
        SubstitutionAssignment.period_number == period,
        SubstitutionAssignment.substitute_teacher_id.is_not(None),
        SubstitutionAssignment.status.in_([AssignmentStatus.ASSIGNED, AssignmentStatus.CONFIRMED, AssignmentStatus.COMPLETED]),
    )
    free_query = select(Teacher).join(ScheduleEntry, ScheduleEntry.teacher_id == Teacher.id).where(
        Teacher.is_active.is_(True), Teacher.id != absent_teacher.id,
        ScheduleEntry.day_of_week == day, ScheduleEntry.period_number == period,
        ScheduleEntry.status == "FREE", ~Teacher.id.in_(scheduled), ~Teacher.id.in_(assigned),
    ).distinct()
    free_query = free_query.options(selectinload(Teacher.subjects))
    teachers = list(db.scalars(free_query).all())
    daily_rows = db.execute(select(SubstitutionAssignment.substitute_teacher_id, func.count()).where(
        SubstitutionAssignment.date == on_date, SubstitutionAssignment.status.in_(["ASSIGNED", "CONFIRMED", "COMPLETED"]),
        SubstitutionAssignment.substitute_teacher_id.is_not(None),
    ).group_by(SubstitutionAssignment.substitute_teacher_id)).all()
    history_rows = db.execute(select(SubstitutionAssignment.substitute_teacher_id, func.count()).where(
        SubstitutionAssignment.status.in_(["ASSIGNED", "CONFIRMED", "COMPLETED"]),
        SubstitutionAssignment.substitute_teacher_id.is_not(None),
    ).group_by(SubstitutionAssignment.substitute_teacher_id)).all()
    daily = dict(daily_rows); history = dict(history_rows)
    candidates = []
    for teacher in teachers:
        match = bool(subject_id and any(subject.id == subject_id for subject in teacher.subjects))
        candidates.append({"id": teacher.id, "name": teacher.name, "specialization": ", ".join(s.name for s in teacher.subjects),
            "daily_assignments": daily.get(teacher.id, 0), "historical_assignments": history.get(teacher.id, 0),
            "subject_match": match, "reasons": ["متاح في هذه الحصة", "خانة الجدول فارغة ومحددة كفراغ",
                "لا يوجد لديه تدريس أو احتياط متعارض", "التخصص مطابق" if match else "ترتيب التخصص غير مطابق" ]})
    candidates.sort(key=lambda item: (not item["subject_match"], item["daily_assignments"], item["historical_assignments"], item["id"]))
    if candidates:
        candidates[0]["reasons"].append("عدد احتياطاته اليوم هو الأقل ضمن المرشحين المتاحين" if candidates[0]["daily_assignments"] == min(c["daily_assignments"] for c in candidates) else "ترتيبه ناتج عن مطابقة التخصص ثم توازن عبء الاحتياط")
    return candidates
