
"""Server-side email delivery and Discord license notifications."""

import json
import smtplib
import ssl
from base64 import urlsafe_b64encode
from datetime import datetime, timezone
from email.message import EmailMessage
from html import escape
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .core import settings


class EmailDeliveryNotConfigured(RuntimeError):
    """Raised when the selected email provider is not configured."""
    pass


def _send_email(message: EmailMessage) -> None:
    """Send email using Gmail API over HTTPS or traditional SMTP."""

    if settings.email_provider == "gmail_api":
        _send_email_gmail_api(message)
    elif settings.email_provider == "smtp":
        _send_email_smtp(message)
    else:
        raise EmailDeliveryNotConfigured(
            "EMAIL_PROVIDER must be smtp or gmail_api"
        )


def _send_email_gmail_api(message: EmailMessage) -> None:
    """Send an existing MIME message through Gmail API."""

    client_id = settings.gmail_client_id
    client_secret = settings.gmail_client_secret
    refresh_token = settings.gmail_refresh_token
    sender = settings.email_from

    if not all((client_id, client_secret, refresh_token, sender)):
        raise EmailDeliveryNotConfigured(
            "Gmail API credentials or EMAIL_FROM are missing"
        )

    token_body = urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode("utf-8")

    token_request = Request(
        "https://oauth2.googleapis.com/token",
        data=token_body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with urlopen(token_request, timeout=15) as response:
            token_data = json.load(response)

        access_token = token_data.get("access_token")
        if not access_token:
            raise RuntimeError(
                "Google OAuth did not return an access token"
            )

        raw_message = urlsafe_b64encode(
            message.as_bytes()
        ).decode("ascii").rstrip("=")

        payload = json.dumps({
            "raw": raw_message
        }).encode("utf-8")

        send_request = Request(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            data=payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        with urlopen(send_request, timeout=20) as response:
            if response.status not in (200, 201):
                raise RuntimeError(
                    f"Gmail API returned HTTP {response.status}"
                )

    except HTTPError as exc:
        raise RuntimeError(
            f"Gmail API request failed (HTTP {exc.code}). "
            "Check OAuth permissions and sender configuration."
        ) from exc

    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(
            "Unable to connect to Gmail API"
        ) from exc

    except (KeyError, ValueError) as exc:
        raise RuntimeError(
            "Invalid response from Gmail API"
        ) from exc


def _send_email_smtp(message: EmailMessage) -> None:
    """Send email using the original SMTP configuration."""

    host = settings.email_host
    sender = settings.email_from

    if not host or not sender:
        raise EmailDeliveryNotConfigured(
            "SMTP email delivery is not configured"
        )

    context = ssl.create_default_context()

    if settings.email_use_ssl:
        client = smtplib.SMTP_SSL(
            host,
            settings.email_port,
            timeout=15,
            context=context,
        )
    else:
        client = smtplib.SMTP(
            host,
            settings.email_port,
            timeout=15,
        )

    try:
        if settings.email_use_starttls and not settings.email_use_ssl:
            client.starttls(context=context)

        if settings.email_username:
            client.login(
                settings.email_username,
                settings.email_password or "",
            )

        client.send_message(message)

    finally:
        try:
            client.quit()
        except (OSError, smtplib.SMTPException):
            client.close()


def _email_styles() -> str:
    """Shared styling for HTML emails."""
    return """
    <style>
      body {
        margin: 0;
        padding: 0;
        background: #edf3f1;
        color: #183b35;
        font-family: Arial, Tahoma, sans-serif;
      }
      .email-container {
        width: 100%;
        max-width: 600px;
        margin: 0 auto;
        background: #ffffff;
        border: 1px solid #dce8e3;
        border-radius: 18px;
        overflow: hidden;
      }
      .email-header {
        background: #087e68;
        padding: 28px 30px;
        color: #ffffff;
        text-align: right;
      }
      .email-body {
        padding: 30px;
        line-height: 1.85;
      }
      .email-footer {
        padding: 20px 30px;
        background: #f5faf8;
        border-top: 1px solid #e5eeea;
        color: #526a62;
        text-align: center;
        font-size: 13px;
      }
      .action-button {
        display: inline-block;
        padding: 14px 26px;
        background: #087e68;
        color: #ffffff !important;
        text-decoration: none;
        border-radius: 9px;
        font-weight: bold;
      }
      .muted {
        color: #647871;
        font-size: 13px;
      }
    </style>
    """


def send_activation_email(recipient: str, activation_key: str) -> None:
    """Send the one-time license activation key."""

    sender = settings.email_from

    if not sender:
        raise EmailDeliveryNotConfigured(
            "EMAIL_FROM is not configured"
        )

    message = EmailMessage()
    message["Subject"] = (
        "تفعيل حسابك | Activate your account - "
        "نظام إدارة جدول الاحتياط"
    )
    message["From"] = sender
    message["To"] = recipient

    message.set_content(
        "مرحبًا،\n\n"
        "تم إنشاء حسابك في نظام إدارة جدول الاحتياط المدرسي بنجاح.\n"
        "لإكمال التفعيل، سجّل الدخول إلى النظام وأدخل مفتاح التفعيل التالي:\n\n"
        "مفتاح التفعيل | ACTIVATION KEY:\n"
        f"{activation_key}\n\n"
        "يُستخدم المفتاح مرة واحدة فقط؛ احتفظ به ولا تشاركه مع أي شخص.\n"
        "إذا لم تطلب إنشاء هذا الحساب، يمكنك تجاهل هذه الرسالة.\n\n"
        "Hello,\n\n"
        "Your account for the School Substitution Management System is ready.\n"
        "To activate it, sign in and enter the activation key above.\n"
        "The key can only be used once. Keep it private and do not share it.\n\n"
        "If you did not request this account, you can ignore this email.\n\n"
        "مع تحيات، Best regards,\n"
        "إدارة النظام | System Administration"
    )

    safe_key = escape(activation_key)
    styles = _email_styles()

    html_content = f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{styles}
</head>
<body>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"
       style="background:#edf3f1;padding:28px 12px;">
  <tr>
    <td align="center">
      <div class="email-container">

        <div class="email-header">
          <div style="font-size:13px;color:#d8f4eb;">
            نظام إدارة جدول الاحتياط المدرسي
          </div>
          <div dir="ltr"
               style="font-size:12px;color:#d8f4eb;text-align:left;">
            School Substitution Management System
          </div>

          <div style="margin-top:20px;font-size:25px;font-weight:bold;">
            تفعيل حسابك
          </div>
          <div dir="ltr"
               style="font-size:18px;text-align:left;font-weight:bold;">
            Activate your account
          </div>
        </div>

        <div class="email-body">
          <p>مرحبًا بك 👋</p>

          <p>
            تم إنشاء حسابك بنجاح في نظام إدارة جدول الاحتياط المدرسي.
            لإكمال التفعيل، سجّل الدخول وأدخل مفتاح التفعيل التالي:
          </p>

          <div style="
            margin:24px 0;
            padding:22px 12px;
            text-align:center;
            background:#eff8f5;
            border:1px solid #cce8dd;
            border-radius:14px;
          ">
            <div style="font-size:12px;font-weight:bold;color:#55756b;">
              مفتاح التفعيل | ACTIVATION KEY
            </div>

            <div dir="ltr" style="
              margin-top:12px;
              padding:16px 8px;
              background:#ffffff;
              border:1px dashed #087e68;
              border-radius:10px;
              font-family:Consolas,'Courier New',monospace;
              font-size:22px;
              font-weight:bold;
              letter-spacing:2px;
              color:#075d4d;
              overflow-wrap:anywhere;
            ">{safe_key}</div>
          </div>

          <p>
            يُستخدم المفتاح مرة واحدة فقط.
            احتفظ به ولا تشاركه مع أي شخص.
          </p>

          <p class="muted">
            إذا لم تطلب إنشاء هذا الحساب، يمكنك تجاهل الرسالة.
          </p>

          <hr style="border:0;border-top:1px solid #e5eeea;margin:25px 0;">

          <div dir="ltr" style="text-align:left;">
            <h3 style="color:#087e68;">Hello!</h3>
            <p>
              Your account has been created successfully.
              Sign in and enter the activation key above.
            </p>
            <p>
              This key can only be used once.
              Please keep it private.
            </p>
            <p class="muted">
              If you did not request this account,
              you can safely ignore this email.
            </p>
          </div>
        </div>

        <div class="email-footer">
          إدارة النظام | System Administration
          <div style="margin-top:5px;">
            نظام إدارة جدول الاحتياط المدرسي
          </div>
        </div>

      </div>
    </td>
  </tr>
</table>
</body>
</html>"""

    message.add_alternative(
        html_content,
        subtype="html",
    )

    _send_email(message)


def send_staff_invitation_email(
    recipient: str,
    school_name: str,
    teacher_name: str,
    role: str,
    invitation_link: str,
) -> None:
    """Send a one-time staff invitation link valid for 24 hours."""

    sender = settings.email_from

    if not sender:
        raise EmailDeliveryNotConfigured(
            "EMAIL_FROM is not configured"
        )

    role_label = {
        "COORDINATOR": "منسق",
        "TEACHER": "معلم",
    }.get(role, role)

    safe_school = escape(school_name)
    safe_teacher = escape(teacher_name)
    safe_role = escape(role_label)
    safe_link = escape(invitation_link, quote=True)

    message = EmailMessage()
    message["Subject"] = "دعوة حساب مدرسي | School account invitation"
    message["From"] = sender
    message["To"] = recipient

    message.set_content(
        f"مرحبًا {teacher_name}،\n\n"
        f"دُعيت لاستخدام نظام بديل بصفة {role_label} في {school_name}.\n"
        "أكمل إعداد حسابك من الرابط التالي "
        "(صالح لمرة واحدة ولمدة 24 ساعة):\n"
        f"{invitation_link}\n\n"
        "Hello,\n"
        "You were invited to the School Substitution System.\n"
        "Use the link above within 24 hours to set your password."
    )

    styles = _email_styles()

    html_content = f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{styles}
</head>
<body>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"
       style="background:#edf3f1;padding:28px 12px;">
  <tr>
    <td align="center">
      <div class="email-container">

        <div class="email-header">
          <div style="font-size:13px;color:#d8f4eb;">
            نظام بديل | Badil System
          </div>
          <div style="margin-top:18px;font-size:25px;font-weight:bold;">
            دعوة للانضمام إلى المدرسة
          </div>
          <div dir="ltr" style="text-align:left;font-size:17px;">
            School Account Invitation
          </div>
        </div>

        <div class="email-body">
          <h2 style="color:#087e68;margin-top:0;">
            أهلًا {safe_teacher} 👋
          </h2>

          <p>
            دعاك مدير <strong>{safe_school}</strong>
            للانضمام إلى نظام إدارة جدول الاحتياط
            بصفة <strong>{safe_role}</strong>.
          </p>

          <p>
            يمكنك إعداد كلمة المرور وتفعيل حسابك
            من خلال الزر التالي:
          </p>

          <div style="text-align:center;margin:30px 0;">
            <a href="{safe_link}" class="action-button"
               style="background:#087e68;color:#ffffff;
                      text-decoration:none;border-radius:9px;
                      padding:14px 26px;display:inline-block;
                      font-weight:bold;">
              إعداد كلمة المرور وتفعيل الحساب
            </a>
          </div>

          <div style="
            padding:15px;
            background:#fff8e8;
            border:1px solid #f0dfb0;
            border-radius:10px;
            color:#775a23;
          ">
            ⏳ رابط الدعوة صالح لمرة واحدة ولمدة 24 ساعة فقط.
          </div>

          <p class="muted" style="margin-top:18px;">
            إذا لم تكن تتوقع هذه الدعوة، يمكنك تجاهل الرسالة.
          </p>

          <hr style="border:0;border-top:1px solid #e5eeea;margin:25px 0;">

          <div dir="ltr" style="text-align:left;">
            <h3 style="color:#087e68;">Join Badil</h3>

            <p>
              You were invited to <strong>{safe_school}</strong>
              as a <strong>{safe_role}</strong>.
            </p>

            <p>
              Use the button above to set your password.
              The one-time invitation expires in 24 hours.
            </p>
          </div>
        </div>

        <div class="email-footer">
          إدارة النظام | System Administration
          <div style="margin-top:5px;">
            نظام إدارة جدول الاحتياط المدرسي
          </div>
        </div>

      </div>
    </td>
  </tr>
</table>
</body>
</html>"""

    message.add_alternative(
        html_content,
        subtype="html",
    )

    _send_email(message)


def send_discord_notification(content: str) -> None:
    """Send an optional Discord notification."""

    webhook = settings.discord_webhook_url

    if not webhook:
        raise RuntimeError(
            "Discord webhook is not configured"
        )

    body = json.dumps({
        "content": content,
        "allowed_mentions": {
            "parse": []
        },
    }).encode("utf-8")

    request = Request(
        webhook,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "SchoolSubstitutionSystem/1.0",
        },
        method="POST",
    )

    with urlopen(request, timeout=5) as response:
        if response.status >= 300:
            raise RuntimeError(
                f"Discord webhook rejected the notification "
                f"(HTTP {response.status})"
            )


def created_license_message(activation_key: str) -> str:
    """Format a newly generated license notification."""

    created_at = datetime.now(timezone.utc).date().isoformat()

    return (
        "🔑 New License Created\n"
        f"Key: ||`{activation_key}`||\n"
        f"Created At: {created_at}\n"
        "Status: Unused"
    )


def activated_license_message(username: str, email: str) -> str:
    """Format an activated license notification."""

    activated_at = datetime.now(timezone.utc).date().isoformat()

    return (
        "🔐 License Activated\n"
        f"Username: {username}\n"
        f"Email: {email}\n"
        "Status: Activated\n"
        f"Activated At: {activated_at}"
    )
