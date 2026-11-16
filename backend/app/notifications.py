"""Server-side email delivery and optional Discord license notifications."""
from datetime import datetime, timezone
from email.message import EmailMessage
from html import escape
import json
import smtplib
import ssl
from urllib.request import Request, urlopen

from .core import settings


class EmailDeliveryNotConfigured(RuntimeError):
    pass


def send_activation_email(recipient: str, activation_key: str) -> None:
    host = settings.email_host
    sender = settings.email_from
    if not host or not sender:
        raise EmailDeliveryNotConfigured("SMTP email delivery is not configured")

    message = EmailMessage()
    message["Subject"] = "تفعيل حسابك | Activate your account - نظام إدارة جدول الاحتياط"
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
        "مع تحيات، Best regards,\nإدارة النظام | System Administration"
    )
    safe_key = escape(activation_key)
    message.add_alternative(
        """<!doctype html>
<html lang="ar" dir="rtl">
  <body style="margin:0;padding:0;background:#edf3f1;font-family:Arial,Tahoma,sans-serif;color:#183b35">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#edf3f1;padding:28px 12px">
      <tr><td align="center">
        <table role="presentation" width="600" cellspacing="0" cellpadding="0" style="width:100%;max-width:600px;background:#fff;border:1px solid #dce8e3;border-radius:18px;overflow:hidden">
          <tr><td style="background:#087e68;padding:26px 30px;color:#fff;text-align:right">
            <div style="font-size:13px;letter-spacing:.3px;color:#d8f4eb">نظام إدارة جدول الاحتياط المدرسي</div>
            <div dir="ltr" style="margin-top:5px;text-align:left;font-size:12px;color:#d8f4eb">School Substitution Management System</div>
            <div style="margin-top:18px;font-size:24px;font-weight:bold">تفعيل حسابك</div>
            <div dir="ltr" style="margin-top:4px;text-align:left;font-size:18px;font-weight:bold">Activate your account</div>
          </td></tr>
          <tr><td style="padding:28px 30px;line-height:1.85">
            <div dir="rtl" style="text-align:right">
              <p style="margin:0 0 12px">مرحبًا،</p>
              <p style="margin:0 0 14px">تم إنشاء حسابك بنجاح. لإكمال التفعيل، سجّل الدخول إلى النظام وأدخل مفتاح التفعيل التالي:</p>
            </div>
            <div style="margin:20px 0;padding:18px 12px;text-align:center;background:#eff8f5;border:1px solid #cce8dd;border-radius:14px">
              <div style="font-size:12px;font-weight:bold;color:#55756b">مفتاح التفعيل | ACTIVATION KEY</div>
              <div dir="ltr" style="margin-top:10px;padding:15px 8px;background:#fff;border:1px dashed #087e68;border-radius:10px;font-family:Consolas,'Courier New',monospace;font-size:22px;font-weight:bold;letter-spacing:2px;color:#075d4d;overflow-wrap:anywhere">"""
        + safe_key
        + """</div>
            </div>
            <div dir="rtl" style="text-align:right">
              <p style="margin:0 0 8px">يُستخدم المفتاح مرة واحدة فقط؛ احتفظ به ولا تشاركه مع أي شخص.</p>
              <p style="margin:0;color:#647871;font-size:13px">إذا لم تطلب إنشاء هذا الحساب، يمكنك تجاهل هذه الرسالة.</p>
            </div>
            <hr style="height:1px;border:0;background:#e5eeea;margin:24px 0">
            <div dir="ltr" style="text-align:left">
              <p style="margin:0 0 12px">Hello,</p>
              <p style="margin:0 0 8px">Your account has been created successfully. To activate it, sign in to the system and enter the key shown above.</p>
              <p style="margin:0 0 8px">The key can only be used once. Keep it private and do not share it.</p>
              <p style="margin:0;color:#647871;font-size:13px">If you did not request this account, you can ignore this email.</p>
            </div>
            <div style="margin-top:24px;padding-top:16px;border-top:1px solid #e5eeea;color:#526a62;font-size:13px;text-align:center">
              إدارة النظام | System Administration<br>نظام إدارة جدول الاحتياط المدرسي
            </div>
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>""",
        subtype="html",
    )

    context = ssl.create_default_context()
    if settings.email_use_ssl:
        client = smtplib.SMTP_SSL(host, settings.email_port, timeout=15, context=context)
    else:
        client = smtplib.SMTP(host, settings.email_port, timeout=15)
    try:
        if settings.email_use_starttls and not settings.email_use_ssl:
            client.starttls(context=context)
        if settings.email_username:
            client.login(settings.email_username, settings.email_password or "")
        client.send_message(message)
    finally:
        try:
            client.quit()
        except (OSError, smtplib.SMTPException):
            client.close()


def send_staff_invitation_email(recipient: str, school_name: str, teacher_name: str, role: str, invitation_link: str) -> None:
    """Send a one-time link for a school employee to activate their own account."""
    host = settings.email_host
    sender = settings.email_from
    if not host or not sender:
        raise EmailDeliveryNotConfigured("SMTP email delivery is not configured")
    role_label = {"COORDINATOR": "منسق", "TEACHER": "معلم"}.get(role, role)
    safe_school, safe_teacher = escape(school_name), escape(teacher_name)
    safe_role, safe_link = escape(role_label), escape(invitation_link, quote=True)
    message = EmailMessage()
    message["Subject"] = "دعوة حساب مدرسي | School account invitation"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(
        f"مرحبًا {teacher_name}، دُعيت لاستخدام نظام بديل بصفة {role_label} في {school_name}.\n"
        f"أكمل إعداد حسابك من الرابط التالي (صالح لمرة واحدة ولمدة 24 ساعة):\n{invitation_link}\n\n"
        "Hello, you were invited to the School Substitution System. Use the link above within 24 hours to set your password."
    )
    message.add_alternative(f"""<!doctype html>
<html lang="ar" dir="rtl"><body style="margin:0;background:#edf3f1;font-family:Arial,Tahoma,sans-serif;color:#183b35;padding:28px 12px">
<table role="presentation" width="600" align="center" style="max-width:600px;width:100%;background:white;border:1px solid #dce8e3;border-radius:16px;border-collapse:separate;padding:28px">
<tr><td><h2 style="margin-top:0;color:#087e68">دعوة للانضمام إلى بديل</h2>
<p>مرحبًا {safe_teacher}، دعاك مدير <strong>{safe_school}</strong> للانضمام بصفة <strong>{safe_role}</strong>.</p>
<p style="text-align:center;margin:28px 0"><a href="{safe_link}" style="display:inline-block;padding:14px 24px;background:#087e68;color:#fff;text-decoration:none;border-radius:9px;font-weight:bold">إعداد كلمة المرور وتفعيل الحساب</a></p>
<p>الرابط صالح لمرة واحدة لمدة 24 ساعة. إذا لم تتوقع هذه الدعوة، تجاهل الرسالة.</p>
<hr style="border:0;border-top:1px solid #e5eeea;margin:24px 0">
<div dir="ltr"><h3>Join Badil</h3><p>You were invited to {safe_school} as a {safe_role}. The one-time link expires in 24 hours.</p></div>
</td></tr></table></body></html>""", subtype="html")
    context = ssl.create_default_context()
    client = smtplib.SMTP_SSL(host, settings.email_port, timeout=15, context=context) if settings.email_use_ssl else smtplib.SMTP(host, settings.email_port, timeout=15)
    try:
        if settings.email_use_starttls and not settings.email_use_ssl:
            client.starttls(context=context)
        if settings.email_username:
            client.login(settings.email_username, settings.email_password or "")
        client.send_message(message)
    finally:
        try:
            client.quit()
        except (OSError, smtplib.SMTPException):
            client.close()


def send_discord_notification(content: str) -> None:
    webhook = settings.discord_webhook_url
    if not webhook:
        raise RuntimeError("Discord webhook is not configured")
    body = json.dumps({"content": content, "allowed_mentions": {"parse": []}}).encode("utf-8")
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
            raise RuntimeError(f"Discord webhook rejected the notification (HTTP {response.status})")


def created_license_message(activation_key: str) -> str:
    created_at = datetime.now(timezone.utc).date().isoformat()
    return f"🔑 New License Created\nKey: ||`{activation_key}`||\nCreated At: {created_at}\nStatus: Unused"


def activated_license_message(username: str, email: str) -> str:
    activated_at = datetime.now(timezone.utc).date().isoformat()
    return (
        "🔐 License Activated\n"
        f"Username: {username}\nEmail: {email}\nStatus: Activated\nActivated At: {activated_at}"
    )
