import os
import re
from datetime import datetime, time

import pymysql
from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import and_, or_, text
from extensions import db
from models import ActivityLog, CommunicationSummary, Customer, Lead, MessageLog, User
from permissions import has_permission
from services.ai_service import summarize_communication
from services.email_service import send_email
from services.whatsapp_service import send_whatsapp, send_whatsapp_template
from .utils import current_user, permission_required

bp = Blueprint("communication", __name__, url_prefix="/api/communication")


def scoped_customers():
    user = current_user()
    query = Customer.query.filter(Customer.lead_id.isnot(None))
    return query if has_permission(user, "leads", "assign") else query.filter(Customer.assigned_to == user.id)


def scoped_leads():
    user = current_user()
    query = Lead.query
    return query if has_permission(user, "leads", "assign") else query.filter(Lead.assigned_to == user.id)


def scoped_person(recipient_type, recipient_id):
    if recipient_type == "customer":
        return scoped_customers().filter(Customer.id == recipient_id).first_or_404()
    if recipient_type == "lead":
        return scoped_leads().filter(Lead.id == recipient_id).first_or_404()
    if recipient_type == "employee":
        user = current_user()
        query = User.query.filter(User.id == recipient_id) if has_permission(user, "leads", "assign") else User.query.filter(User.id == user.id)
        return query.first_or_404()
    return None


def message_status(result):
    if result.get("ok"):
        return "sent"
    if result.get("skipped"):
        return "skipped"
    return "failed"


def personalize_message(body, person):
    replacements = {
        "{name}": person.name or "",
        "{phone}": person.phone or "",
        "{email}": getattr(person, "email", None) or "",
        "{service}": getattr(person, "service", None) or "",
    }
    message = body or ""
    for token, value in replacements.items():
        message = message.replace(token, value)
    return message


def normalize_phone(phone):
    digits = re.sub(r"\D+", "", phone or "")
    without_country = digits[2:] if digits.startswith("91") and len(digits) > 10 else digits
    with_country = digits if digits.startswith("91") else f"91{digits}" if digits else ""
    return digits, without_country, with_country


def parse_bot_conversation(conversation, chat_date):
    messages = []
    for line in (conversation or "").splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^\[(User|Bot)\s+([0-9]{1,2}:[0-9]{2})\]\s*(.*)$", line, re.IGNORECASE)
        if not match:
            continue
        role, msg_time, text_body = match.groups()
        messages.append({
            "role": "user" if role.lower() == "user" else "bot",
            "time": msg_time,
            "text": text_body,
            "chat_date": chat_date.isoformat() if hasattr(chat_date, "isoformat") else chat_date,
        })
    return messages


def bot_db_connection():
    return pymysql.connect(
        host=os.getenv("BOT_DB_HOST", os.getenv("DB_HOST", "localhost")),
        port=int(os.getenv("BOT_DB_PORT", os.getenv("DB_PORT", "3306"))),
        user=os.getenv("BOT_DB_USER", os.getenv("DB_USER", "root")),
        password=os.getenv("BOT_DB_PASSWORD", os.getenv("DB_PASSWORD", "")),
        database=os.getenv("BOT_DB_NAME", "digidara_bot"),
        cursorclass=pymysql.cursors.DictCursor,
    )


def empty_whatsapp_sessions(error=None):
    payload = {"items": [], "total": 0}
    if error:
        payload["error"] = error
    return payload


def bot_rows():
    conn = bot_db_connection()
    with conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT phone, name, chat_date, conversation, created_at, updated_at
                FROM messages
                ORDER BY updated_at DESC, chat_date DESC, created_at DESC
                """
            )
            return cursor.fetchall()


def lead_external_id(phone):
    digits, without_country, with_country = normalize_phone(phone)
    return f"bot-whatsapp:{with_country or without_country or digits}"


def row_datetime(row):
    for key in ("updated_at", "created_at"):
        value = row.get(key)
        if value:
            return value
    chat_date = row.get("chat_date")
    if isinstance(chat_date, datetime):
        return chat_date
    if hasattr(chat_date, "year"):
        return datetime.combine(chat_date, time.min)
    if chat_date:
        try:
            return datetime.fromisoformat(str(chat_date)[:10])
        except ValueError:
            return None
    return None


def latest_user_message(row):
    parsed = parse_bot_conversation(row.get("conversation"), row.get("chat_date"))
    for message in reversed(parsed):
        if message["role"] == "user" and message.get("text"):
            return message["text"]
    return ""


def upsert_whatsapp_lead(row, actor_id):
    phone = row.get("phone")
    digits, without_country, with_country = normalize_phone(phone)
    normalized_phone = with_country or without_country or digits
    if not normalized_phone:
        return None, "missing_phone"

    external_id = lead_external_id(phone)
    lead = Lead.query.filter_by(source_system="whatsapp_bot", external_id=external_id).first()
    if not lead:
        lead = Lead.query.filter_by(phone=normalized_phone, source="whatsapp").first()

    is_new = lead is None
    if is_new:
        lead = Lead(
            name=row.get("name") or "WhatsApp User",
            phone=normalized_phone,
            service="WhatsApp Enquiry",
            lead_category="course",
            source="whatsapp",
            tag="new",
            status="new",
            assigned_to=actor_id,
        )
        db.session.add(lead)

    if row.get("name") and (is_new or lead.name in {"WhatsApp User", normalized_phone, phone}):
        lead.name = row["name"]
    lead.phone = normalized_phone
    lead.source = "whatsapp"
    lead.source_system = "whatsapp_bot"
    lead.external_id = external_id
    lead.external_created_at = lead.external_created_at or row_datetime(row)
    if actor_id and not lead.assigned_to:
        lead.assigned_to = actor_id
    if not lead.notes:
        last_message = latest_user_message(row)
        lead.notes = f"Imported from WhatsApp bot. Last user message: {last_message}" if last_message else "Imported from WhatsApp bot."

    db.session.flush()
    db.session.add(ActivityLog(
        user_id=actor_id,
        action="whatsapp_bot_lead_synced",
        entity_type="lead",
        entity_id=lead.id,
        entity_name=lead.name,
        meta=external_id,
    ))
    return lead, "created" if is_new else "updated"


@bp.post("/quick-send")
@permission_required("communication", "send")
def quick_send():
    data = request.get_json() or {}
    rtype, rid = data.get("recipient_type"), data.get("recipient_id")
    person = scoped_person(rtype, rid)
    if not person:
        return jsonify({"message": "Recipient type must be customer, lead, or employee"}), 400
    channel = data.get("channel", "WhatsApp")
    body = personalize_message((data.get("message_body") or "").strip(), person)
    if not body:
        return jsonify({"message": "Message body is required"}), 400
    template_used = data.get("template_used")
    if channel == "Email":
        result = send_email(person.email, "Message from Digidara Technologies", body)
    elif rtype == "customer":
        template_used = current_app.config.get("WHATSAPP_COMMUNICATION_TEMPLATE_NAME")
        language = current_app.config.get("WHATSAPP_TEMPLATE_LANGUAGE", "en")
        service = getattr(person, "service", None) or "your existing service request"
        result = send_whatsapp_template(person.phone, template_used, language, [person.name, service, body])
    else:
        result = send_whatsapp(person.phone, body)
    log = MessageLog(recipient_type=rtype, recipient_id=rid, recipient_name=person.name, channel=channel, message_body=body, template_used=template_used, status=message_status(result))
    db.session.add(log)
    db.session.commit()
    return jsonify(log.to_dict()), 201


@bp.post("/bulk-whatsapp")
@permission_required("communication", "send")
def bulk_whatsapp():
    data = request.get_json() or {}
    customer_mode = "customer_ids" in data
    raw_ids = data.get("customer_ids", []) if customer_mode else data.get("lead_ids", [])
    ids = [int(value) for value in raw_ids if str(value).isdigit()]
    body = (data.get("message_body") or "").strip()
    template = data.get("template_used") or "Bulk WhatsApp"
    if not ids:
        return jsonify({"message": "Select at least one customer" if customer_mode else "Select at least one lead"}), 400
    if not body:
        return jsonify({"message": "Message body is required"}), 400

    unique_ids = list(dict.fromkeys(ids))[:200]
    people = (scoped_customers().filter(Customer.id.in_(unique_ids)).all() if customer_mode
              else scoped_leads().filter(Lead.id.in_(unique_ids)).all())
    person_map = {person.id: person for person in people}
    logs = []
    summary = {"total": len(unique_ids), "sent": 0, "skipped": 0, "failed": 0, "missing": 0}

    for recipient_id in unique_ids:
        person = person_map.get(recipient_id)
        if not person:
            summary["missing"] += 1
            continue
        message = personalize_message(body, person)
        result = send_whatsapp(person.phone, message)
        status = message_status(result)
        summary[status] = summary.get(status, 0) + 1
        log = MessageLog(
            recipient_type="customer" if customer_mode else "lead",
            recipient_id=person.id,
            recipient_name=person.name,
            channel="WhatsApp",
            message_body=message,
            template_used=template,
            status=status,
        )
        db.session.add(log)
        logs.append(log)

    db.session.commit()
    return jsonify({"summary": summary, "items": [log.to_dict() for log in logs]}), 201


@bp.post("/sync-whatsapp-leads")
@permission_required("leads", "create")
def sync_whatsapp_leads():
    try:
        rows = bot_rows()
    except Exception:
        return jsonify({"message": "Bot database unavailable"}), 503

    actor = current_user()
    created = 0
    updated = 0
    skipped = 0
    items = []
    seen = set()
    for row in rows:
        external_id = lead_external_id(row.get("phone"))
        if external_id in seen:
            continue
        seen.add(external_id)
        lead, status = upsert_whatsapp_lead(row, actor.id if actor else None)
        if status == "created":
            created += 1
        elif status == "updated":
            updated += 1
        else:
            skipped += 1
        if lead:
            items.append(lead.to_dict())

    db.session.commit()
    return jsonify({"created": created, "updated": updated, "skipped": skipped, "items": items})


@bp.get("/customer-recipients")
@permission_required("communication", "view")
def customer_recipients():
    query = scoped_customers()
    status = (request.args.get("status") or "").strip()
    search = (request.args.get("search") or "").strip()
    if status:
        query = query.filter(Customer.status == status)
    if search:
        like = f"%{search}%"
        query = query.filter(or_(Customer.name.ilike(like), Customer.phone.ilike(like), Customer.email.ilike(like)))
    total = query.count()
    rows = query.order_by(Customer.name.asc()).limit(200).all()
    return jsonify({"items": [row.to_dict() for row in rows], "total": total, "limited": total > 200})

@bp.get("/message-log")
@permission_required("communication", "view")
def logs():
    user = current_user()
    query = MessageLog.query
    recipient_type = (request.args.get("recipient_type") or "").strip()
    if recipient_type:
        query = query.filter(MessageLog.recipient_type == recipient_type)
    if not has_permission(user, "leads", "assign"):
        customer_ids = scoped_customers().with_entities(Customer.id)
        lead_ids = scoped_leads().with_entities(Lead.id)
        query = query.filter(or_(
            and_(MessageLog.recipient_type == "customer", MessageLog.recipient_id.in_(customer_ids)),
            and_(MessageLog.recipient_type == "lead", MessageLog.recipient_id.in_(lead_ids)),
            and_(MessageLog.recipient_type == "employee", MessageLog.recipient_id == user.id),
        ))
    rows = query.order_by(MessageLog.sent_at.desc()).limit(50).all()
    return jsonify([row.to_dict() for row in rows])


@bp.get("/summaries")
@permission_required("communication", "view")
def summaries():
    user = current_user()
    query = CommunicationSummary.query
    if not has_permission(user, "leads", "assign"):
        customer_ids = scoped_customers().with_entities(Customer.id)
        lead_ids = scoped_leads().with_entities(Lead.id)
        query = query.filter(or_(
            and_(CommunicationSummary.recipient_type == "customer", CommunicationSummary.recipient_id.in_(customer_ids)),
            and_(CommunicationSummary.recipient_type == "lead", CommunicationSummary.recipient_id.in_(lead_ids)),
            and_(CommunicationSummary.recipient_type == "employee", CommunicationSummary.recipient_id == user.id),
        ))
    rows = query.order_by(CommunicationSummary.created_at.desc()).limit(50).all()
    return jsonify([row.to_dict() for row in rows])


@bp.post("/summaries")
@permission_required("communication", "send")
def create_summary():
    data = request.get_json() or {}
    rtype = data.get("recipient_type") or "lead"
    rid = int(data.get("recipient_id") or 0)
    channel = data.get("channel") or "Mixed"
    person = scoped_person(rtype, rid)
    if not person:
        return jsonify({"message": "Recipient type must be customer, lead, or employee"}), 400
    q = MessageLog.query.filter_by(recipient_type=rtype, recipient_id=rid)
    if channel != "Mixed":
        q = q.filter_by(channel=channel)
    messages = q.order_by(MessageLog.sent_at.desc()).limit(30).all()
    result = summarize_communication(person, messages, channel)
    row = CommunicationSummary(
        recipient_type=rtype,
        recipient_id=rid,
        recipient_name=person.name,
        channel=channel,
        summary_text=result["summary_text"],
        key_points=result["key_points"],
        sentiment=result["sentiment"],
        next_action=result["next_action"],
        message_count=len(messages),
        model=result["model"],
        created_by=current_user().id,
    )
    db.session.add(row)
    db.session.commit()
    return jsonify(row.to_dict()), 201


@bp.get("/whatsapp-sessions")
@permission_required("communication", "view")
def whatsapp_sessions():
    try:
        rows = bot_rows()
    except Exception:
        return jsonify(empty_whatsapp_sessions("Bot database unavailable"))

    items = []
    for row in rows:
        parsed = parse_bot_conversation(row.get("conversation"), row.get("chat_date"))
        last_message = parsed[-1] if parsed else None
        chat_date = row.get("chat_date")
        created_at = row.get("created_at")
        updated_at = row.get("updated_at")
        items.append({
            "phone": row.get("phone"),
            "name": row.get("name"),
            "chat_date": chat_date.isoformat() if hasattr(chat_date, "isoformat") else chat_date,
            "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else created_at,
            "updated_at": updated_at.isoformat() if hasattr(updated_at, "isoformat") else updated_at,
            "conversation": row.get("conversation") or "",
            "messages": parsed,
            "message_count": len(parsed),
            "last_message": last_message,
        })
    return jsonify({"items": items, "total": len(items)})


@bp.get("/whatsapp-history/<path:phone>")
@permission_required("communication", "view")
def whatsapp_history(phone):
    normalized, without_country, with_country = normalize_phone(phone)
    response = {
        "phone": normalized,
        "name": None,
        "messages": [],
        "summaries": [],
        "total_days": 0,
    }
    if not normalized:
        return jsonify(response)

    try:
        conn = bot_db_connection()
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT phone, name, chat_date, conversation, created_at, updated_at
                    FROM messages
                    WHERE phone = %s OR phone = %s
                    ORDER BY chat_date ASC, created_at ASC
                    """,
                    (with_country, without_country),
                )
                message_rows = cursor.fetchall()

                cursor.execute(
                    """
                    SELECT summary_date, summary_text
                    FROM summaries
                    WHERE phone = %s OR phone = %s
                    ORDER BY summary_date ASC
                    """,
                    (with_country, without_country),
                )
                summary_rows = cursor.fetchall()
    except Exception:
        return jsonify({
            **response,
            "summaries": [],
            "error": "Bot database unavailable",
        })

    messages = []
    chat_days = set()
    for row in message_rows:
        response["name"] = response["name"] or row.get("name")
        chat_date = row.get("chat_date")
        if chat_date:
            chat_days.add(chat_date.isoformat() if hasattr(chat_date, "isoformat") else str(chat_date))
        messages.extend(parse_bot_conversation(row.get("conversation"), chat_date))

    summaries = [
        {
            "summary_date": row.get("summary_date").isoformat() if hasattr(row.get("summary_date"), "isoformat") else row.get("summary_date"),
            "summary_text": row.get("summary_text"),
        }
        for row in summary_rows
    ]

    response.update({
        "name": response["name"],
        "messages": messages,
        "summaries": summaries,
        "total_days": len(chat_days),
    })
    return jsonify(response)
