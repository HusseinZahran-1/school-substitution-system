"""Explainable database-backed substitute candidate selection."""
from collections import defaultdict
from datetime import date
import re
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
    """Filter conflicts, then prioritize planned reserve slots before ordinary free periods."""
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
    free_query = select(Teacher, ScheduleEntry.notes).join(ScheduleEntry, ScheduleEntry.teacher_id == Teacher.id).where(
        Teacher.is_active.is_(True), Teacher.id != absent_teacher.id,
        ScheduleEntry.day_of_week == day, ScheduleEntry.period_number == period,
        ScheduleEntry.status == "FREE", ~Teacher.id.in_(scheduled), ~Teacher.id.in_(assigned),
    ).distinct()
    free_query = free_query.options(selectinload(Teacher.subjects))
    teachers = list(db.execute(free_query).all())
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
    for teacher, slot_notes in teachers:
        match = bool(subject_id and any(subject.id == subject_id for subject in teacher.subjects))
        reserve_match = re.search(r"(?:^|\b)RESERVE_PRIORITY:(\d+)(?:\b|$)", slot_notes or "", re.IGNORECASE)
        reserve_priority = int(reserve_match.group(1)) if reserve_match else None
        reserve_reason = (f"خانة احتياط ح{reserve_priority} حسب جدول المدرسة" if reserve_priority is not None
                         else "متاح في خانة فراغ عادية")
        candidates.append({"id": teacher.id, "name": teacher.name, "specialization": ", ".join(s.name for s in teacher.subjects),
            "daily_assignments": daily.get(teacher.id, 0), "historical_assignments": history.get(teacher.id, 0),
            "subject_match": match, "reserve_priority": reserve_priority, "reasons": ["متاح في هذه الحصة", reserve_reason,
                "لا يوجد لديه تدريس أو احتياط متعارض", "التخصص مطابق" if match else "ترتيب التخصص غير مطابق" ]})
    candidates.sort(key=lambda item: (
        item["reserve_priority"] is None,
        item["reserve_priority"] if item["reserve_priority"] is not None else 0,
        not item["subject_match"], item["daily_assignments"], item["historical_assignments"], item["id"],
    ))
    if candidates:
        if candidates[0]["reserve_priority"] is not None:
            candidates[0]["reasons"].append("أولوية الاحتياط المعتمدة تسبق الخانات الفارغة العادية")
        else:
            candidates[0]["reasons"].append("ترتيبه ناتج عن مطابقة التخصص ثم توازن عبء الاحتياط")
    return candidates
