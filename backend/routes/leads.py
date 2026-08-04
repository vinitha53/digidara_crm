import csv
import io
from datetime import datetime
from flask import Blueprint, Response, jsonify, request
from sqlalchemy import func
from extensions import db
from models import ActivityLog, Customer, Lead, MessageLog, Task
from permissions import has_permission
from services.ai_service import classify_lead
from services.email_service import send_email
from services.lead_acknowledgement_service import send_customer_conversion_welcome, send_lead_acknowledgement
from services.whatsapp_service import send_whatsapp
from services.workflow_service import run_lead_workflows
from .utils import current_user, log_activity, permission_required, parse_date, update_model

bp = Blueprint("leads", __name__, url_prefix="/api/leads")
ALLOWED = [
    "name", "phone", "email", "company", "service", "lead_category", "qualification",
    "program_duration", "course_name", "internship_name", "business_name",
    "business_requirement", "source", "tag", "status", "deal_value", "probability",
    "expected_close_date", "lost_reason", "assigned_to", "notes", "city"
]
SOURCES = {"website", "chatbot", "whatsapp", "email", "inperson"}


def scoped():
    user = current_user()
    q = Lead.query
    return q if has_permission(user, "leads", "assign") else q.filter(Lead.assigned_to == user.id)


def normalize_lead(lead):
    category = lead.lead_category or "course"
    lead.source = lead.source if lead.source in SOURCES else "website"
    try:
        lead.deal_value = max(0, int(lead.deal_value or 0))
    except (TypeError, ValueError):
        lead.deal_value = 0
    try:
        lead.probability = max(0, min(100, int(lead.probability or 0)))
    except (TypeError, ValueError):
        lead.probability = 10
    if lead.status == "won":
        lead.probability = 100
        lead.lost_reason = None
    elif lead.status == "lost" and not lead.lost_reason:
        lead.lost_reason = "Not specified"
    elif lead.status != "lost":
        lead.lost_reason = None
    if category == "course":
        lead.service = lead.course_name or lead.service or "Course Enquiry"
        lead.program_duration = None
        lead.company = None
        lead.business_name = None
        lead.business_requirement = None
    elif category == "internship":
        lead.service = lead.internship_name or lead.service or "Internship Enquiry"
        lead.company = None
        lead.business_name = None
        lead.business_requirement = None
    elif category == "business":
        lead.service = lead.business_requirement or lead.service or "Business Enquiry"
        lead.qualification = None
        lead.program_duration = None
        lead.course_name = None
        lead.internship_name = None
        lead.company = lead.business_name or lead.company
    return lead


def message_status(result):
    if result.get("ok"):
        return "sent"
    if result.get("skipped"):
        return "skipped"
    return "failed"


def customer_message(lead):
    if lead.lead_category == "course":
        subject = f"Welcome as a customer - {lead.course_name or lead.service}"
        body = f"Hi {lead.name}, welcome to Digidara Technologies. Your course enquiry for {lead.course_name or lead.service} is confirmed, and our team will share the next steps shortly."
    elif lead.lead_category == "internship":
        subject = f"Internship onboarding - {lead.internship_name or lead.service}"
        duration = f"{lead.program_duration} " if lead.program_duration else ""
        body = f"Hi {lead.name}, welcome to Digidara Technologies. Your {duration}{lead.internship_name or lead.service} internship is confirmed, and our team will guide you through onboarding."
    else:
        subject = "Business customer onboarding - Digidara Technologies"
        body = f"Hi {lead.name}, welcome to Digidara Technologies. We are happy to start working with you on {lead.business_requirement or lead.service}. Our business team will contact you with the next steps."
    return subject, " ".join(body.split())


def send_customer_welcome(customer, lead):
    send_customer_conversion_welcome(customer, lead)


def convert_won_lead_to_customer(lead):
    if lead.status != "won":
        return None
    customer = Customer.query.filter_by(lead_id=lead.id).first()
    is_new = customer is None
    if not customer:
        customer = Customer(lead_id=lead.id)
        db.session.add(customer)
    customer.name = lead.name
    customer.phone = lead.phone
    customer.email = lead.email
    customer.company = lead.company or lead.business_name
    customer.service = lead.service
    customer.value = lead.deal_value or customer.value or 0
    customer.status = "active"
    customer.assigned_to = lead.assigned_to
    customer.notes = lead.notes
    db.session.flush()
    if is_new:
        send_customer_welcome(customer, lead)
        log_activity(current_user().id, "lead_converted_to_customer", "customer", customer.id, customer.name)
    return customer


def score_lead(lead):
    messages = MessageLog.query.filter_by(recipient_type="lead", recipient_id=lead.id).all() if lead.id else []
    open_tasks = Task.query.filter(
        (Task.related_type == "lead") &
        ((Task.related_id == lead.id) | (Task.related_name == lead.name)) &
        (Task.status != "done")
    ).count() if lead.id else 0
    result = classify_lead(
        lead,
        message_count=len(messages),
        successful_messages=len([m for m in messages if m.status == "sent"]),
        open_tasks=open_tasks,
    )
    lead.tag = result["tag"]
    lead.ai_score = result["score"]
    lead.ai_reason = result["reason"]
    lead.ai_score_factors = result.get("factors")
    lead.ai_next_best_action = result.get("next_best_action")
    lead.ai_scored_at = datetime.utcnow()
    return result


@bp.get("/")
@permission_required("leads", "view")
def list_leads():
    q = scoped()
    segment = request.args.get("segment")
    if segment == "academic":
        q = q.filter(Lead.lead_category.in_(["course", "internship"]))
    elif segment == "project":
        q = q.filter(Lead.lead_category.in_(["business", "project"]))
    if request.args.get("stage") == "open":
        q = q.filter(Lead.status.in_(["new", "contacted", "qualified"]))
    for key in ("status", "tag", "assigned_to", "source", "lead_category"):
        if request.args.get(key):
            q = q.filter(getattr(Lead, key) == request.args[key])
    if request.args.get("city"):
        q = q.filter(Lead.city.ilike(f"%{request.args['city']}%"))
    if request.args.get("service"):
        q = q.filter(Lead.service.ilike(f"%{request.args['service']}%"))
    if request.args.get("lost_reason"):
        reason = func.coalesce(func.nullif(func.trim(Lead.lost_reason), ""), "Not specified")
        q = q.filter(reason == request.args["lost_reason"])
    if request.args.get("min_value"):
        q = q.filter(Lead.deal_value >= int(request.args["min_value"]))
    if request.args.get("max_value"):
        q = q.filter(Lead.deal_value <= int(request.args["max_value"]))
    if request.args.get("expected_from"):
        q = q.filter(Lead.expected_close_date >= parse_date(request.args["expected_from"]))
    if request.args.get("expected_to"):
        q = q.filter(Lead.expected_close_date <= parse_date(request.args["expected_to"]))
    search = request.args.get("search")
    if search:
        like = f"%{search}%"
        q = q.filter((Lead.name.ilike(like)) | (Lead.email.ilike(like)) | (Lead.phone.ilike(like)))
    page = max(int(request.args.get("page", 1)), 1)
    per_page = min(max(int(request.args.get("per_page", 20)), 1), 200)
    latest_activity = func.coalesce(Lead.updated_at, Lead.created_at)
    items = q.order_by(latest_activity.desc(), Lead.id.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )
    return jsonify({"items": [x.to_dict() for x in items.items], "total": items.total, "page": page})


@bp.get("/overview")
@permission_required("leads", "view")
def leads_overview():
    q = scoped()
    category_counts = dict(q.with_entities(Lead.lead_category, func.count(Lead.id)).group_by(Lead.lead_category).all())
    status_counts = dict(q.with_entities(Lead.status, func.count(Lead.id)).group_by(Lead.status).all())
    course = int(category_counts.get("course", 0) or 0)
    internship = int(category_counts.get("internship", 0) or 0)
    project = int(category_counts.get("business", 0) or 0) + int(category_counts.get("project", 0) or 0)
    return jsonify({
        "total": q.count(),
        "course": course,
        "internship": internship,
        "academic": course + internship,
        "project": project,
        "statuses": {key: int(value or 0) for key, value in status_counts.items()},
    })


@bp.get("/export")
@permission_required("leads", "view")
def export_leads():
    latest_activity = func.coalesce(Lead.updated_at, Lead.created_at)
    rows = scoped().order_by(latest_activity.desc(), Lead.id.desc()).all()
    output = io.StringIO()
    fields = ["id", "name", "phone", "email", "company", "service", "lead_category", "source", "tag", "status", "assigned_to", "city", "created_at"]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for lead in rows:
        data = lead.to_dict()
        writer.writerow({field: data.get(field) for field in fields})
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=leads.csv"})


@bp.post("/import")
@permission_required("leads", "create")
def import_leads():
    data = request.get_json() or {}
    text = data.get("csv") or ""
    if not text.strip():
        return jsonify({"message": "CSV content is required"}), 400
    reader = csv.DictReader(io.StringIO(text))
    created, skipped = 0, []
    for index, row in enumerate(reader, start=2):
        phone = (row.get("phone") or "").strip()
        email = (row.get("email") or "").strip()
        if not row.get("name") or not phone:
            skipped.append({"row": index, "reason": "name and phone are required"})
            continue
        duplicate = Lead.query.filter((Lead.phone == phone) | ((Lead.email == email) if email else (Lead.id == 0))).first()
        if duplicate:
            skipped.append({"row": index, "reason": "duplicate phone or email"})
            continue
        lead = Lead(
            name=row["name"].strip(),
            phone=phone,
            email=email or None,
            company=row.get("company") or None,
            service=row.get("service") or row.get("course_name") or "Imported Lead",
            lead_category=row.get("lead_category") or "course",
            source=row.get("source") or "website",
            tag=row.get("tag") or "new",
            status=row.get("status") or "new",
            city=row.get("city") or None,
            assigned_to=current_user().id,
            notes=row.get("notes") or None,
        )
        normalize_lead(lead)
        db.session.add(lead)
        created += 1
    log_activity(current_user().id, "leads_imported", "lead", None, f"{created} leads imported")
    db.session.commit()
    return jsonify({"created": created, "skipped": skipped})


@bp.get("/duplicates")
@permission_required("leads", "view")
def duplicates():
    rows = scoped().all()
    groups = {}
    for lead in rows:
        for key in [f"phone:{lead.phone}", f"email:{lead.email}" if lead.email else None]:
            if key:
                groups.setdefault(key.lower(), []).append(lead)
    result = []
    for key, leads in groups.items():
        if len(leads) > 1:
            result.append({"match": key, "leads": [lead.to_dict() for lead in leads]})
    return jsonify(result)


@bp.post("/bulk")
@permission_required("leads", "update")
def bulk_update():
    data = request.get_json() or {}
    ids = data.get("ids") or []
    action = data.get("action")
    if not ids or action not in {"status", "tag", "assign", "delete"}:
        return jsonify({"message": "Valid ids and action are required"}), 400
    q = scoped().filter(Lead.id.in_(ids))
    rows = q.all()
    for lead in rows:
        if action == "status":
            lead.status = data.get("value") or lead.status
            normalize_lead(lead)
            convert_won_lead_to_customer(lead)
        elif action == "tag":
            lead.tag = data.get("value") or lead.tag
        elif action == "assign" and has_permission(current_user(), "leads", "assign"):
            lead.assigned_to = int(data.get("value"))
        elif action == "delete" and has_permission(current_user(), "leads", "delete"):
            db.session.delete(lead)
    log_activity(current_user().id, "leads_bulk_updated", "lead", None, f"{len(rows)} leads affected")
    db.session.commit()
    return jsonify({"updated": len(rows)})


@bp.post("/")
@permission_required("leads", "create")
def create_lead():
    data = request.get_json() or {}
    lead = normalize_lead(update_model(Lead(), data, ALLOWED))
    if "expected_close_date" in data:
        lead.expected_close_date = parse_date(data["expected_close_date"]) if data.get("expected_close_date") else None
    if not lead.assigned_to:
        lead.assigned_to = current_user().id
    db.session.add(lead)
    db.session.flush()
    send_lead_acknowledgement(lead)
    convert_won_lead_to_customer(lead)
    log_activity(current_user().id, "lead_created", "lead", lead.id, lead.name)
    db.session.commit()
    return jsonify(lead.to_dict()), 201


@bp.get("/<int:id>")
@permission_required("leads", "view")
def detail(id):
    return jsonify(scoped().filter_by(id=id).first_or_404().to_dict())


@bp.get("/<int:id>/timeline")
@permission_required("leads", "view")
def timeline(id):
    lead = scoped().filter_by(id=id).first_or_404()
    messages = MessageLog.query.filter_by(recipient_type="lead", recipient_id=lead.id).order_by(MessageLog.sent_at.desc()).limit(20).all()
    activity = ActivityLog.query.filter_by(entity_type="lead", entity_id=lead.id).order_by(ActivityLog.created_at.desc()).limit(20).all()
    items = [{
        "kind": "lead",
        "title": "Lead created",
        "body": lead.service,
        "timestamp": lead.created_at.isoformat() if lead.created_at else None,
    }]
    items += [{"kind": "message", "title": f"{m.channel} {m.status}", "body": m.message_body, "timestamp": m.sent_at.isoformat() if m.sent_at else None} for m in messages]
    items += [{"kind": "activity", "title": a.action.replace("_", " ").title(), "body": a.entity_name, "timestamp": a.created_at.isoformat() if a.created_at else None} for a in activity]
    return jsonify(sorted(items, key=lambda item: item["timestamp"] or "", reverse=True))


@bp.put("/<int:id>")
@permission_required("leads", "update")
def update(id):
    lead = scoped().filter_by(id=id).first_or_404()
    data = request.get_json() or {}
    if data.get("status") == "won" and lead.status != "won" and not has_permission(current_user(), "leads", "convert"):
        return jsonify({"message": "Lead conversion permission required"}), 403
    old_status = lead.status
    normalize_lead(update_model(lead, data, ALLOWED))
    if "expected_close_date" in data:
        lead.expected_close_date = parse_date(data["expected_close_date"]) if data.get("expected_close_date") else None
    if old_status != "won" and lead.status == "won":
        convert_won_lead_to_customer(lead)
    elif lead.status == "won":
        convert_won_lead_to_customer(lead)
    run_lead_workflows(lead, old_status, lead.status, current_user())
    log_activity(current_user().id, "lead_updated", "lead", lead.id, lead.name)
    db.session.commit()
    return jsonify(lead.to_dict())


@bp.delete("/<int:id>")
@permission_required("leads", "delete")
def delete(id):
    lead = scoped().filter_by(id=id).first_or_404()
    db.session.delete(lead)
    log_activity(current_user().id, "lead_deleted", "lead", id, lead.name)
    db.session.commit()
    return jsonify({"message": "Lead deleted"})


@bp.post("/<int:id>/classify")
@permission_required("leads", "classify")
def classify(id):
    lead = scoped().filter_by(id=id).first_or_404()
    score_lead(lead)
    log_activity(current_user().id, "lead_classified", "lead", lead.id, lead.name)
    db.session.commit()
    return jsonify(lead.to_dict())


@bp.post("/score-all")
@permission_required("leads", "classify")
def score_all():
    rows = scoped().filter(Lead.status.in_(["new", "contacted", "qualified"])).all()
    for lead in rows:
        score_lead(lead)
    log_activity(current_user().id, "leads_ai_scored", "lead", None, f"{len(rows)} leads scored")
    db.session.commit()
    return jsonify({"updated": len(rows)})


@bp.get("/pipeline")
@permission_required("leads", "view")
def pipeline():
    statuses = ["new", "contacted", "qualified", "won", "lost"]
    return jsonify({s: [x.to_dict() for x in scoped().filter_by(status=s).all()] for s in statuses})
