import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import current_app
from extensions import db
from models import CompanySettings
from services.integration_service import integration_config


def email_credentials():
    settings = db.session.get(CompanySettings, 1)
    configured = integration_config("gmail")
    host = current_app.config.get("SMTP_HOST") or configured.get("smtp_host") or "smtp.gmail.com"
    user = current_app.config.get("SMTP_USER") or configured.get("from_email") or (settings.gmail_address if settings else "")
    password = current_app.config.get("SMTP_PASS") or configured.get("app_password") or (settings.gmail_app_password if settings else "")
    try:
        port = int(configured.get("smtp_port") or current_app.config.get("SMTP_PORT", 587))
    except (TypeError, ValueError):
        port = 587
    use_tls = configured.get("use_tls", True)
    if isinstance(use_tls, str):
        use_tls = use_tls.strip().lower() in {"1", "true", "yes", "on"}
    return host, user, str(password or "").replace(" ", ""), port, bool(use_tls)


def send_email(to, subject, html):
    host, user, password, port, use_tls = email_credentials()
    if not host or not user or not password:
        return {"ok": False, "skipped": True, "error": "Gmail address and app password are required in Settings > Integrations."}
    if not to:
        return {"ok": False, "skipped": True, "error": "Recipient email address is required."}
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP(host, port) as server:
            if use_tls:
                server.starttls()
            server.login(user, password)
            server.sendmail(user, [to], msg.as_string())
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
