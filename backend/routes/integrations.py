import hashlib
import hmac
import json
import re
import time
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import ActivityLog, Lead, User
from services.lead_acknowledgement_service import send_lead_acknowledgement
from services.lead_scoring_service import lead_scoring_signature, rescore_if_changed

bp = Blueprint("integrations", __name__, url_prefix="/api/integrations")

SOURCES = {"website", "chatbot", "whatsapp", "email", "inperson"}
SOURCE_SYSTEM_DEFAULTS = {"google_form": "website"}
CATEGORIES = {"course", "internship", "business"}
STATUSES = {"new", "contacted", "qualified", "won", "lost", "converted", "closed", "not_interested"}
MAX_CLOCK_SKEW_SECONDS = 300
IST_OFFSET = timedelta(hours=5, minutes=30)

GOOGLE_FORM_CONTAINERS = {"answers", "formdata", "namedvalues", "responses"}
FIELD_ALIASES = {
    "name": {"name", "fullname", "studentname", "candidatename", "yourname"},
    "phone": {"phone", "phonenumber", "mobile", "mobilenumber", "contactnumber", "whatsappnumber"},
    "email": {"email", "emailaddress"},
    "company": {"company", "companyname", "organization", "organisation"},
    "service": {"service", "serviceinterested", "interestedservice", "program", "programme"},
    "lead_category": {"leadcategory", "category", "enquirytype", "inquirytype", "leadtype"},
    "qualification": {"qualification", "educationalqualification", "education"},
    "program_duration": {"programduration", "programmeduration", "duration", "internshipduration"},
    "course_name": {"coursename", "course", "interestedcourse", "courseinterested"},
    "internship_name": {"internshipname", "internship", "interestedinternship", "internshipinterested"},
    "business_name": {"businessname", "clientname"},
    "business_requirement": {"businessrequirement", "projectrequirement", "requirement"},
    "notes": {"notes", "note", "message", "comments", "comment", "additionalinformation", "query"},
    "city": {"city", "location", "place"},
    "status": {"status", "leadstatus"},
    "external_id": {"externalid", "responseid", "formresponseid", "id"},
    "external_created_at": {"externalcreatedat", "createdat", "timestamp", "submittedat", "submissiontime"},
}
ALIAS_TO_FIELD = {
    alias: field
    for field, aliases in FIELD_ALIASES.items()
    for alias in aliases
}


def parse_datetime(value, assume_ist=False):
    if not value:
        return None
    text = clean(value)
    parsed = None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        for date_format in (
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%m/%d/%Y %H:%M:%S",
            "%m/%d/%Y %H:%M",
        ):
            try:
                parsed = datetime.strptime(text, date_format)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed - IST_OFFSET if assume_ist else parsed


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


def normalized_key(value):
    return re.sub(r"[^a-z0-9]", "", clean(value).lower())


def scalar_value(value):
    if isinstance(value, (list, tuple)):
        return next((clean(item) for item in value if clean(item)), "")
    if isinstance(value, dict):
        for key in ("answer", "value", "text"):
            if clean(value.get(key)):
                return clean(value[key])
        return ""
    return clean(value)


def canonical_field(label):
    key = normalized_key(label)
    field = ALIAS_TO_FIELD.get(key)
    if field:
        return field
    if "email" in key:
        return "email"
    if any(token in key for token in ("phone", "mobile", "whatsapp", "contactnumber")):
        return "phone"
    if "qualification" in key or key.startswith("education"):
        return "qualification"
    if "duration" in key:
        return "program_duration"
    if "timestamp" in key or "submittedat" in key or "submissiontime" in key:
        return "external_created_at"
    if "internship" in key:
        return "internship_name"
    if "course" in key:
        return "course_name"
    if "business" in key and any(token in key for token in ("requirement", "service", "project")):
        return "business_requirement"
    if "company" in key or "businessname" in key:
        return "business_name"
    if key.endswith("name") and not any(token in key for token in ("course", "internship", "business", "company")):
        return "name"
    return None


def google_form_payload(data):
    """Promote Google Forms question headings/namedValues into CRM fields."""
    canonical = {}
    note_parts = []

    def add(label, raw_value, keep_unknown=False):
        value = scalar_value(raw_value)
        if not value:
            return
        field = canonical_field(label)
        if field == "notes":
            note_parts.append(value)
        elif field and field not in canonical:
            canonical[field] = value
        elif keep_unknown:
            note_parts.append(f"{clean(label)}: {value}")

    # Explicit top-level values win over question-heading aliases.
    for field in FIELD_ALIASES:
        if field in data and field != "notes":
            add(field, data[field])

    for label, value in data.items():
        key = normalized_key(label)
        if key in GOOGLE_FORM_CONTAINERS:
            if isinstance(value, dict):
                for question, answer in value.items():
                    add(question, answer, keep_unknown=True)
            elif isinstance(value, list):
                for response in value:
                    if not isinstance(response, dict):
                        continue
                    question = response.get("question") or response.get("title") or response.get("name")
                    answer = response.get("answer") or response.get("value") or response.get("text")
                    if question:
                        add(question, answer, keep_unknown=True)
        elif label not in FIELD_ALIASES and canonical_field(label):
            add(label, value)

    raw_notes = data.get("notes") or data.get("message") or data.get("last_message")
    if isinstance(raw_notes, dict):
        for question, answer in raw_notes.items():
            add(question, answer, keep_unknown=True)
    elif clean(raw_notes):
        text = clean(raw_notes)
        parsed_json = None
        if text.startswith("{"):
            try:
                parsed_json = json.loads(text)
            except (TypeError, ValueError):
                parsed_json = None
        if isinstance(parsed_json, dict):
            for question, answer in parsed_json.items():
                add(question, answer, keep_unknown=True)
        else:
            labeled_lines = 0
            plain_lines = []
            for line in text.splitlines():
                match = re.match(r"^\s*([^:=]{2,100})\s*[:=]\s*(.+?)\s*$", line)
                if match:
                    labeled_lines += 1
                    add(match.group(1), match.group(2), keep_unknown=True)
                elif clean(line):
                    plain_lines.append(clean(line))
            if labeled_lines:
                note_parts.extend(plain_lines)
            else:
                note_parts.append(text)

    canonical["notes"] = "\n".join(dict.fromkeys(note_parts)) or None
    return canonical


def normalize_payload(data):
    source_system = clean(data.get("source_system") or data.get("source") or "whatsapp").lower()
    allowed_sources = current_app.config.get("INTEGRATION_ALLOWED_SOURCES") or ["whatsapp", "chatbot", "website"]
    if source_system not in allowed_sources:
        raise ValueError("Source system is not allowed")
    if source_system == "google_form":
        data = {**data, **google_form_payload(data)}
    requested_source = clean(data.get("source")).lower()
    source = requested_source if requested_source in SOURCES else SOURCE_SYSTEM_DEFAULTS.get(
        source_system, source_system if source_system in SOURCES else "chatbot"
    )
    inferred_category = "business" if clean(data.get("business_requirement") or data.get("business_name")) else (
        "internship" if clean(data.get("internship_name")) else "course"
    )
    category = clean(data.get("lead_category") or data.get("category") or inferred_category).lower()
    if category not in CATEGORIES:
        category = "business" if clean(data.get("business_requirement") or data.get("business_name")) else "course"
    status = clean(data.get("status") or "new").lower()
    lead = {
        "name": clean(data.get("name") or data.get("full_name") or ("Google Form Lead" if source_system == "google_form" else "WhatsApp User")),
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
        "status": status if status in STATUSES else "new",
        "notes": clean(data.get("notes") or data.get("message") or data.get("last_message")) or None,
        "city": clean(data.get("city")) or None,
        "source_system": source_system,
        "external_id": clean(data.get("external_id") or data.get("id") or data.get("message_id")) or None,
        "external_created_at": parse_datetime(
            data.get("external_created_at") or data.get("created_at"),
            assume_ist=source_system == "google_form",
        ),
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

        if fields["source_system"] == "google_form":
            admin = User.query.filter(User.role == "admin", User.is_active == 1).order_by(User.id.asc()).first()
            if not admin:
                skipped.append({"index": index, "reason": "No active admin user is available for Google Form assignment"})
                continue
            fields["assigned_to"] = admin.id

        lead = None
        if fields.get("external_id"):
            lead = Lead.query.filter_by(source_system=fields["source_system"], external_id=fields["external_id"]).first()
        if not lead:
            lead = Lead.query.filter_by(phone=fields["phone"], source=fields["source"]).first()

        is_new = lead is None
        if is_new:
            lead = Lead()
            db.session.add(lead)
        previous_scoring_signature = lead_scoring_signature(lead) if not is_new else None
        apply_lead_fields(lead, fields)
        if is_new and fields["source_system"] == "google_form" and fields.get("external_created_at"):
            lead.created_at = fields["external_created_at"]
        db.session.flush()
        rescore_if_changed(lead, previous_scoring_signature, force=is_new)
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
