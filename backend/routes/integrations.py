import hashlib
import hmac
import time
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import ActivityLog, Lead
from services.lead_acknowledgement_service import send_lead_acknowledgement

bp = Blueprint("integrations", __name__, url_prefix="/api/integrations")

SOURCES = {"website", "chatbot", "whatsapp", "email", "inperson"}
CATEGORIES = {"course", "internship", "business"}
STATUSES = {"new", "contacted", "qualified", "won", "lost", "converted", "closed", "not_interested"}
TAGS = {"new", "hot", "warm", "cold"}
MAX_CLOCK_SKEW_SECONDS = 300


def parse_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def expected_signature(timestamp, body):
    secret = current_app.config.get("CRM_INTEGRATION_SIGNING_SECRET") or ""
    signed = f"{timestamp}.".encode("utf-8") + body
    return hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()


def verify_request():
    api_key = current_app.config.get("CRM_INTEGRATION_API_KEY") or ""
    signing_secret = current_app.config.get("CRM_INTEGRATION_SIGNING_SECRET") or ""
    if not api_key or not signing_secret:
        return "CRM integration secrets are not configured"
    if not hmac.compare_digest(request.headers.get("X-CRM-API-Key", ""), api_key):
        return "Invalid integration API key"
    timestamp = request.headers.get("X-CRM-Timestamp", "")
    try:
        sent_at = int(timestamp)
    except ValueError:
        return "Invalid integration timestamp"
    if abs(int(time.time()) - sent_at) > MAX_CLOCK_SKEW_SECONDS:
        return "Integration timestamp expired"
    signature = request.headers.get("X-CRM-Signature", "")
    if not hmac.compare_digest(signature, expected_signature(timestamp, request.get_data() or b"")):
        return "Invalid integration signature"
    return None


def clean(value):
    return str(value).strip() if value is not None else ""


def normalize_payload(data):
    source_system = clean(data.get("source_system") or data.get("source") or "whatsapp").lower()
    allowed_sources = current_app.config.get("INTEGRATION_ALLOWED_SOURCES") or ["whatsapp", "chatbot", "website"]
    if source_system not in allowed_sources:
        raise ValueError("Source system is not allowed")
    source = source_system if source_system in SOURCES else "chatbot"
    category = clean(data.get("lead_category") or data.get("category") or "course").lower()
    if category not in CATEGORIES:
        category = "business" if clean(data.get("business_requirement") or data.get("business_name")) else "course"
    status = clean(data.get("status") or "new").lower()
    tag = clean(data.get("tag") or "new").lower()
    lead = {
        "name": clean(data.get("name") or data.get("full_name") or "WhatsApp User"),
        "phone": clean(data.get("phone") or data.get("mobile") or data.get("whatsapp_number")),
        "email": clean(data.get("email")) or None,
        "company": clean(data.get("company") or data.get("business_name")) or None,
        "service": clean(data.get("service") or data.get("course_name") or data.get("internship_name") or data.get("business_requirement") or "WhatsApp Enquiry"),
        "lead_category": category,
        "qualification": clean(data.get("qualification")) or None,
        "program_duration": clean(data.get("program_duration")) or None,
        "course_name": clean(data.get("course_name")) or None,
        "internship_name": clean(data.get("internship_name")) or None,
        "business_name": clean(data.get("business_name") or data.get("company")) or None,
        "business_requirement": clean(data.get("business_requirement")) or None,
        "source": source,
        "tag": tag if tag in TAGS else "new",
        "status": status if status in STATUSES else "new",
        "notes": clean(data.get("notes") or data.get("message") or data.get("last_message")) or None,
        "city": clean(data.get("city")) or None,
        "source_system": source_system,
        "external_id": clean(data.get("external_id") or data.get("id") or data.get("message_id")) or None,
        "external_created_at": parse_datetime(data.get("external_created_at") or data.get("created_at")),
    }
    if not lead["phone"]:
        raise ValueError("Phone is required")
    return lead


def apply_lead_fields(lead, fields):
    for key, value in fields.items():
        setattr(lead, key, value)
    if lead.lead_category == "course":
        lead.service = lead.course_name or lead.service or "Course Enquiry"
        lead.program_duration = None
        lead.company = None
        lead.business_name = None
        lead.business_requirement = None
    elif lead.lead_category == "internship":
        lead.service = lead.internship_name or lead.service or "Internship Enquiry"
        lead.company = None
        lead.business_name = None
        lead.business_requirement = None
    elif lead.lead_category == "business":
        lead.service = lead.business_requirement or lead.service or "Business Enquiry"
        lead.qualification = None
        lead.program_duration = None
        lead.course_name = None
        lead.internship_name = None
        lead.company = lead.business_name or lead.company
    return lead


@bp.post("/leads")
def receive_lead():
    error = verify_request()
    if error:
        return jsonify({"message": error}), 401

    data = request.get_json(silent=True) or {}
    rows = data if isinstance(data, list) else [data]
    if not rows:
        return jsonify({"message": "At least one lead is required"}), 400

    created = 0
    updated = 0
    skipped = []
    items = []

    for index, row in enumerate(rows):
        try:
            fields = normalize_payload(row)
        except ValueError as exc:
            skipped.append({"index": index, "reason": str(exc)})
            continue

        lead = None
        if fields.get("external_id"):
            lead = Lead.query.filter_by(source_system=fields["source_system"], external_id=fields["external_id"]).first()
        if not lead:
            lead = Lead.query.filter_by(phone=fields["phone"], source=fields["source"]).first()

        is_new = lead is None
        if is_new:
            lead = Lead()
            db.session.add(lead)
        apply_lead_fields(lead, fields)
        db.session.flush()
        if is_new:
            send_lead_acknowledgement(lead, send_email_copy=False)
        db.session.add(ActivityLog(
            user_id=None,
            action="integration_lead_received",
            entity_type="lead",
            entity_id=lead.id,
            entity_name=lead.name,
            meta=f"{fields['source_system']}:{fields.get('external_id') or fields['phone']}",
        ))
        created += 1 if is_new else 0
        updated += 0 if is_new else 1
        items.append(lead.to_dict())

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "Duplicate external lead id received"}), 409

    return jsonify({"created": created, "updated": updated, "skipped": skipped, "items": items}), 201 if created else 200
