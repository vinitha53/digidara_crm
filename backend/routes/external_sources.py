import os
from datetime import datetime

import pymysql
from flask import Blueprint, jsonify

from extensions import db
from models import ActivityLog, Lead
from services.lead_scoring_service import lead_scoring_signature, rescore_if_changed
from .utils import current_user, permission_required

bp = Blueprint("external_sources", __name__, url_prefix="/api/external-sources")

WEBSITE_TABLES = {
    "chat_users": {
        "source": "chatbot",
        "source_system": "website_chat_users",
        "default_service": "Chatbot Enquiry",
    },
    "contact_inquiries": {
        "source": "website",
        "source_system": "website_contact_inquiries",
        "default_service": "Website Enquiry",
    },
}


def website_db_connection():
    database = os.getenv("WEBSITE_DB_NAME", "")
    if not database:
        raise RuntimeError("WEBSITE_DB_NAME is required")
    return pymysql.connect(
        host=os.getenv("WEBSITE_DB_HOST", os.getenv("DB_HOST", "localhost")),
        port=int(os.getenv("WEBSITE_DB_PORT", os.getenv("DB_PORT", "3306"))),
        user=os.getenv("WEBSITE_DB_USER", os.getenv("DB_USER", "root")),
        password=os.getenv("WEBSITE_DB_PASSWORD", os.getenv("DB_PASSWORD", "")),
        database=database,
        cursorclass=pymysql.cursors.DictCursor,
    )


def first_value(row, names):
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return ""


def parse_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def table_columns(cursor, table_name):
    cursor.execute(f"SHOW COLUMNS FROM `{table_name}`")
    return [row["Field"] for row in cursor.fetchall()]


def order_column(columns):
    for name in ("updated_at", "created_at", "submitted_at", "created_on", "id"):
        if name in columns:
            return name
    return columns[0] if columns else None


def fetch_table_rows(cursor, table_name, limit=500):
    columns = table_columns(cursor, table_name)
    if not columns:
        return []
    order_by = order_column(columns)
    cursor.execute(f"SELECT * FROM `{table_name}` ORDER BY `{order_by}` DESC LIMIT %s", (limit,))
    return cursor.fetchall()


def external_id_for(table_name, row):
    row_id = first_value(row, ("id", "user_id", "inquiry_id", "enquiry_id", "chat_user_id", "contact_id"))
    if row_id:
        return f"website:{table_name}:{row_id}"
    phone = first_value(row, ("phone", "mobile", "phone_number", "mobile_number", "whatsapp", "whatsapp_number", "contact_number"))
    email = first_value(row, ("email", "email_address", "mail"))
    created = first_value(row, ("created_at", "submitted_at", "created_on", "date", "timestamp"))
    return f"website:{table_name}:{phone or email}:{created}"


def map_website_lead(table_name, row):
    meta = WEBSITE_TABLES[table_name]
    name = first_value(row, ("name", "full_name", "user_name", "username", "customer_name", "visitor_name")) or "Website Visitor"
    phone = first_value(row, ("phone", "mobile", "phone_number", "mobile_number", "whatsapp", "whatsapp_number", "contact_number"))
    email = first_value(row, ("email", "email_address", "mail"))
    if not phone and email:
        phone = f"email:{email}"
    service = first_value(row, ("service", "course", "course_name", "interest", "subject", "program", "requirement")) or meta["default_service"]
    message = first_value(row, ("message", "inquiry", "enquiry", "query", "question", "description", "comment", "comments", "last_message"))
    company = first_value(row, ("company", "company_name", "business_name", "organization"))
    city = first_value(row, ("city", "location", "place"))
    created_at = first_value(row, ("created_at", "submitted_at", "created_on", "date", "timestamp"))
    category = "business" if company or table_name == "contact_inquiries" and "business" in service.lower() else "course"
    return {
        "name": name,
        "phone": phone,
        "email": email or None,
        "company": company or None,
        "service": service,
        "lead_category": category,
        "course_name": service if category == "course" else None,
        "business_name": company or None,
        "business_requirement": service if category == "business" else None,
        "source": meta["source"],
        "source_system": meta["source_system"],
        "external_id": external_id_for(table_name, row),
        "external_created_at": parse_datetime(created_at),
        "notes": message or f"Imported from website table {table_name}.",
        "city": city or None,
    }


def apply_lead_fields(lead, fields, actor_id):
    for key, value in fields.items():
        setattr(lead, key, value)
    if actor_id and not lead.assigned_to:
        lead.assigned_to = actor_id
    return lead


def upsert_website_lead(table_name, row, actor_id):
    fields = map_website_lead(table_name, row)
    if not fields["phone"]:
        return None, "missing_phone_or_email"
    lead = Lead.query.filter_by(source_system=fields["source_system"], external_id=fields["external_id"]).first()
    if not lead:
        lead = Lead.query.filter_by(phone=fields["phone"], source=fields["source"]).first()
    is_new = lead is None
    if is_new:
        lead = Lead()
        db.session.add(lead)
    previous_scoring_signature = lead_scoring_signature(lead) if not is_new else None
    apply_lead_fields(lead, fields, actor_id)
    db.session.flush()
    rescore_if_changed(lead, previous_scoring_signature, force=is_new)
    db.session.add(ActivityLog(
        user_id=actor_id,
        action="website_lead_synced",
        entity_type="lead",
        entity_id=lead.id,
        entity_name=lead.name,
        meta=fields["external_id"],
    ))
    return lead, "created" if is_new else "updated"


@bp.post("/sync-website-leads")
@permission_required("leads", "create")
def sync_website_leads():
    actor = current_user()
    summary = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "tables": {},
        "items": [],
    }
    try:
        conn = website_db_connection()
        with conn:
            with conn.cursor() as cursor:
                for table_name in WEBSITE_TABLES:
                    table_summary = {"created": 0, "updated": 0, "skipped": 0}
                    try:
                        rows = fetch_table_rows(cursor, table_name)
                    except Exception as exc:
                        summary["tables"][table_name] = {**table_summary, "error": str(exc)}
                        continue
                    seen = set()
                    for row in rows:
                        external_id = external_id_for(table_name, row)
                        if external_id in seen:
                            continue
                        seen.add(external_id)
                        lead, status = upsert_website_lead(table_name, row, actor.id if actor else None)
                        if status == "created":
                            summary["created"] += 1
                            table_summary["created"] += 1
                        elif status == "updated":
                            summary["updated"] += 1
                            table_summary["updated"] += 1
                        else:
                            summary["skipped"] += 1
                            table_summary["skipped"] += 1
                        if lead:
                            summary["items"].append(lead.to_dict())
                    summary["tables"][table_name] = table_summary
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"message": "Website database unavailable", "error": str(exc)}), 503
    return jsonify(summary)
