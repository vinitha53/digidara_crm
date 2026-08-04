import requests
from flask import current_app
from extensions import db
from models import CompanySettings
from services.integration_service import integration_config


def whatsapp_credentials():
    settings = db.session.get(CompanySettings, 1)
    configured = integration_config("whatsapp")
    token = (
        current_app.config.get("WHATSAPP_TOKEN")
        or configured.get("api_key")
        or configured.get("access_token")
        or (settings.whatsapp_api_token if settings else "")
    )
    phone_number_id = (
        current_app.config.get("WHATSAPP_PHONE_NUMBER_ID")
        or configured.get("sender_number")
        or configured.get("phone_number_id")
        or (settings.whatsapp_phone_number_id if settings else "")
    )
    api_url = str(configured.get("api_url") or "https://graph.facebook.com/v19.0").rstrip("/")
    return token, phone_number_id, api_url


def send_whatsapp(to, body):
    token, phone_number_id, api_url = whatsapp_credentials()
    if not token or not phone_number_id:
        return {"ok": False, "skipped": True, "error": "WhatsApp Phone Number ID and API token are required in Settings > Integrations."}
    if not to:
        return {"ok": False, "skipped": True, "error": "Recipient phone number is required."}
    url = f"{api_url}/{phone_number_id}/messages"
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body}}
    try:
        res = requests.post(url, json=payload, headers={"Authorization": f"Bearer {token}"}, timeout=15)
        return {"ok": res.ok, "status_code": res.status_code, "data": res.json() if res.content else {}}
    except requests.RequestException as exc:
        return {"ok": False, "error": str(exc)}


def send_whatsapp_template(to, template_name, language_code, body_params=None, url_button_params=None):
    token, phone_number_id, api_url = whatsapp_credentials()
    if not token or not phone_number_id:
        return {"ok": False, "skipped": True, "error": "WhatsApp Phone Number ID and API token are required in Settings > Integrations."}
    if not to:
        return {"ok": False, "skipped": True, "error": "Recipient phone number is required."}
    if not template_name:
        return {"ok": False, "skipped": True, "error": "WhatsApp template name is required."}

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code or "en"},
        },
    }
    params = [str(value or "") for value in (body_params or [])]
    components = []
    if params:
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": value} for value in params],
        })
    for index, value in enumerate(url_button_params or []):
        components.append({
            "type": "button",
            "sub_type": "url",
            "index": str(index),
            "parameters": [{"type": "text", "text": str(value or "")}],
        })
    if components:
        payload["template"]["components"] = components

    url = f"{api_url}/{phone_number_id}/messages"
    try:
        res = requests.post(url, json=payload, headers={"Authorization": f"Bearer {token}"}, timeout=15)
        return {"ok": res.ok, "status_code": res.status_code, "data": res.json() if res.content else {}}
    except requests.RequestException as exc:
        return {"ok": False, "error": str(exc)}
