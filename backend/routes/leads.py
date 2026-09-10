from datetime import datetime, time, timedelta
from flask import Blueprint, jsonify, request
from sqlalchemy import func
from extensions import db
from models import ActivityLog, Customer, Lead, MessageLog, Task, User
from permissions import has_permission
from services.ai_followup_service import STOP_STATUSES, cancel_followups
from services.email_service import send_email
from services.lead_acknowledgement_service import send_customer_conversion_welcome, send_lead_acknowledgement
from services.lead_assignment_service import send_lead_assignment_notification
from services.lead_scoring_service import lead_scoring_signature, rescore_if_changed, score_and_apply_lead
from services.lost_reason_service import canonical_lost_reason, validate_lost_reason
from services.whatsapp_service import send_whatsapp
from services.workflow_service import run_lead_workflows
from .utils import current_user, log_activity, permission_required, parse_date, update_model

bp = Blueprint("leads", __name__, url_prefix="/api/leads")
ALLOWED = [
    "name", "phone", "email", "company", "service", "lead_category", "qualification",
    "program_duration", "course_name", "internship_name", "business_name",
    "business_requirement", "source", "tag", "status", "deal_value", "probability",
    "expected_close_date", "lost_reason", "lost_reason_detail", "assigned_to", "notes", "city"
]
SOURCES = {"website", "chatbot", "whatsapp", "email", "inperson"}
IST_OFFSET = timedelta(hours=5, minutes=30)


def scoped():
    user = current_user()
    q = Lead.query
    return q if user.role == "admin" else q.filter(Lead.assigned_to == user.id)


def newest_first(query):
    """Keep lead collections in stable, newest-created-first order."""
    return query.order_by(Lead.created_at.desc(), Lead.id.desc())


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
        lead.lost_reason_detail = None
    elif lead.status == "lost":
        lead.lost_reason, lead.lost_reason_detail = validate_lost_reason(
            lead.status, lead.lost_reason, lead.lost_reason_detail,
        )
    elif lead.status != "lost":
        lead.lost_reason = None
        lead.lost_reason_detail = None
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


def assignable_staff(assigned_to):
    try:
        user_id = int(assigned_to)
    except (TypeError, ValueError):
        return None
    return User.query.filter(
        User.id == user_id,
        User.is_active == 1,
        User.role != "admin",
    ).first()


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
    cancel_followups(lead, "Lead converted to customer", current_user().id)
    if is_new:
        send_customer_welcome(customer, lead)
        log_activity(current_user().id, "lead_converted_to_customer", "customer", customer.id, customer.name)
    return customer


def score_lead(lead):
    return score_and_apply_lead(lead)


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
        raw_reason = request.args["lost_reason"].strip()
        if raw_reason.lower() == "not specified":
            q = q.filter((Lead.lost_reason.is_(None)) | (func.trim(Lead.lost_reason) == ""))
        else:
            requested_reason = canonical_lost_reason(raw_reason)
            q = q.filter(Lead.lost_reason == requested_reason)
    if request.args.get("min_value"):
        q = q.filter(Lead.deal_value >= int(request.args["min_value"]))
    if request.args.get("max_value"):
        q = q.filter(Lead.deal_value <= int(request.args["max_value"]))
    if request.args.get("expected_from"):
        q = q.filter(Lead.expected_close_date >= parse_date(request.args["expected_from"]))
    if request.args.get("expected_to"):
        q = q.filter(Lead.expected_close_date <= parse_date(request.args["expected_to"]))
    if request.args.get("created_from"):
        start_date = parse_date(request.args["created_from"])
        q = q.filter(Lead.created_at >= datetime.combine(start_date, time.min) - IST_OFFSET)
    if request.args.get("created_to"):
        end_date = parse_date(request.args["created_to"]) + timedelta(days=1)
        q = q.filter(Lead.created_at < datetime.combine(end_date, time.min) - IST_OFFSET)
    search = request.args.get("search")
    if search:
        like = f"%{search}%"
        q = q.filter((Lead.name.ilike(like)) | (Lead.email.ilike(like)) | (Lead.phone.ilike(like)))
    page = max(int(request.args.get("page", 1)), 1)
    per_page = min(max(int(request.args.get("per_page", 20)), 1), 200)
    items = newest_first(q).paginate(
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


@bp.get("/assignees")
@permission_required("leads", "assign")
def assignees():
    rows = User.query.filter(
        User.is_active == 1,
        User.role != "admin",
    ).order_by(User.name.asc()).all()
    return jsonify([{
        "id": user.id,
        "name": user.name,
        "role": user.role,
        "department": user.department,
    } for user in rows])


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
    assignee = None
    lost_reason = None
    lost_reason_detail = None
    if action == "assign":
        if not has_permission(current_user(), "leads", "assign"):
            return jsonify({"message": "Lead assignment permission required"}), 403
        assignee = assignable_staff(data.get("value"))
        if not assignee:
            return jsonify({"message": "Select an active staff member"}), 400
    if action == "status" and data.get("value") == "lost":
        try:
            lost_reason, lost_reason_detail = validate_lost_reason(
                "lost", data.get("lost_reason"), data.get("lost_reason_detail"),
            )
        except ValueError as exc:
            return jsonify({"message": str(exc)}), 400
    q = scoped().filter(Lead.id.in_(ids))
    rows = q.all()
    for lead in rows:
        if action == "status":
            lead.status = data.get("value") or lead.status
            if lead.status == "lost":
                lead.lost_reason = lost_reason
                lead.lost_reason_detail = lost_reason_detail
            normalize_lead(lead)
            if lead.status in STOP_STATUSES and lead.status != "won":
                cancel_followups(lead, f"Lead status stops automation: {lead.status}", current_user().id)
            convert_won_lead_to_customer(lead)
        elif action == "tag":
            lead.tag = data.get("value") or lead.tag
        elif action == "assign":
            if lead.assigned_to != assignee.id:
                lead.assigned_to = assignee.id
                send_lead_assignment_notification(lead, assignee)
        elif action == "delete" and has_permission(current_user(), "leads", "delete"):
            db.session.delete(lead)
    log_activity(current_user().id, "leads_bulk_updated", "lead", None, f"{len(rows)} leads affected")
    db.session.commit()
    return jsonify({"updated": len(rows)})


@bp.post("/")
@permission_required("leads", "create")
def create_lead():
    data = request.get_json() or {}
    try:
        data["lost_reason"], data["lost_reason_detail"] = validate_lost_reason(
            data.get("status") or "new", data.get("lost_reason"), data.get("lost_reason_detail"),
        )
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    actor = current_user()
    if has_permission(actor, "leads", "assign"):
        assigned_staff = assignable_staff(data.get("assigned_to"))
        if not assigned_staff:
            return jsonify({"message": "Assigned Staff is required. Select an active staff member."}), 400
        data["assigned_to"] = assigned_staff.id
    else:
        assigned_staff = actor
        data["assigned_to"] = actor.id
    lead = normalize_lead(update_model(Lead(), data, ALLOWED))
    if "expected_close_date" in data:
        lead.expected_close_date = parse_date(data["expected_close_date"]) if data.get("expected_close_date") else None
    db.session.add(lead)
    db.session.flush()
    score_and_apply_lead(lead)
    send_lead_acknowledgement(lead)
    send_lead_assignment_notification(lead, assigned_staff)
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
    previous_scoring_signature = lead_scoring_signature(lead)
    data = request.get_json() or {}
    try:
        data["lost_reason"], data["lost_reason_detail"] = validate_lost_reason(
            data.get("status", lead.status),
            data.get("lost_reason", lead.lost_reason),
            data.get("lost_reason_detail", lead.lost_reason_detail),
        )
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    actor = current_user()
    previous_assignee_id = lead.assigned_to
    new_assignee = None
    if "assigned_to" in data:
        if not has_permission(actor, "leads", "assign"):
            if str(data.get("assigned_to") or "") != str(lead.assigned_to or actor.id):
                return jsonify({"message": "Lead assignment permission required"}), 403
            data["assigned_to"] = lead.assigned_to or actor.id
        else:
            assignee = assignable_staff(data.get("assigned_to"))
            if not assignee:
                return jsonify({"message": "Assigned Staff is required. Select an active staff member."}), 400
            data["assigned_to"] = assignee.id
            new_assignee = assignee
    if data.get("status") == "won" and lead.status != "won" and not has_permission(current_user(), "leads", "convert"):
        return jsonify({"message": "Lead conversion permission required"}), 403
    old_status = lead.status
    normalize_lead(update_model(lead, data, ALLOWED))
    if lead.status in STOP_STATUSES and lead.status != "won":
        cancel_followups(lead, f"Lead status stops automation: {lead.status}", current_user().id)
    if new_assignee and previous_assignee_id != lead.assigned_to:
        send_lead_assignment_notification(lead, new_assignee)
    if "expected_close_date" in data:
        lead.expected_close_date = parse_date(data["expected_close_date"]) if data.get("expected_close_date") else None
    rescore_if_changed(lead, previous_scoring_signature)
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
    return jsonify({s: [x.to_dict() for x in newest_first(scoped().filter_by(status=s)).all()] for s in statuses})
