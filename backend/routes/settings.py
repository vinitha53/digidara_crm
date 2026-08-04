import re

from flask import Blueprint, jsonify, request
from extensions import db
from models import CompanySettings, RolePermission, User
from permissions import PERMISSION_PAGES, default_allowed, role_definitions
from services.email_service import email_credentials
from services.integration_service import integration_config, save_integration_config
from services.whatsapp_service import whatsapp_credentials
from .utils import admin_required, current_user, login_required, log_activity, permission_required

bp = Blueprint("settings", __name__, url_prefix="/api/settings")

COMPANY_FIELDS = [
    "company_name", "tagline", "website", "email", "phone", "city", "gst_number",
]
OPTION_FIELDS = ["course_name_options", "internship_name_options", "business_service_options"]
AI_FIELDS = [
    "ai_followups_enabled", "ai_followup_hot_interval_days", "ai_followup_warm_interval_days",
    "ai_followup_cold_interval_days", "ai_followup_business_hours", "ai_followup_working_days",
    "ai_followup_max_count", "ai_followup_stop_after_no_response",
    "ai_followup_preferred_channel", "ai_followup_llm_model",
]
PUBLIC_FIELDS = COMPANY_FIELDS + OPTION_FIELDS + AI_FIELDS
INTEGRATION_FIELDS = {
    "whatsapp": ["whatsapp_phone_number_id", "whatsapp_api_token"],
    "gmail": ["gmail_address", "gmail_app_password"],
    "google_reviews": ["google_review_url", "google_review_place_id", "google_review_api_key"],
}
SECRET_FIELDS = {"whatsapp_api_token", "gmail_app_password", "google_review_api_key"}
DAY_KEYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def row():
    settings = CompanySettings.query.get(1)
    if not settings:
        settings = CompanySettings(id=1)
        db.session.add(settings)
        db.session.commit()
    return settings


def public_company(settings):
    payload = {field: getattr(settings, field) for field in PUBLIC_FIELDS}
    payload["updated_at"] = settings.updated_at.isoformat() if settings.updated_at else None
    return payload


def integration_payload(settings):
    whatsapp_token, whatsapp_phone_number_id, _ = whatsapp_credentials()
    _, gmail_address, gmail_password, _, _ = email_credentials()
    return {
        "whatsapp": {
            "configured": bool(whatsapp_token and whatsapp_phone_number_id),
            "phone_number_id": whatsapp_phone_number_id or "",
            "secret_configured": bool(whatsapp_token),
        },
        "gmail": {
            "configured": bool(gmail_address and gmail_password),
            "address": gmail_address or "",
            "secret_configured": bool(gmail_password),
        },
        "google_reviews": {
            "configured": bool(settings.google_review_url and settings.google_review_place_id and settings.google_review_api_key),
            "url": settings.google_review_url or "",
            "place_id": settings.google_review_place_id or "",
            "secret_configured": bool(settings.google_review_api_key),
        },
        "updated_at": settings.updated_at.isoformat() if settings.updated_at else None,
    }


def clean_options(value, label):
    values = []
    seen = set()
    for raw in str(value or "").splitlines():
        item = raw.strip()
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        if len(item) > 190:
            raise ValueError(f"{label} entries must be 190 characters or fewer")
        seen.add(key)
        values.append(item)
    if not values:
        raise ValueError(f"Add at least one {label.lower()} option")
    if len(values) > 100:
        raise ValueError(f"{label} supports up to 100 options")
    return "\n".join(values)


def validate_company_update(data):
    clean = {}
    for field in COMPANY_FIELDS:
        if field in data:
            clean[field] = str(data[field] or "").strip()
    if "company_name" in clean and not clean["company_name"]:
        raise ValueError("Company name is required")
    if clean.get("email") and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", clean["email"]):
        raise ValueError("Enter a valid company email")
    option_labels = {
        "course_name_options": "Course",
        "internship_name_options": "Internship",
        "business_service_options": "Project service",
    }
    for field, label in option_labels.items():
        if field in data:
            clean[field] = clean_options(data[field], label)

    integer_ranges = {
        "ai_followup_hot_interval_days": (1, 90),
        "ai_followup_warm_interval_days": (1, 90),
        "ai_followup_cold_interval_days": (1, 90),
        "ai_followup_max_count": (0, 50),
        "ai_followup_stop_after_no_response": (0, 50),
    }
    for field, (minimum, maximum) in integer_ranges.items():
        if field in data:
            try:
                value = int(data[field])
            except (TypeError, ValueError):
                raise ValueError("Follow-up values must be whole numbers")
            if value < minimum or value > maximum:
                raise ValueError(f"Follow-up value must be between {minimum} and {maximum}")
            clean[field] = value
    if "ai_followups_enabled" in data:
        clean["ai_followups_enabled"] = bool(data["ai_followups_enabled"])
    if "ai_followup_business_hours" in data:
        hours = str(data["ai_followup_business_hours"] or "").strip()
        match = re.match(r"^(\d{2}):(\d{2})-(\d{2}):(\d{2})$", hours)
        if not match or any(int(value) > limit for value, limit in zip(match.groups(), [23, 59, 23, 59])):
            raise ValueError("Business hours must use HH:MM-HH:MM")
        if hours[:5] >= hours[6:]:
            raise ValueError("Business end time must be after start time")
        clean["ai_followup_business_hours"] = hours
    if "ai_followup_working_days" in data:
        requested = [item.strip().title()[:3] for item in str(data["ai_followup_working_days"] or "").split(",")]
        days = [day for day in DAY_KEYS if day in requested]
        if not days:
            raise ValueError("Select at least one working day")
        clean["ai_followup_working_days"] = ",".join(days)
    if "ai_followup_preferred_channel" in data:
        channel = str(data["ai_followup_preferred_channel"] or "").title()
        if channel not in {"Whatsapp", "Email"}:
            raise ValueError("Preferred channel must be WhatsApp or Email")
        clean["ai_followup_preferred_channel"] = "WhatsApp" if channel == "Whatsapp" else channel
    if "ai_followup_llm_model" in data:
        model = str(data["ai_followup_llm_model"] or "").strip()
        if not model or len(model) > 120:
            raise ValueError("Enter a valid AI model name")
        clean["ai_followup_llm_model"] = model
    return clean


@bp.get("/company")
@permission_required("settings", "view")
def company():
    return jsonify(public_company(row()))


@bp.put("/company")
@permission_required("settings", "update")
def update_company():
    try:
        clean = validate_company_update(request.get_json() or {})
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    settings = row()
    for key, value in clean.items():
        setattr(settings, key, value)
    user = current_user()
    log_activity(user.id, "updated CRM settings", "settings", 1, settings.company_name)
    db.session.commit()
    return jsonify(public_company(settings))


@bp.get("/integrations")
@permission_required("settings", "view")
def integrations():
    return jsonify(integration_payload(row()))


@bp.put("/integrations")
@permission_required("settings", "update")
def update_integrations():
    data = request.get_json() or {}
    provider = data.get("provider")
    if provider not in INTEGRATION_FIELDS:
        return jsonify({"message": "Choose a valid integration"}), 400
    settings = row()
    for field in INTEGRATION_FIELDS[provider]:
        if field not in data:
            continue
        value = str(data[field] or "").strip()
        if field in SECRET_FIELDS and not value:
            continue
        setattr(settings, field, value)
    if provider == "gmail" and settings.gmail_address and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", settings.gmail_address):
        return jsonify({"message": "Enter a valid Gmail sender address"}), 400
    if provider == "whatsapp":
        current = integration_config("whatsapp")
        save_integration_config("whatsapp", {
            "api_url": current.get("api_url") or "https://graph.facebook.com/v19.0",
            "sender_number": settings.whatsapp_phone_number_id,
            "api_key": str(data.get("whatsapp_api_token") or "").strip() or current.get("api_key"),
            "app_secret": current.get("app_secret", ""),
            "verify_token": current.get("verify_token", ""),
            "template_namespace": current.get("template_namespace", ""),
        })
    elif provider == "gmail":
        current = integration_config("gmail")
        save_integration_config("gmail", {
            "use_tls": current.get("use_tls", True),
            "smtp_host": current.get("smtp_host") or "smtp.gmail.com",
            "smtp_port": current.get("smtp_port") or 587,
            "from_email": settings.gmail_address,
            "app_password": str(data.get("gmail_app_password") or "").strip() or current.get("app_password"),
        })
    user = current_user()
    log_activity(user.id, f"updated {provider.replace('_', ' ')} integration", "settings", 1, provider)
    db.session.commit()
    return jsonify(integration_payload(settings))


@bp.get("/lead-options")
@login_required
def lead_options():
    settings = row()
    return jsonify({field: getattr(settings, field) for field in OPTION_FIELDS})


def permission_response():
    rows = RolePermission.query.all()
    saved = {(item.role, item.page_key, item.action): bool(item.allowed) for item in rows}
    last_updates = {}
    for item in rows:
        if item.updated_at and (item.role not in last_updates or item.updated_at > last_updates[item.role]):
            last_updates[item.role] = item.updated_at
    user_counts = dict(db.session.query(User.role, db.func.count(User.id)).group_by(User.role).all())
    user_counts["staff"] = user_counts.get("staff", 0) + user_counts.get("employee", 0)
    permissions = {}
    roles = role_definitions(include_inactive=True)
    for role in roles:
        role_key = role["key"]
        permissions[role_key] = {}
        allowed_actions = 0
        allowed_pages = 0
        for page in PERMISSION_PAGES:
            page_key = page["key"]
            permissions[role_key][page_key] = {}
            for action in page["actions"]:
                allowed = True if role_key == "admin" else saved.get(
                    (role_key, page_key, action), default_allowed(role_key, page_key, action)
                )
                permissions[role_key][page_key][action] = allowed
                allowed_actions += int(allowed)
            allowed_pages += int(permissions[role_key][page_key].get("view", False))
        role["user_count"] = user_counts.get(role_key, 0)
        role["allowed_pages"] = allowed_pages
        role["allowed_actions"] = allowed_actions
        role["permissions_updated_at"] = last_updates.get(role_key).isoformat() if last_updates.get(role_key) else None
    return {"roles": roles, "pages": PERMISSION_PAGES, "permissions": permissions}


@bp.get("/permissions")
@admin_required
def get_permissions():
    return jsonify(permission_response())


def save_role_permissions(role_key, pages):
    role_keys = {role["key"] for role in role_definitions(include_inactive=True)}
    if role_key not in role_keys:
        raise ValueError("Role not found")
    user = current_user()
    for page in PERMISSION_PAGES:
        page_key = page["key"]
        incoming = pages.get(page_key) if isinstance(pages, dict) else {}
        incoming = incoming if isinstance(incoming, dict) else {}
        view_allowed = role_key == "admin" or bool(incoming.get("view", False))
        for action in page["actions"]:
            allowed = role_key == "admin" or (view_allowed and bool(incoming.get(action, False)))
            item = RolePermission.query.filter_by(role=role_key, page_key=page_key, action=action).first()
            if not item:
                item = RolePermission(role=role_key, page_key=page_key, action=action)
                db.session.add(item)
            item.allowed = int(allowed)
            item.updated_by = user.id


@bp.put("/permissions/<role_key>")
@admin_required
def save_role_permission_set(role_key):
    data = request.get_json() or {}
    try:
        save_role_permissions(role_key, data.get("permissions") or {})
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 404
    user = current_user()
    log_activity(user.id, "updated role permissions", "role", None, role_key)
    db.session.commit()
    return jsonify(permission_response())


@bp.put("/permissions")
@admin_required
def save_permissions():
    data = request.get_json() or {}
    for role_key, pages in (data.get("permissions") or {}).items():
        try:
            save_role_permissions(role_key, pages)
        except ValueError:
            continue
    db.session.commit()
    return jsonify(permission_response())
