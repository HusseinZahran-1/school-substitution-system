"""Registration, one-time license activation, and signed administrator sessions."""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
import base64
import hashlib
import hmac
import logging
import re
import secrets
import smtplib
import threading
import time
from pathlib import Path

from argon2 import PasswordHasher, exceptions as argon2_exceptions
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models as m
from .core import settings
from .permissions import account_access, required_permission
from .database import get_db
from .notifications import (
    EmailDeliveryNotConfigured,
    activated_license_message,
    created_license_message,
    send_activation_email,
    send_staff_invitation_email,
    send_discord_notification,
)
from .schemas import AdminLoginIn, AdminRegisterIn, LicenseActivationIn, StaffInviteAcceptIn

auth_router = APIRouter(prefix="/api/auth", tags=["authentication"])
SESSION_COOKIE = "school_admin_session"
ACTIVATION_COOKIE = "school_admin_activation"
SESSION_DAYS = 30
ACTIVATION_MINUTES = 10
STAFF_INVITE_HOURS = 24
_LOGGER = logging.getLogger(__name__)


def _load_session_secret() -> bytes:
    if settings.session_secret:
        return settings.session_secret.encode("utf-8")
    path = Path(__file__).resolve().parents[1] / ".session_secret"
    try:
        return path.read_text(encoding="utf-8").strip().encode("utf-8")
    except FileNotFoundError:
        secret = secrets.token_urlsafe(48)
        try:
            with path.open("x", encoding="utf-8") as key_file:
                key_file.write(secret)
        except FileExistsError:
            secret = path.read_text(encoding="utf-8").strip()
        return secret.encode("utf-8")


_SESSION_SECRET = _load_session_secret()
_RATE_LOCK = threading.Lock()
_RATE_ATTEMPTS: dict[str, deque[float]] = defaultdict(deque)
_LICENSE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
_PASSWORD_HASHER = PasswordHasher()


def _rate_limit(request: Request, action: str, limit: int, window_seconds: int) -> None:
    remote = request.client.host if request.client else "unknown"
    key = f"{action}:{remote}"
    now = time.monotonic()
    with _RATE_LOCK:
        attempts = _RATE_ATTEMPTS[key]
        while attempts and now - attempts[0] >= window_seconds:
            attempts.popleft()
        if len(attempts) >= limit:
            raise HTTPException(status_code=429, detail="محاولات كثيرة؛ انتظر قليلًا ثم حاول مرة أخرى")
        attempts.append(now)
        if len(_RATE_ATTEMPTS) > 10_000:
            for stale_key in [k for k, values in _RATE_ATTEMPTS.items() if not values]:
                _RATE_ATTEMPTS.pop(stale_key, None)


def _issue_token(username: str, purpose: str = "session", ttl_seconds: int = SESSION_DAYS * 86400, session_version: int = 0) -> str:
    expires = int(time.time()) + ttl_seconds
    payload = f"{purpose}\n{username}\n{expires}\n{session_version}".encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    signature = hmac.new(_SESSION_SECRET, encoded.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def _password_digest(password: str) -> str:
    return _PASSWORD_HASHER.hash(password)


def _verify_password(account: m.AdminAccount, password: str) -> bool:
    stored_hash = account.password_hash
    if stored_hash.startswith("$argon2"):
        try:
            return _PASSWORD_HASHER.verify(stored_hash, password)
        except (argon2_exceptions.VerifyMismatchError, argon2_exceptions.InvalidHashError):
            return False
    # Verify historical PBKDF2 hashes once, then upgrade successful logins to Argon2id.
    try:
        salt = bytes.fromhex(account.password_salt)
    except ValueError:
        return False
    legacy_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 420_000).hex()
    if not hmac.compare_digest(legacy_hash, stored_hash):
        return False
    account.password_hash = _password_digest(password)
    account.password_salt = ""
    return True


def _read_token(token: str | None) -> tuple[str, str, int] | None:
    if not token or "." not in token:
        return None
    encoded, supplied_signature = token.rsplit(".", 1)
    expected = hmac.new(_SESSION_SECRET, encoded.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, supplied_signature):
        return None
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        parts = base64.urlsafe_b64decode(padded).decode("utf-8").split("\n")
        # Accept prior signed session cookies during rolling upgrades.
        if len(parts) == 2:
            purpose, username, expires_text, session_version = "session", parts[0], parts[1], "0"
        elif len(parts) == 3:
            purpose, username, expires_text = parts
            session_version = "0"
        elif len(parts) == 4:
            purpose, username, expires_text, session_version = parts
        else:
            return None
        if int(expires_text) <= int(time.time()):
            return None
        return purpose, username, int(session_version)
    except (ValueError, UnicodeDecodeError):
        return None


def _license_hash(activation_key: str) -> str:
    pepper = (settings.license_hash_secret or "").encode("utf-8") or _SESSION_SECRET
    canonical_key = activation_key.replace("-", "").upper()
    return hmac.new(pepper, canonical_key.encode("ascii"), hashlib.sha256).hexdigest()


def _new_license_key() -> str:
    raw = "".join(secrets.choice(_LICENSE_ALPHABET) for _ in range(16))
    return "-".join(raw[index:index + 4] for index in range(0, 16, 4))


def _has_active_license(db: Session, user_id: int) -> bool:
    return db.scalar(
        select(m.LicenseKey.id).where(
            m.LicenseKey.assigned_user_id == user_id,
            m.LicenseKey.status == "ACTIVATED",
        )
    ) is not None


def _set_session(response: Response, request: Request, username: str, purpose: str = "session", session_version: int = 0) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        _issue_token(username, purpose=purpose, session_version=session_version),
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        secure=settings.session_cookie_secure or request.url.scheme == "https",
        samesite="lax",
        path="/",
    )
    response.delete_cookie(ACTIVATION_COOKIE, httponly=True, samesite="lax", path="/")


def _notify_discord(message: str) -> None:
    try:
        send_discord_notification(message)
    except Exception as exc:
        # Webhook delivery is best-effort and must never undo a committed account/license.
        status = getattr(exc, "code", None)
        suffix = f" (HTTP {status})" if status else ""
        _LOGGER.warning("Discord license notification could not be delivered (%s%s)", type(exc).__name__, suffix)


def require_admin(request: Request, db: Session = Depends(get_db)) -> m.AdminAccount | m.StaffAccount:
    token_data = _read_token(request.cookies.get(SESSION_COOKIE))
    if not token_data or token_data[0] not in {"session", "staff"}:
        raise HTTPException(status_code=401, detail="يلزم تسجيل الدخول للمتابعة")
    if token_data[0] == "session":
        account = db.scalar(select(m.AdminAccount).where(m.AdminAccount.username == token_data[1]))
        if not account or token_data[2] != account.session_version or not _has_active_license(db, account.id):
            raise HTTPException(status_code=401, detail="الحساب غير مفعّل؛ سجل الدخول وفعّل مفتاح الترخيص")
        return account
    staff = db.scalar(select(m.StaffAccount).where(m.StaffAccount.username == token_data[1]))
    if not staff or token_data[2] != staff.session_version or not staff.is_active or not staff.teacher.is_active:
        raise HTTPException(status_code=401, detail="حساب الموظف غير نشط؛ راجع مدير المدرسة")
    return staff


def require_school_scope(
    request: Request,
    admin: m.AdminAccount | m.StaffAccount = Depends(require_admin),
    db: Session = Depends(get_db),
) -> m.AdminAccount | m.StaffAccount:
    """Bind the authenticated account's school to every ORM operation in this request."""
    db.info["school_id"] = admin.school_id
    access = account_access(admin)
    method, path = request.method.upper(), request.url.path.rstrip("/")
    common_read = method == "GET" and path in {
        "/api/staff/me", "/api/staff/me/schedule", "/api/staff/me/assignments", "/api/school-settings",
    }
    required = required_permission(method, path)
    if not (access["role"] == "MANAGER" or common_read or (required and required in access["permissions"])):
        raise HTTPException(status_code=403, detail="ليس لديك صلاحية لتنفيذ هذا الإجراء")
    return admin


@auth_router.get("/status")
def auth_status(request: Request, db: Session = Depends(get_db)):
    username = None
    authenticated = False
    activation_required = False
    role = None

    session_data = _read_token(request.cookies.get(SESSION_COOKIE))
    if session_data and session_data[0] == "session":
        account = db.scalar(select(m.AdminAccount).where(m.AdminAccount.username == session_data[1]))
        if account and session_data[2] == account.session_version and _has_active_license(db, account.id):
            username = account.username
            authenticated = True
            role = "MANAGER"
    elif session_data and session_data[0] == "staff":
        account = db.scalar(select(m.StaffAccount).where(m.StaffAccount.username == session_data[1]))
        if account and session_data[2] == account.session_version and account.is_active and account.teacher.is_active:
            username = account.username
            authenticated = True
            role = account.role

    if not authenticated:
        pending_data = _read_token(request.cookies.get(ACTIVATION_COOKIE))
        if pending_data and pending_data[0] == "activation":
            account = db.scalar(select(m.AdminAccount).where(m.AdminAccount.username == pending_data[1]))
            if account and not _has_active_license(db, account.id):
                username = account.username
                activation_required = True

    return {
        "setup_required": db.scalar(select(func.count()).select_from(m.AdminAccount)) == 0,
        "registration_available": settings.registration_enabled,
        "authenticated": authenticated,
        "activation_required": activation_required,
        "username": username,
        "role": role if authenticated else None,
    }


@auth_router.post("/register", status_code=201)
@auth_router.post("/setup", status_code=201, include_in_schema=False)
def register(payload: AdminRegisterIn, request: Request, db: Session = Depends(get_db)):
    if not settings.registration_enabled:
        raise HTTPException(status_code=403, detail="التسجيل مغلق حاليًا")
    _rate_limit(request, "register", limit=5, window_seconds=3600)
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="كلمتا المرور غير متطابقتين")
    if not settings.email_host or not settings.email_from:
        raise HTTPException(status_code=503, detail="خدمة البريد غير مهيأة؛ أضف إعدادات SMTP في ملف .env")
    if (db.scalar(select(m.AdminAccount.id).where(func.lower(m.AdminAccount.username) == payload.username)) or
            db.scalar(select(m.StaffAccount.id).where(func.lower(m.StaffAccount.username) == payload.username))):
        raise HTTPException(status_code=409, detail="اسم المستخدم مستخدم مسبقًا")
    if (db.scalar(select(m.AdminAccount.id).where(func.lower(m.AdminAccount.email) == str(payload.email))) or
            db.scalar(select(m.StaffAccount.id).where(func.lower(m.StaffAccount.email) == str(payload.email)))):
        raise HTTPException(status_code=409, detail="البريد الإلكتروني مستخدم مسبقًا")
    activation_key = _new_license_key()
    school = m.School(name=payload.school_name or f"مدرسة {payload.username}")
    db.add(school)
    db.flush()
    account = m.AdminAccount(
        school_id=school.id,
        username=payload.username,
        email=str(payload.email),
        password_salt="",
        password_hash=_password_digest(payload.password),
    )
    db.add(account)
    db.add(m.SchoolSettings(school_id=school.id, school_name=school.name))
    try:
        db.flush()
        db.add(m.LicenseKey(key_hash=_license_hash(activation_key), status="UNUSED"))
        db.flush()
        # Do not persist an account when its activation key could not be delivered.
        send_activation_email(account.email, activation_key)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="اسم المستخدم أو البريد الإلكتروني مستخدم مسبقًا") from exc
    except (EmailDeliveryNotConfigured, OSError, smtplib.SMTPException) as exc:
        db.rollback()
        _LOGGER.warning(
            "Activation email delivery failed (%s; SMTP code=%s)",
            type(exc).__name__,
            getattr(exc, "smtp_code", None),
        )
        raise HTTPException(
            status_code=503,
            detail="تعذر إرسال مفتاح التفعيل. تحقق من بيانات SMTP والسماح باتصال SMTP الصادر من الجهاز أو الاستضافة.",
        ) from exc

    _notify_discord(created_license_message(activation_key))
    return {"registered": True, "activation_required": True, "email": account.email}


@auth_router.post("/login")
def login(payload: AdminLoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    _rate_limit(request, "login", limit=10, window_seconds=300)
    account = db.scalar(select(m.AdminAccount).where(func.lower(m.AdminAccount.username) == payload.username))
    staff = None
    if account is None:
        staff = db.scalar(select(m.StaffAccount).where(func.lower(m.StaffAccount.username) == payload.username))
        account = staff
    valid = False
    if account:
        valid = _verify_password(account, payload.password)
    if not valid:
        raise HTTPException(status_code=401, detail="اسم المستخدم أو كلمة المرور غير صحيحة")
    if isinstance(account, m.StaffAccount):
        if not account.is_active or not account.teacher.is_active:
            raise HTTPException(status_code=403, detail="الحساب لم يُفعّل بعد؛ افتح رابط الدعوة المرسل إلى بريدك")
        _set_session(response, request, account.username, purpose="staff", session_version=account.session_version)
        return {"authenticated": True, "activation_required": False, "username": account.username, "role": account.role}
    if account.password_hash.startswith("$argon2"):
        # Persist an Argon2 upgrade after validating a historical password.
        if account.password_salt:
            account.password_salt = ""
            db.commit()

    if not _has_active_license(db, account.id):
        response.delete_cookie(SESSION_COOKIE, httponly=True, samesite="lax", path="/")
        response.set_cookie(
            ACTIVATION_COOKIE,
            _issue_token(account.username, purpose="activation", ttl_seconds=ACTIVATION_MINUTES * 60),
            max_age=ACTIVATION_MINUTES * 60,
            httponly=True,
            secure=settings.session_cookie_secure or request.url.scheme == "https",
            samesite="lax",
            path="/",
        )
        return {"authenticated": False, "activation_required": True, "username": account.username}

    _set_session(response, request, account.username, session_version=account.session_version)
    return {"authenticated": True, "activation_required": False, "username": account.username, "role": "MANAGER"}


def _staff_invite_digest(token: str) -> str:
    return hmac.new(_SESSION_SECRET, token.encode("ascii"), hashlib.sha256).hexdigest()


@auth_router.post("/accept-staff-invite")
def accept_staff_invite(payload: StaffInviteAcceptIn, request: Request, response: Response, db: Session = Depends(get_db)):
    _rate_limit(request, "accept-staff-invite", limit=10, window_seconds=600)
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="كلمتا المرور غير متطابقتين")
    digest = _staff_invite_digest(payload.token)
    account = db.scalar(select(m.StaffAccount).where(m.StaffAccount.invite_token_hash == digest))
    now = datetime.now(timezone.utc)
    expires_at = account.invite_expires_at if account else None
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if not account or not expires_at or expires_at <= now or account.is_active:
        raise HTTPException(status_code=400, detail="رابط الدعوة غير صالح أو انتهت صلاحيته؛ اطلب من المدير إرسال دعوة جديدة")
    account.password_hash = _password_digest(payload.password)
    account.is_active = True
    account.invite_token_hash = None
    account.invite_expires_at = None
    db.commit()
    _set_session(response, request, account.username, purpose="staff", session_version=account.session_version)
    return {"authenticated": True, "username": account.username, "role": account.role}


@auth_router.post("/activate-license")
def activate_license(payload: LicenseActivationIn, request: Request, response: Response, db: Session = Depends(get_db)):
    _rate_limit(request, "activate-license", limit=10, window_seconds=600)
    token_data = _read_token(request.cookies.get(ACTIVATION_COOKIE))
    if not token_data or token_data[0] != "activation":
        raise HTTPException(status_code=401, detail="انتهت جلسة التفعيل؛ سجل الدخول مرة أخرى")
    account = db.scalar(select(m.AdminAccount).where(m.AdminAccount.username == token_data[1]))
    if not account:
        raise HTTPException(status_code=401, detail="الحساب غير موجود؛ أعد التسجيل")
    if _has_active_license(db, account.id):
        _set_session(response, request, account.username)
        return {"authenticated": True, "activated": True}

    license_row = db.scalar(
        select(m.LicenseKey)
        .where(m.LicenseKey.key_hash == _license_hash(payload.license_key))
        .with_for_update()
    )
    if not license_row or license_row.status != "UNUSED" or license_row.assigned_user_id is not None:
        raise HTTPException(status_code=400, detail="مفتاح التفعيل غير صحيح أو مستخدم مسبقًا")

    license_row.assigned_user_id = account.id
    license_row.status = "ACTIVATED"
    license_row.activated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="مفتاح التفعيل غير صحيح أو مستخدم مسبقًا") from exc

    _set_session(response, request, account.username)
    _notify_discord(activated_license_message(account.username, account.email))
    return {"authenticated": True, "activated": True}


@auth_router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token_data = _read_token(request.cookies.get(SESSION_COOKIE))
    if token_data:
        purpose, username, session_version = token_data
        if purpose == "session":
            account = db.scalar(select(m.AdminAccount).where(m.AdminAccount.username == username))
        elif purpose == "staff":
            account = db.scalar(select(m.StaffAccount).where(m.StaffAccount.username == username))
        else:
            account = None
        if account and account.session_version == session_version:
            account.session_version += 1
            db.commit()
    response.delete_cookie(SESSION_COOKIE, httponly=True, samesite="lax", path="/")
    response.delete_cookie(ACTIVATION_COOKIE, httponly=True, samesite="lax", path="/")
    return {"authenticated": False}
