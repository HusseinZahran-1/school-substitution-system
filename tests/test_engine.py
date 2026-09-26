from datetime import date
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from backend.app import models as m
from backend.app.engine import school_day, suggest_candidates

THURSDAY = date(2026, 9, 24)

def setup_school(db):
    math = m.Subject(name="رياضيات"); arabic = m.Subject(name="عربي")
    absent = m.Teacher(name="الغائب", subjects=[math]); free_math = m.Teacher(name="حر رياضيات", subjects=[math])
    free_other = m.Teacher(name="حر عربي", subjects=[arabic]); busy = m.Teacher(name="مشغول", subjects=[math])
    db.add_all([math, arabic, absent, free_math, free_other, busy]); db.flush()
    cls = m.SchoolClass(name="2/ب"); db.add(cls); db.flush()
    def entry(t, status, subject=math):
        db.add(m.ScheduleEntry(teacher_id=t.id, day_of_week="THURSDAY", period_number=3, status=status,
                               class_id=cls.id if status == "TEACHING" else None, subject_id=subject.id if subject else None))
    entry(absent, "TEACHING"); entry(free_math, "FREE"); entry(free_other, "FREE", arabic); entry(busy, "TEACHING")
    db.commit()
    return absent, free_math, free_other, busy, cls, math

def test_date_maps_to_school_day():
    assert school_day(THURSDAY) == "THURSDAY"

def test_weekends_rejected():
    with pytest.raises(ValueError): school_day(date(2026, 9, 25))

def test_teacher_exists_and_absent_teacher_never_candidate(db):
    absent, fm, fo, busy, _, math = setup_school(db)
    ids = [x["id"] for x in suggest_candidates(db, absent_teacher=absent, on_date=THURSDAY, period=3, subject_id=math.id)]
    assert absent.id not in ids

def test_free_teacher_is_selected_and_subject_match_ranks_first(db):
    absent, fm, fo, busy, _, math = setup_school(db)
    candidates = suggest_candidates(db, absent_teacher=absent, on_date=THURSDAY, period=3, subject_id=math.id)
    assert candidates[0]["id"] == fm.id
    assert candidates[0]["subject_match"] is True

def test_busy_teacher_is_excluded(db):
    absent, fm, fo, busy, _, math = setup_school(db)
    ids = [x["id"] for x in suggest_candidates(db, absent_teacher=absent, on_date=THURSDAY, period=3, subject_id=math.id)]
    assert busy.id not in ids

def test_existing_assignment_excludes_candidate(db):
    absent, fm, fo, busy, cls, math = setup_school(db)
    other = m.Teacher(name="غائب آخر"); db.add(other); db.flush()
    absence = m.Absence(teacher_id=other.id, date=THURSDAY); db.add(absence); db.flush()
    ap = m.AbsencePeriod(absence_id=absence.id, period_number=3, class_id=cls.id); db.add(ap); db.flush()
    db.add(m.SubstitutionAssignment(absence_period_id=ap.id, absent_teacher_id=other.id, substitute_teacher_id=fm.id, date=THURSDAY, period_number=3, class_id=cls.id, status="ASSIGNED")); db.commit()
    candidates = suggest_candidates(db, absent_teacher=absent, on_date=THURSDAY, period=3, subject_id=math.id)
    assert fm.id not in {x["id"] for x in candidates}

def test_unique_substitute_period_constraint(db):
    absent, fm, fo, busy, cls, _ = setup_school(db)
    a2 = m.Teacher(name="غائب إضافي"); db.add(a2); db.flush(); absence = m.Absence(teacher_id=a2.id, date=THURSDAY); db.add(absence); db.flush()
    ap1 = m.AbsencePeriod(absence_id=absence.id, period_number=1, class_id=cls.id); ap2 = m.AbsencePeriod(absence_id=absence.id, period_number=2, class_id=cls.id); db.add_all([ap1, ap2]); db.flush()
    db.add_all([m.SubstitutionAssignment(absence_period_id=ap1.id, absent_teacher_id=a2.id, substitute_teacher_id=fm.id, date=THURSDAY, period_number=3, status="ASSIGNED"),
                m.SubstitutionAssignment(absence_period_id=ap2.id, absent_teacher_id=a2.id, substitute_teacher_id=fm.id, date=THURSDAY, period_number=3, status="ASSIGNED")])
    with pytest.raises(IntegrityError): db.commit()

def test_fairness_orders_by_daily_workload(db):
    absent, fm, fo, busy, cls, math = setup_school(db)
    other = m.Teacher(name="غائب آخر"); db.add(other); db.flush(); absence = m.Absence(teacher_id=other.id, date=THURSDAY); db.add(absence); db.flush()
    ap = m.AbsencePeriod(absence_id=absence.id, period_number=2, class_id=cls.id); db.add(ap); db.flush()
    db.add(m.SubstitutionAssignment(absence_period_id=ap.id, absent_teacher_id=other.id, substitute_teacher_id=fm.id, date=THURSDAY, period_number=2, status="ASSIGNED")); db.commit()
    candidates = suggest_candidates(db, absent_teacher=absent, on_date=THURSDAY, period=3, subject_id=None)
    assert candidates[0]["id"] == fo.id

def test_no_free_candidates_returns_empty(db):
    absent, fm, fo, busy, _, math = setup_school(db)
    for teacher in [fm, fo]:
        entry = db.scalar(select(m.ScheduleEntry).where(m.ScheduleEntry.teacher_id == teacher.id))
        entry.status = "DUTY"
    db.commit()
    assert suggest_candidates(db, absent_teacher=absent, on_date=THURSDAY, period=3, subject_id=math.id) == []

def test_duplicate_schedule_is_rejected(db):
    absent, fm, fo, busy, _, _ = setup_school(db)
    db.add(m.ScheduleEntry(teacher_id=fm.id, day_of_week="THURSDAY", period_number=3, status="FREE"))
    with pytest.raises(IntegrityError): db.commit()

def test_invalid_period_is_rejected_by_database(db):
    t = m.Teacher(name="اختبار"); db.add(t); db.flush()
    db.add(m.ScheduleEntry(teacher_id=t.id, day_of_week="THURSDAY", period_number=8, status="FREE"))
    with pytest.raises(IntegrityError): db.commit()

def test_inactive_teacher_is_not_candidate(db):
    absent, fm, fo, busy, _, math = setup_school(db); fm.is_active = False; db.commit()
    ids = [x["id"] for x in suggest_candidates(db, absent_teacher=absent, on_date=THURSDAY, period=3, subject_id=math.id)]
    assert fm.id not in ids

def test_teacher_without_free_cell_is_not_candidate(db):
    absent, fm, fo, busy, _, math = setup_school(db)
    db.delete(db.scalar(select(m.ScheduleEntry).where(m.ScheduleEntry.teacher_id == fm.id))); db.commit()
    ids = [x["id"] for x in suggest_candidates(db, absent_teacher=absent, on_date=THURSDAY, period=3, subject_id=math.id)]
    assert fm.id not in ids
