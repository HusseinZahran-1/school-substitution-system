"""Create the first active school administrator from an interactive shell."""
from datetime import datetime, timezone
from getpass import getpass
import secrets

from sqlalchemy import func, select

from . import models
from .database import SessionLocal
from .schemas import AdminRegisterIn
from .security import _license_hash, _password_digest


def main() -> None:
    school_name = input("School name: ").strip()
    username = input("Admin username (no spaces): ").strip()
    email = input("Admin email: ").strip()
    password = getpass("Admin password (10+ chars, letters and numbers): ")
    confirmation = getpass("Confirm password: ")

    payload = AdminRegisterIn(
        username=username,
        email=email,
        password=password,
        confirm_password=confirmation,
    )

    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(models.AdminAccount)):
            raise SystemExit("An administrator already exists; refusing to create another bootstrap account.")

        account = models.AdminAccount(
            username=payload.username,
            email=str(payload.email),
            password_salt="",
            password_hash=_password_digest(payload.password),
        )
        school = models.School(name=school_name or f"مدرسة {username}")
        db.add(school)
        db.flush()
        account.school_id = school.id
        db.add(account)
        db.add(models.SchoolSettings(school_id=school.id, school_name=school.name))
        db.flush()
        db.add(models.LicenseKey(
            key_hash=_license_hash(secrets.token_urlsafe(32)),
            status="ACTIVATED",
            assigned_user_id=account.id,
            activated_at=datetime.now(timezone.utc),
        ))
        db.commit()

    print(f"Administrator {payload.username!r} created and activated.")


if __name__ == "__main__":
    main()
