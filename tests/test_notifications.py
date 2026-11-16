import json

import pytest

from backend.app import notifications


def test_activation_email_uses_arabic_bilingual_multipart_template(monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["connection"] = (host, port, timeout)

        def starttls(self, context):
            sent["starttls"] = True

        def login(self, username, password):
            sent["login"] = (username, password)

        def send_message(self, message):
            sent["message"] = message

        def quit(self):
            sent["quit"] = True

        def close(self):
            sent["closed"] = True

    monkeypatch.setattr(notifications.settings, "email_host", "smtp.example.com")
    monkeypatch.setattr(notifications.settings, "email_port", 587)
    monkeypatch.setattr(notifications.settings, "email_username", "mail@example.com")
    monkeypatch.setattr(notifications.settings, "email_password", "test-secret")
    monkeypatch.setattr(notifications.settings, "email_from", "mail@example.com")
    monkeypatch.setattr(notifications.settings, "email_use_ssl", False)
    monkeypatch.setattr(notifications.settings, "email_use_starttls", True)
    monkeypatch.setattr(notifications.smtplib, "SMTP", FakeSMTP)

    notifications.send_activation_email("user@example.com", "ABCD-2345-EFGH-6789")

    message = sent["message"]
    assert "تفعيل حسابك" in str(message["Subject"])
    assert "Activate your account" in str(message["Subject"])
    assert message["To"] == "user@example.com"
    assert sent["starttls"] is True
    assert len(list(message.iter_parts())) == 2
    plain = message.get_body(preferencelist=("plain",)).get_content()
    html = message.get_body(preferencelist=("html",)).get_content()
    assert "مرحبًا" in plain and "Hello" in plain
    assert "مفتاح التفعيل" in html and "ACTIVATION KEY" in html
    assert "سجّل الدخول" in html and "sign in" in html
    assert "ABCD-2345-EFGH-6789" in plain
    assert "ABCD-2345-EFGH-6789" in html


def test_discord_webhook_sends_json_without_enabling_mentions(monkeypatch):
    captured = {}

    class FakeResponse:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data)
        captured["user_agent"] = request.get_header("User-agent")
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(notifications.settings, "discord_webhook_url", "https://discord.test/webhook/token")
    monkeypatch.setattr(notifications, "urlopen", fake_urlopen)

    notifications.send_discord_notification("License test notification")

    assert captured["url"] == "https://discord.test/webhook/token"
    assert captured["body"] == {
        "content": "License test notification",
        "allowed_mentions": {"parse": []},
    }
    assert captured["user_agent"] == "SchoolSubstitutionSystem/1.0"
    assert captured["timeout"] == 5


def test_discord_webhook_missing_configuration_is_an_explicit_error(monkeypatch):
    monkeypatch.setattr(notifications.settings, "discord_webhook_url", None)

    with pytest.raises(RuntimeError, match="not configured"):
        notifications.send_discord_notification("License test notification")
