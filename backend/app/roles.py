"""Manager-owned role definitions; employees cannot delegate their own access."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from . import models as m
from .database import get_db
from .permissions import BUILTIN_ROLES, DEPENDENCIES, PERMISSIONS
from .schemas import SchoolRoleIn
from .security import require_school_scope


def manager(account=Depends(require_school_scope)):
    if not isinstance(account, m.AdminAccount):
        raise HTTPException(403, "إدارة الأدوار متاحة لمدير المدرسة فقط")
    return account


roles_router = APIRouter(prefix="/api/roles", dependencies=[Depends(manager)])


def role_view(role, count=0):
    return {"id": role.id, "name": role.name, "description": role.description,
            "permissions": role.permissions, "member_count": count}


def save(db, role, action, actor):
    db.add(m.AuditLog(entity_type="role", entity_id=role.id, action=action,
                      actor=actor, detail=f"{role.name}: {', '.join(role.permissions)}"))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "الدور مستخدم أو اسمه موجود بالفعل؛ حدّث القائمة وحاول مجددًا") from exc


@roles_router.get("")
def list_roles(db: Session = Depends(get_db)):
    counts = dict(db.execute(select(m.StaffAccount.custom_role_id, func.count())
                            .group_by(m.StaffAccount.custom_role_id)).all())
    return {"catalog": PERMISSIONS, "dependencies": {k: sorted(v) for k, v in DEPENDENCIES.items()},
            "builtins": [{"key": key, **value} for key, value in BUILTIN_ROLES.items()],
            "roles": [role_view(role, counts.get(role.id, 0)) for role in db.scalars(select(m.SchoolRole).order_by(m.SchoolRole.name))]}


def unique_name(db, name, role_id=None):
    query = select(m.SchoolRole.id).where(func.lower(m.SchoolRole.name) == name.lower())
    if role_id:
        query = query.where(m.SchoolRole.id != role_id)
    if db.scalar(query):
        raise HTTPException(409, "يوجد دور بهذا الاسم في المدرسة")


@roles_router.post("", status_code=201)
def create_role(payload: SchoolRoleIn, db: Session = Depends(get_db), admin=Depends(manager)):
    unique_name(db, payload.name)
    role = m.SchoolRole(**payload.model_dump())
    db.add(role)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "يوجد دور بهذا الاسم في المدرسة") from exc
    save(db, role, "CREATED", admin.username)
    return role_view(role)


@roles_router.put("/{role_id}")
def update_role(role_id: int, payload: SchoolRoleIn, db: Session = Depends(get_db), admin=Depends(manager)):
    role = db.scalar(select(m.SchoolRole).where(m.SchoolRole.id == role_id).with_for_update())
    if not role:
        raise HTTPException(404, "الدور غير موجود")
    unique_name(db, payload.name, role.id)
    for key, value in payload.model_dump().items():
        setattr(role, key, value)
    save(db, role, "UPDATED", admin.username)
    return role_view(role)


@roles_router.delete("/{role_id}", status_code=204)
def delete_role(role_id: int, db: Session = Depends(get_db), admin=Depends(manager)):
    role = db.scalar(select(m.SchoolRole).where(m.SchoolRole.id == role_id).with_for_update())
    if not role:
        raise HTTPException(404, "الدور غير موجود")
    if db.scalar(select(m.StaffAccount.id).where(m.StaffAccount.custom_role_id == role_id).limit(1)):
        raise HTTPException(409, "غيّر أدوار الموظفين المرتبطين بهذا الدور قبل حذفه")
    db.delete(role)
    save(db, role, "DELETED", admin.username)
