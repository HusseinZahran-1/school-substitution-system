"""First-run administrator setup and signed, HTTP-only login sessions."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models as m
from .core import settings
from .database import get_db
from .schemas import AdminLoginIn, AdminSetupIn

auth_router = APIRouter(prefix="/api/auth", tags=["authentication"])
SESSION_COOKIE = "school_admin_session"
SESSION_HOURS = 8
PASSWORD_ITERATIONS = 420_000
_SESSION_SECRET = (
    settings.session_secret.encode("utf-8")
    if settings.session_secret
    else secrets.token_bytes(48)
)


def _password_digest(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS).hex()


def _issue_token(username: str) -> str:
    expires = int(time.time()) + SESSION_HOURS * 60 * 60
    payload = f"{username}\n{expires}".encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    signature = hmac.new(_SESSION_SECRET, encoded.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def _token_username(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    encoded, supplied_signature = token.rsplit(".", 1)
    expected = hmac.new(_SESSION_SECRET, encoded.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, supplied_signature):
        return None
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        username, expires_text = base64.urlsafe_b64decode(padded).decode("utf-8").split("\n", 1)
        if int(expires_text) <= int(time.time()):
            return None
        return username
    except (ValueError, UnicodeDecodeError):
        return None


def require_admin(request: Request, db: Session = Depends(get_db)) -> m.AdminAccount:
    username = _token_username(request.cookies.get(SESSION_COOKIE))
    if not username:
        raise HTTPException(status_code=401, detail="يلزم تسجيل الدخول للمتابعة")
    admin = db.scalar(select(m.AdminAccount).where(m.AdminAccount.username == username))
    if not admin:
        raise HTTPException(status_code=401, detail="انتهت جلسة الدخول؛ سجل الدخول مرة أخرى")
    return admin


@auth_router.get("/status")
def auth_status(request: Request, db: Session = Depends(get_db)):
    setup_required = db.scalar(select(func.count()).select_from(m.AdminAccount)) == 0
    username = _token_username(request.cookies.get(SESSION_COOKIE))
    authenticated = bool(username and db.scalar(select(m.AdminAccount.id).where(m.AdminAccount.username == username)))
    return {"setup_required": setup_required, "authenticated": authenticated, "username": username if authenticated else None}


@auth_router.post("/setup", status_code=201)
def setup_admin(payload: AdminSetupIn, request: Request, response: Response, db: Session = Depends(get_db)):
    if db.scalar(select(func.count()).select_from(m.AdminAccount)):
        raise HTTPException(status_code=409, detail="تم إعداد حساب الإدارة مسبقًا؛ سجل الدخول")
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="كلمتا المرور غير متطابقتين")
    salt = secrets.token_bytes(24)
    account = m.AdminAccount(username=payload.username.strip(), password_salt=salt.hex(), password_hash=_password_digest(payload.password, salt))
    db.add(account)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    response.set_cookie(SESSION_COOKIE, _issue_token(account.username), max_age=SESSION_HOURS * 3600,
                        httponly=True, secure=request.url.scheme == "https", samesite="lax", path="/")
    return {"authenticated": True, "username": account.username}


@auth_router.post("/login")
def login(payload: AdminLoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    account = db.scalar(select(m.AdminAccount).where(m.AdminAccount.username == payload.username.strip()))
    valid = False
    if account:
        try:
            valid = hmac.compare_digest(_password_digest(payload.password, bytes.fromhex(account.password_salt)), account.password_hash)
        except ValueError:
            valid = False
    if not valid:
        raise HTTPException(status_code=401, detail="اسم المستخدم أو كلمة المرور غير صحيحة")
    response.set_cookie(SESSION_COOKIE, _issue_token(account.username), max_age=SESSION_HOURS * 3600,
                        httponly=True, secure=request.url.scheme == "https", samesite="lax", path="/")
    return {"authenticated": True, "username": account.username}


@auth_router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, httponly=True, samesite="lax", path="/")
    return {"authenticated": False}
