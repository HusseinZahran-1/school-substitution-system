from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from backend.app.main import app
from backend.app.database import get_db
from backend.app import models as m

def test_unknown_teacher_returns_404(db: Session):
    def override_db():
        yield db
    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).get("/api/teachers/9999")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()

def test_existing_teacher_is_readable(db: Session):
    db.add(m.Teacher(name="موجود")); db.commit()
    def override_db():
        yield db
    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).get("/api/teachers/1")
        assert response.status_code == 200
        assert response.json()["name"] == "موجود"
    finally:
        app.dependency_overrides.clear()

def test_absence_returns_reviewable_candidates_and_assigns_separately(db: Session):
    from datetime import date
    absent = m.Teacher(name="معلم غائب")
    substitute = m.Teacher(name="معلم متاح")
    subject = m.Subject(name="علوم")
    absent.subjects.append(subject)
    db.add_all([absent, substitute, subject]); db.flush()
    cls = m.SchoolClass(name="2/ب"); db.add(cls); db.flush()
    db.add_all([
        m.ScheduleEntry(teacher_id=absent.id, day_of_week="THURSDAY", period_number=3, status="TEACHING", subject_id=subject.id, class_id=cls.id),
        m.ScheduleEntry(teacher_id=substitute.id, day_of_week="THURSDAY", period_number=3, status="FREE"),
    ])
    db.commit()
    def override_db():
        yield db
    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        response = client.post("/api/absences", json={"teacher_id": absent.id, "date": str(date(2026, 9, 24)), "periods": [{"period_number": 3}]})
        assert response.status_code == 201, response.text
        item = response.json()["periods"][0]
        assert item["recommended_substitute"]["id"] == substitute.id
        assert item["status"] == "SUGGESTED"
        assignment = client.post(f"/api/substitutions/{item['assignment_id']}/assign", json={"substitute_teacher_id": substitute.id})
        assert assignment.status_code == 200, assignment.text
        assert assignment.json()["status"] == "ASSIGNED"
    finally:
        app.dependency_overrides.clear()

def test_imported_teachers_are_active_and_available_for_absence(db: Session):
    import io
    from datetime import date
    from fastapi.testclient import TestClient

    def override_db():
        yield db
    app.dependency_overrides[get_db] = override_db
    csv_content = (
        "teacher,day,period,status,رقم الشعبة,subject,notes\n"
        "معلم مستورد,الأحد,1,TEACHING,1/2,رياضيات,\n"
        "معلم مستورد,الأحد,2,FREE,,,\n"
        "معلم بديل,الأحد,1,FREE,,,\n"
    ).encode("utf-8")
    try:
        client = TestClient(app)
        imported = client.post(
            "/api/schedule/import-file?replace_existing=true",
            files={"file": ("schedule.csv", io.BytesIO(csv_content), "text/csv")},
        )
        assert imported.status_code == 200, imported.text
        staff = client.get("/api/teachers?active_only=true")
        assert staff.status_code == 200
        teachers = {item["name"]: item for item in staff.json()}
        assert "معلم مستورد" in teachers
        assert teachers["معلم مستورد"]["is_active"] is True
        classes = client.get("/api/classes")
        assert classes.status_code == 200
        assert "1/2" in {item["name"] for item in classes.json()}
        override_class = client.post("/api/classes", json={"name": "2/3"})
        assert override_class.status_code == 201, override_class.text
        overview = client.get("/api/dashboard/overview")
        assert overview.status_code == 200
        assert overview.json()["active_teachers"] == 2
        assert overview.json()["configured_slots"] == 3
        assert overview.json()["expected_slots"] == 70

        absence = client.post("/api/absences", json={
            "teacher_id": teachers["معلم مستورد"]["id"],
            "date": str(date(2026, 9, 27)),
            "periods": [
                {"period_number": 1, "class_id": override_class.json()["id"]},
                {"period_number": 2, "class_id": override_class.json()["id"]},
            ],
        })
        assert absence.status_code == 201, absence.text
        assert absence.json()["absent_teacher"]["name"] == "معلم مستورد"
        assert [item["class"] for item in absence.json()["periods"]] == ["2/3", "2/3"]
    finally:
        app.dependency_overrides.clear()
