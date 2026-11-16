"""Authorization integration tests, including tenant isolation and live revocation."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.app import api, models as m, security
from backend.app.database import get_db
from backend.app.main import app


@pytest.fixture
def access_client(db):
    db.info.pop("school_id", None)
    manager = m.AdminAccount(school_id=1, username="manager", email="manager@example.com",
                             password_hash=security._password_digest("Manager-pass-123"), password_salt="")
    other_school = m.School(name="Other school")
    teacher = m.Teacher(school_id=1, name="Teacher one")
    db.add_all([manager, other_school, teacher]); db.flush()
    db.add(m.LicenseKey(key_hash="test-license", status="ACTIVATED", assigned_user_id=manager.id))
    staff = m.StaffAccount(school_id=1, teacher_id=teacher.id, username="staff", email="staff@example.com",
                          role="TEACHER", password_hash=security._password_digest("Teacher-pass-123"), is_active=True)
    db.add(staff); db.commit()
    app.dependency_overrides.pop(security.require_admin, None)
    def session():
        with Session(db.get_bind(), expire_on_commit=False) as request_db:
            yield request_db
    app.dependency_overrides[get_db] = session
    client = TestClient(app, headers={"Origin": "http://testserver"})
    client.cookies.set(security.SESSION_COOKIE, security._issue_token("manager"))
    yield client, db, staff.id, other_school.id
    app.dependency_overrides.pop(get_db, None)


def test_role_lifecycle_assignment_and_live_revocation(access_client):
    client, db, staff_id, _ = access_client
    result = client.post("/api/roles", json={"name": "مسؤول التقارير", "permissions": ["reports.view"]})
    assert result.status_code == 201, result.text
    role_id = result.json()["id"]
    result = client.put(f"/api/staff/{staff_id}", json={"role": "CUSTOM", "custom_role_id": role_id})
    assert result.status_code == 200, result.text
    assert result.json()["role_name"] == "مسؤول التقارير"
    assert client.delete(f"/api/roles/{role_id}").status_code == 409
    client.cookies.set(security.SESSION_COOKIE, security._issue_token("staff", purpose="staff", session_version=1))
    assert client.get("/api/staff/me").json()["permissions"] == ["reports.view"]
    assert client.get("/api/reports/daily-substitutions?on_date=2026-10-22").status_code == 200
    for path in ["/api/roles", "/api/staff", "/api/teachers", "/api/schedule", "/api/substitutions", "/api/audit"]:
        assert client.get(path).status_code == 403, path
    assert client.post("/api/roles", json={"name": "Escalation", "permissions": []}).status_code == 403
    assert client.put(f"/api/staff/{staff_id}", json={"role": "COORDINATOR"}).status_code == 403
    # Same staff cookie loses permission as soon as the manager edits the role.
    manager_client = TestClient(app, headers={"Origin": "http://testserver"})
    manager_client.cookies.set(security.SESSION_COOKIE, security._issue_token("manager"))
    assert manager_client.put(f"/api/roles/{role_id}", json={"name": "عرض شخصي", "permissions": []}).status_code == 200
    assert client.get("/api/reports/daily-substitutions?on_date=2026-10-22").status_code == 403
    assert client.get("/api/staff/me/schedule").status_code == 200
    assert client.get("/api/staff/me/assignments").status_code == 200
    assert manager_client.put(f"/api/staff/{staff_id}", json={"role": "TEACHER"}).status_code == 200
    assert manager_client.delete(f"/api/roles/{role_id}").status_code == 204
    assert client.get("/api/staff/me").status_code == 401  # assigned-role change revokes session
    db.expire_all()
    assert db.scalar(select(m.AuditLog.id).where(m.AuditLog.entity_type == "role"))


def test_tenant_isolation_validation_and_permission_dependencies(access_client):
    client, db, staff_id, other_school = access_client
    foreign = m.SchoolRole(school_id=other_school, name="Private", permissions=["schedule.edit"])
    db.add(foreign); db.commit()
    assert not client.get("/api/roles").json()["roles"]
    assert client.put(f"/api/roles/{foreign.id}", json={"name": "Stolen", "permissions": []}).status_code == 404
    assert client.delete(f"/api/roles/{foreign.id}").status_code == 404
    assert client.put(f"/api/staff/{staff_id}", json={"role":"CUSTOM", "custom_role_id":foreign.id}).status_code == 404
    assert client.put(f"/api/staff/{staff_id}", json={"role":"MANAGER"}).status_code == 422
    for invalid in ["manager", "roles.manage", "staff.manage", "made.up"]:
        assert client.post("/api/roles", json={"name":"Invalid", "permissions":[invalid]}).status_code == 422
    for invalid in [" ", "مدير", "معلم"]:
        assert client.post("/api/roles", json={"name":invalid, "permissions":[]}).status_code == 422
    created = client.post("/api/roles", json={"name":"مشرف الجدول", "permissions":["schedule.import"]})
    assert set(created.json()["permissions"]) == {"schedule.import", "schedule.edit", "schedule.view", "directory.view", "directory.edit"}
    assert client.post("/api/roles", json={"name":"مشرف الجدول"}).status_code == 409


@pytest.mark.parametrize("role,allowed,denied", [
    ("TEACHER", ["/api/staff/me/schedule", "/api/staff/me/assignments"], ["/api/schedule", "/api/substitutions", "/api/staff", "/api/roles"]),
    ("COORDINATOR", ["/api/schedule", "/api/substitutions", "/api/teachers", "/api/audit"], ["/api/staff", "/api/roles"]),
])
def test_builtin_roles_keep_their_boundaries(access_client, role, allowed, denied):
    client, db, staff_id, _ = access_client
    staff = db.get(m.StaffAccount, staff_id); staff.role=role; db.commit()
    client.cookies.set(security.SESSION_COOKIE, security._issue_token("staff", purpose="staff"))
    for path in allowed:
        assert client.get(path).status_code == 200, path
    for path in denied:
        assert client.get(path).status_code == 403, path
    assert client.post("/api/schedule", json={}).status_code == 403
    assert client.post("/api/schedule/import-file").status_code == 403
    assert client.put("/api/school-settings", json={"school_name":"No"}).status_code == 403


def test_invitation_preserves_custom_role_and_is_single_use(access_client, monkeypatch):
    client, db, _, _ = access_client
    role = client.post("/api/roles", json={"name":"متابعة", "permissions":["reports.view"]}).json()
    teacher=m.Teacher(school_id=1, name="Invited teacher");db.add(teacher);db.commit()
    messages=[]
    monkeypatch.setattr(api.settings,"email_host","smtp.example.test")
    monkeypatch.setattr(api.settings,"email_from","school@example.com")
    monkeypatch.setattr(api,"send_staff_invitation_email",lambda *args:messages.append(args))
    result=client.post("/api/staff",json={"teacher_id":teacher.id,"username":"invited","email":"invited@example.com","role":"CUSTOM","custom_role_id":role["id"]})
    assert result.status_code==201,result.text
    assert messages[0][3]=="متابعة"
    token=messages[0][-1].split("#staff_invite=")[1]
    payload={"token":token,"password":"New-password-123","confirm_password":"New-password-123"}
    assert client.post("/api/auth/accept-staff-invite",json=payload).status_code==200
    assert client.get("/api/staff/me").json()["permissions"]==["reports.view"]
    assert client.post("/api/auth/accept-staff-invite",json=payload).status_code==400


def test_role_writes_reject_missing_or_hostile_origin(access_client):
    client, *_ = access_client
    assert client.post("/api/roles",json={"name":"blocked"},headers={"Origin":"https://other.example"}).status_code==403
    del client.headers["Origin"]
    assert client.post("/api/roles",json={"name":"blocked"}).status_code==403


def test_custom_schedule_editor_can_edit_but_cannot_import_or_manage_people(access_client):
    client, db, staff_id, _ = access_client
    role = client.post("/api/roles", json={"name":"محرر الحصص", "permissions":["schedule.edit"]}).json()
    assert client.put(f"/api/staff/{staff_id}", json={"role":"CUSTOM", "custom_role_id":role["id"]}).status_code == 200
    teacher_id = db.get(m.StaffAccount, staff_id).teacher_id
    client.cookies.set(security.SESSION_COOKIE, security._issue_token("staff", purpose="staff", session_version=1))
    payload = {"teacher_id":teacher_id, "day_of_week":"SUNDAY", "period_number":1, "status":"FREE"}
    created = client.post("/api/schedule",json=payload)
    assert created.status_code == 201, created.text
    assert client.put(f"/api/schedule/{created.json()['id']}",json={**payload,"status":"DUTY"}).status_code == 200
    assert client.get("/api/teachers").status_code == 200
    assert client.post("/api/teachers",json={"name":"Forbidden"}).status_code == 403
    assert client.post("/api/schedule/import-file").status_code == 403
    assert client.delete(f"/api/schedule/{created.json()['id']}").status_code == 204


def test_personal_portal_only_returns_linked_teacher_records(access_client):
    client, db, staff_id, _ = access_client
    own = db.get(m.StaffAccount, staff_id).teacher_id
    other=m.Teacher(school_id=1,name="Other colleague");db.add(other);db.flush()
    for teacher_id in [own,other.id]:
        db.add(m.ScheduleEntry(school_id=1,teacher_id=teacher_id,day_of_week="SUNDAY",period_number=1,status="FREE"))
    db.commit()
    client.cookies.set(security.SESSION_COOKIE,security._issue_token("staff",purpose="staff"))
    result=client.get(f"/api/staff/me/schedule?teacher_id={other.id}")
    assert result.status_code == 200
    assert [row["teacher_id"] for row in result.json()] == [own]
