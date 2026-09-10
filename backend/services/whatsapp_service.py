import json
import re

import requests
from flask import current_app
from extensions import db
from models import CompanySettings
from services.integration_service import integration_config


def whatsapp_recipient(value):
    digits = re.sub(r"\D+", "", str(value or ""))
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 10:
        digits = f"91{digits}"
    return digits


def whatsapp_credentials():
    settings = db.session.get(CompanySettings, 1)
    configured = integration_config("whatsapp")
    token = (
        current_app.config.get("WHATSAPP_ACCESS_TOKEN")
        or current_app.config.get("WHATSAPP_TOKEN")
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
    version = current_app.config.get("WHATSAPP_GRAPH_API_VERSION") or "v23.0"
    api_url = str(configured.get("api_url") or f"https://graph.facebook.com/{version}").rstrip("/")
    return token, phone_number_id, api_url


def whatsapp_meta_config():
    configured = integration_config("whatsapp")
    token, phone_number_id, api_url = whatsapp_credentials()
    return {
        "token": token,
        "phone_number_id": phone_number_id,
        "waba_id": current_app.config.get("WHATSAPP_BUSINESS_ACCOUNT_ID") or configured.get("waba_id") or configured.get("business_account_id") or "",
        "api_url": api_url,
        "app_secret": current_app.config.get("WHATSAPP_APP_SECRET") or configured.get("app_secret") or "",
        "verify_token": current_app.config.get("WHATSAPP_WEBHOOK_VERIFY_TOKEN") or configured.get("verify_token") or "",
    }


def safe_response(response):
    try:
        data = response.json() if response.content else {}
    except ValueError:
        data = {}
    result = {"ok": response.ok, "status_code": response.status_code, "data": data}
    if not response.ok:
        error = data.get("error") if isinstance(data, dict) else {}
        result.update({
            "error": str((error or {}).get("message") or "Meta WhatsApp request failed")[:500],
            "error_code": str((error or {}).get("code") or response.status_code),
            "transient": response.status_code == 429 or response.status_code >= 500 or bool((error or {}).get("is_transient")),
        })
    return result


def validate_whatsapp_credentials(require_waba=False):
    config = whatsapp_meta_config()
    missing = []
    if not config["token"]:
        missing.append("access token")
    if not config["phone_number_id"]:
        missing.append("Phone Number ID")
    if require_waba and not config["waba_id"]:
        missing.append("WhatsApp Business Account ID")
    return {"ok": not missing, "missing": missing, "configured": not missing}


def derive_waba_id():
    config = whatsapp_meta_config()
    if config["waba_id"]:
        return {"ok": True, "waba_id": config["waba_id"]}
    if not config["token"] or not config["phone_number_id"]:
        return {"ok": False, "error": "WhatsApp access token and Phone Number ID are required."}
    try:
        response = requests.get(
            f"{config['api_url']}/{config['phone_number_id']}",
            params={"fields": "whatsapp_business_account"},
            headers={"Authorization": f"Bearer {config['token']}"},
            timeout=15,
        )
        result = safe_response(response)
        account = (result.get("data") or {}).get("whatsapp_business_account") or {}
        if result["ok"] and account.get("id"):
            result["waba_id"] = str(account["id"])
        elif result["ok"]:
            result.update({"ok": False, "error": "Meta did not return a WhatsApp Business Account ID."})
        return result
    except requests.RequestException as exc:
        return {"ok": False, "error": f"Meta connection failed: {exc}", "transient": True}


def fetch_approved_templates(after=None, limit=100):
    config = whatsapp_meta_config()
    waba = derive_waba_id()
    if not waba.get("ok"):
        return waba
    params = {
        "fields": "id,name,language,status,category,components",
        "limit": max(1, min(int(limit or 100), 100)),
    }
    if after:
        params["after"] = after
    try:
        response = requests.get(
            f"{config['api_url']}/{waba['waba_id']}/message_templates",
            params=params,
            headers={"Authorization": f"Bearer {config['token']}"},
            timeout=20,
        )
        result = safe_response(response)
        if result["ok"]:
            payload = result.get("data") or {}
            result["templates"] = [item for item in payload.get("data", []) if str(item.get("status", "")).upper() == "APPROVED"]
            result["paging"] = payload.get("paging") or {}
            result["waba_id"] = waba["waba_id"]
        return result
    except requests.RequestException as exc:
        return {"ok": False, "error": f"Meta template synchronization failed: {exc}", "transient": True}


def upload_whatsapp_media(file_stream, mime_type, filename):
    config = whatsapp_meta_config()
    if not config["token"] or not config["phone_number_id"]:
        return {"ok": False, "error": "WhatsApp credentials are not configured."}
    try:
        response = requests.post(
            f"{config['api_url']}/{config['phone_number_id']}/media",
            data={"messaging_product": "whatsapp", "type": mime_type},
            files={"file": (filename, file_stream, mime_type)},
            headers={"Authorization": f"Bearer {config['token']}"},
            timeout=30,
        )
        result = safe_response(response)
        result["media_id"] = str((result.get("data") or {}).get("id") or "")
        return result
    except requests.RequestException as exc:
        return {"ok": False, "error": f"Meta media upload failed: {exc}", "transient": True}


def send_whatsapp(to, body):
    token, phone_number_id, api_url = whatsapp_credentials()
    recipient = whatsapp_recipient(to)
    if not recipient:
        return {"ok": False, "skipped": True, "error": "Recipient phone number is required.", "recipient_phone": recipient, "transport": "text"}
    if not token or not phone_number_id:
        return {"ok": False, "skipped": True, "error": "WhatsApp Phone Number ID and API token are required in Settings > Integrations.", "recipient_phone": recipient, "transport": "text"}
    url = f"{api_url}/{phone_number_id}/messages"
    payload = {"messaging_product": "whatsapp", "to": recipient, "type": "text", "text": {"body": body}}
    try:
        res = requests.post(url, json=payload, headers={"Authorization": f"Bearer {token}"}, timeout=15)
        return {**safe_response(res), "recipient_phone": recipient, "transport": "text"}
    except requests.RequestException as exc:
        return {"ok": False, "error": str(exc), "recipient_phone": recipient, "transport": "text"}


def send_whatsapp_template(to, template_name, language_code, body_params=None, url_button_params=None, header_media_id=None):
    token, phone_number_id, api_url = whatsapp_credentials()
    recipient = whatsapp_recipient(to)
    if not recipient:
        return {"ok": False, "skipped": True, "error": "Recipient phone number is required.", "recipient_phone": recipient, "transport": "template", "template_name": template_name}
    if not token or not phone_number_id:
        return {"ok": False, "skipped": True, "error": "WhatsApp Phone Number ID and API token are required in Settings > Integrations.", "recipient_phone": recipient, "transport": "template", "template_name": template_name}
    if not template_name:
        return {"ok": False, "skipped": True, "error": "WhatsApp template name is required.", "recipient_phone": recipient, "transport": "template", "template_name": template_name}

    payload = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code or "en"},
        },
    }
    params = [str(value or "") for value in (body_params or [])]
    components = []
    if header_media_id:
        components.append({
            "type": "header",
            "parameters": [{"type": "image", "image": {"id": str(header_media_id)}}],
        })
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
        return {**safe_response(res), "recipient_phone": recipient, "transport": "template", "template_name": template_name}
    except requests.RequestException as exc:
        return {"ok": False, "error": str(exc), "recipient_phone": recipient, "transport": "template", "template_name": template_name}


def provider_message_id(result):
    messages = (result.get("data") or {}).get("messages") if isinstance(result, dict) else None
    return str((messages or [{}])[0].get("id") or "")


def safe_provider_response(result):
    sanitized = {
        key: value for key, value in (result or {}).items()
        if key not in {"token", "access_token", "headers"}
    }
    return json.dumps(sanitized, ensure_ascii=False, default=str)[:16000]
