from datetime import date, timedelta
from flask import Blueprint, Response, jsonify, request
import base64
import csv
import io
from extensions import db
from sqlalchemy import and_, or_
from models import ActivityLog, CompanySettings, Customer, CustomerDocument, CustomerNote, Lead, MessageLog, Task
from permissions import has_permission
from services.email_service import send_email
from services.google_reviews_service import find_customer_review
from services.whatsapp_service import send_whatsapp
from .utils import current_user, log_activity, permission_required, parse_date, update_model

bp = Blueprint("customers", __name__, url_prefix="/api/customers")
ALLOWED = ["lead_id", "name", "phone", "email", "company", "service", "value", "status", "assigned_to", "notes", "rating"]


def message_status(result):
    if result.get("ok"):
        return "sent"
    if result.get("skipped"):
        return "skipped"
    return "failed"


def normalize_rating(customer):
    if customer.rating in ("", None):
        customer.rating = None
        return
    try:
        customer.rating = max(1, min(5, int(customer.rating)))
    except (TypeError, ValueError):
        customer.rating = None


def scoped():
    user = current_user()
    q = Customer.query.filter(Customer.lead_id.isnot(None))
    return q if has_permission(user, "leads", "assign") else q.filter(Customer.assigned_to == user.id)


def needs_contact_filter():
    cutoff = date.today() - timedelta(days=7)
    return and_(
        Customer.status.in_(["active", "followup"]),
        or_(Customer.last_contact.is_(None), Customer.last_contact <= cutoff),
    )


def apply_segment(q, segment):
    if not segment or segment == "all":
        return q
    q = q.join(Lead, Lead.id == Customer.lead_id)
    if segment == "academic":
        return q.filter(Lead.lead_category.in_(["course", "internship"]))
    if segment == "project":
        return q.filter(Lead.lead_category == "client_project")
    return q.filter(Lead.lead_category == segment)


def customer_rows(rows):
    lead_ids = [row.lead_id for row in rows if row.lead_id]
    leads = {lead.id: lead for lead in Lead.query.filter(Lead.id.in_(lead_ids)).all()} if lead_ids else {}
    return [row.to_dict() | {
        "lead_category": leads[row.lead_id].lead_category if row.lead_id in leads else None,
        "interest": lead_interest(leads.get(row.lead_id), row.service),
    } for row in rows]


def lead_interest(lead, fallback):
    if not lead:
        return fallback
    if lead.lead_category == "course":
        return lead.course_name or lead.service or fallback
    if lead.lead_category == "internship":
        return lead.internship_name or lead.service or fallback
    return lead.service or fallback


def customer_health(customer, lead, tasks, messages):
    open_tasks = [task for task in tasks if task.status != "done"]
    overdue_tasks = [
        task for task in open_tasks
        if task.due_date and task.due_date < date.today()
    ]
    score = 70
    if customer.status == "active":
        score += 10
    if customer.rating and customer.rating >= 4:
        score += 10
    if overdue_tasks:
        score -= min(25, len(overdue_tasks) * 8)
    if not messages:
        score -= 10
    if lead and lead.status == "won":
        score += 5
    score = max(0, min(100, score))
    if score >= 80:
        label = "healthy"
    elif score >= 55:
        label = "watch"
    else:
        label = "risk"
    return {
        "score": score,
        "label": label,
        "open_tasks": len(open_tasks),
        "overdue_tasks": len(overdue_tasks),
        "message_count": len(messages),
    }


def customer_summary(customer, lead, health, messages, tasks):
    source = lead.source if lead else "direct"
    latest_message = messages[0].sent_at.isoformat() if messages else "no recent communication"
    next_task = next((task for task in tasks if task.status != "done"), None)
    next_action = next_task.title if next_task else "No pending task"
    return {
        "headline": f"{customer.name} is a {customer.status} customer for {customer.service}.",
        "relationship": f"Originated from {source}; relationship health is {health['label']} at {health['score']}%.",
        "engagement": f"{health['message_count']} logged messages; latest activity: {latest_message}.",
        "next_action": next_action,
    }


def timeline_item(kind, title, body, timestamp, meta=None):
    return {
        "kind": kind,
        "title": title,
        "body": body,
        "timestamp": timestamp.isoformat() if hasattr(timestamp, "isoformat") else timestamp,
        "meta": meta or {},
    }


@bp.get("/")
@permission_required("customers", "view")
def list_customers():
    q = apply_segment(scoped(), request.args.get("segment"))
    if request.args.get("status"):
        q = q.filter(Customer.status == request.args["status"])
    if request.args.get("attention") == "contact_overdue":
        q = q.filter(needs_contact_filter())
    if request.args.get("search"):
        like = f"%{request.args['search']}%"
        q = q.filter((Customer.name.ilike(like)) | (Customer.phone.ilike(like)) | (Customer.email.ilike(like)))
    page = int(request.args.get("page", 1))
    items = q.order_by(Customer.created_at.desc()).paginate(page=page, per_page=25, error_out=False)
    return jsonify({"items": customer_rows(items.items), "total": items.total, "page": page, "pages": items.pages})


@bp.get("/overview")
@permission_required("customers", "view")
def customer_overview():
    base = scoped()
    count = lambda query: query.with_entities(db.func.count(Customer.id)).scalar() or 0
    return jsonify({
        "total": count(base),
        "active": count(base.filter(Customer.status == "active")),
        "followup": count(base.filter(Customer.status == "followup")),
        "contact_overdue": count(base.filter(needs_contact_filter())),
        "segments": {
            "academic": count(apply_segment(base, "academic")),
            "course": count(apply_segment(base, "course")),
            "internship": count(apply_segment(base, "internship")),
            "project": count(apply_segment(base, "project")),
        },
    })


@bp.get("/export")
@permission_required("customers", "view")
def export_customers():
    rows = scoped().order_by(Customer.created_at.desc()).all()
    output = io.StringIO()
    fields = ["id", "name", "phone", "email", "company", "service", "status", "rating", "last_contact", "assigned_to", "created_at"]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for customer in rows:
        data = customer.to_dict()
        writer.writerow({field: data.get(field) for field in fields})
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=customers.csv"})


@bp.post("/")
@permission_required("customers", "create")
def create_customer():
    data = request.get_json() or {}
    if not data.get("lead_id"):
        return jsonify({"message": "Customers are created only when a lead status changes to won."}), 400
    lead = Lead.query.get_or_404(data["lead_id"])
    if lead.status != "won":
        return jsonify({"message": "Lead must be won before it can become a customer."}), 400
    existing = Customer.query.filter_by(lead_id=lead.id).first()
    if existing:
        return jsonify(existing.to_dict()), 200
    data |= {k: getattr(lead, k) for k in ["name", "phone", "email", "company", "service", "assigned_to", "notes"]}
    customer = update_model(Customer(), data, ALLOWED)
    normalize_rating(customer)
    if data.get("last_contact"):
        customer.last_contact = parse_date(data["last_contact"])
    db.session.add(customer)
    db.session.flush()
    log_activity(current_user().id, "customer_created", "customer", customer.id, customer.name)
    db.session.commit()
    return jsonify(customer.to_dict()), 201


@bp.get("/<int:id>")
@permission_required("customers", "view")
def detail(id):
    return jsonify(scoped().filter_by(id=id).first_or_404().to_dict())


@bp.get("/<int:id>/360")
@permission_required("customers", "view")
def customer_360(id):
    customer = scoped().filter_by(id=id).first_or_404()
    lead = Lead.query.get(customer.lead_id) if customer.lead_id else None
    messages = MessageLog.query.filter_by(
        recipient_type="customer",
        recipient_id=customer.id,
    ).order_by(MessageLog.sent_at.desc()).limit(20).all()
    task_query = Task.query.filter(
        (Task.related_type == "customer") & (
            (Task.related_id == customer.id) | (Task.related_name == customer.name)
        )
    )
    if not has_permission(current_user(), "tasks", "assign"):
        task_query = task_query.filter(Task.assigned_to == current_user().id)
    tasks = task_query.order_by(Task.due_date.is_(None), Task.due_date.asc(), Task.created_at.desc()).limit(20).all()
    activity = ActivityLog.query.filter(
        ((ActivityLog.entity_type == "customer") & (ActivityLog.entity_id == customer.id))
        | ((ActivityLog.entity_type == "lead") & (ActivityLog.entity_id == customer.lead_id))
    ).order_by(ActivityLog.created_at.desc()).limit(20).all()
    notes = CustomerNote.query.filter_by(customer_id=customer.id).order_by(CustomerNote.created_at.desc()).limit(20).all()
    documents = CustomerDocument.query.filter_by(customer_id=customer.id).order_by(CustomerDocument.created_at.desc()).limit(20).all()

    health = customer_health(customer, lead, tasks, messages)
    timeline = []
    if lead:
        timeline.append(timeline_item(
            "lead",
            "Lead converted",
            f"{lead.name} moved through the {lead.source} source as a {lead.tag} lead.",
            lead.updated_at or lead.created_at,
            {"status": lead.status, "source": lead.source},
        ))
    timeline.extend([
        timeline_item("message", f"{message.channel} {message.status}", message.message_body, message.sent_at, {
            "template": message.template_used,
            "status": message.status,
        })
        for message in messages[:8]
    ])
    timeline.extend([
        timeline_item("note", f"{note.note_type.title()} note", note.note, note.created_at, {
            "user": note.user.name if note.user else None,
        })
        for note in notes[:8]
    ])
    timeline.extend([
        timeline_item("document", "Document attached", doc.file_name, doc.created_at, {"size": doc.file_size})
        for doc in documents[:8]
    ])
    timeline.extend([
        timeline_item("task", task.title, task.notes or task.related_name or task.priority, task.due_date or task.created_at, {
            "status": task.status,
            "priority": task.priority,
        })
        for task in tasks[:8]
    ])
    timeline.extend([
        timeline_item("activity", row.action.replace("_", " ").title(), row.entity_name, row.created_at)
        for row in activity[:8]
    ])
    timeline = sorted(
        timeline,
        key=lambda item: item["timestamp"] or "",
        reverse=True,
    )[:20]

    return jsonify({
        "customer": customer.to_dict(),
        "lead": lead.to_dict() if lead else None,
        "health": health,
        "ai_summary": customer_summary(customer, lead, health, messages, tasks),
        "messages": [message.to_dict() for message in messages],
        "tasks": [task.to_dict() for task in tasks],
        "activity": [row.to_dict() for row in activity],
        "notes": [row.to_dict() for row in notes],
        "documents": [row.to_dict() for row in documents],
        "timeline": timeline,
    })


@bp.post("/<int:id>/notes")
@permission_required("customers", "update")
def add_note(id):
    customer = scoped().filter_by(id=id).first_or_404()
    data = request.get_json() or {}
    if not data.get("note"):
        return jsonify({"message": "Note is required"}), 400
    note = CustomerNote(customer_id=customer.id, user_id=current_user().id, note=data["note"], note_type=data.get("note_type") or "general")
    db.session.add(note)
    log_activity(current_user().id, "customer_note_added", "customer", customer.id, customer.name)
    db.session.commit()
    return jsonify(note.to_dict()), 201


@bp.post("/<int:id>/documents")
@permission_required("customers", "update")
def add_document(id):
    customer = scoped().filter_by(id=id).first_or_404()
    data = request.get_json() or {}
    content = data.get("content_base64") or ""
    if not data.get("file_name") or not content:
        return jsonify({"message": "File name and content are required"}), 400
    document = CustomerDocument(
        customer_id=customer.id,
        user_id=current_user().id,
        file_name=data["file_name"],
        mime_type=data.get("mime_type") or "application/octet-stream",
        file_size=int(data.get("file_size") or 0),
        content_base64=content,
        description=data.get("description"),
    )
    db.session.add(document)
    log_activity(current_user().id, "customer_document_added", "customer", customer.id, customer.name)
    db.session.commit()
    return jsonify(document.to_dict()), 201


@bp.get("/<int:id>/documents/<int:document_id>")
@permission_required("customers", "view")
def download_document(id, document_id):
    scoped().filter_by(id=id).first_or_404()
    document = CustomerDocument.query.filter_by(id=document_id, customer_id=id).first_or_404()
    content = base64.b64decode(document.content_base64)
    return Response(content, mimetype=document.mime_type or "application/octet-stream", headers={"Content-Disposition": f"attachment; filename={document.file_name}"})


@bp.put("/<int:id>")
@permission_required("customers", "update")
def update(id):
    customer = scoped().filter_by(id=id).first_or_404()
    data = request.get_json() or {}
    update_model(customer, data, ALLOWED)
    normalize_rating(customer)
    if data.get("last_contact"):
        customer.last_contact = parse_date(data["last_contact"])
    log_activity(current_user().id, "customer_updated", "customer", customer.id, customer.name)
    db.session.commit()
    return jsonify(customer.to_dict())


@bp.post("/<int:id>/send-review")
@permission_required("customers", "send_review")
def send_review(id):
    customer = scoped().filter_by(id=id).first_or_404()
    settings = CompanySettings.query.get(1)
    review_url = settings.google_review_url if settings and settings.google_review_url else "https://g.page/r/CXarerFSXX1qEBM/review"
    body = f"Hi {customer.name}, thank you for choosing Digidara Technologies for {customer.service}. Please share your Google review here: {review_url}"
    email_subject = "Share your review for Digidara Technologies"
    whatsapp_result = send_whatsapp(customer.phone, body)
    db.session.add(MessageLog(recipient_type="customer", recipient_id=customer.id, recipient_name=customer.name, channel="WhatsApp", message_body=body, template_used="Google review request", status=message_status(whatsapp_result)))
    email_result = send_email(customer.email, email_subject, f"<p>{body}</p>")
    db.session.add(MessageLog(recipient_type="customer", recipient_id=customer.id, recipient_name=customer.name, channel="Email", message_body=body, template_used="Google review request", status=message_status(email_result)))
    log_activity(current_user().id, "google_review_request_sent", "customer", customer.id, customer.name)
    db.session.commit()
    return jsonify({"message": "Review request queued", "review_url": review_url}), 201


@bp.post("/<int:id>/sync-review")
@permission_required("customers", "sync_review")
def sync_review(id):
    customer = scoped().filter_by(id=id).first_or_404()
    result = find_customer_review(customer)
    if not result.get("ok"):
        return jsonify(result), 400
    if not result.get("matched"):
        return jsonify({
            "message": "No matching Google review found for this customer name yet.",
            "place_rating": result.get("place_rating"),
            "user_ratings_total": result.get("user_ratings_total"),
        }), 404
    customer.rating = result["rating"]
    log_activity(current_user().id, "google_review_rating_synced", "customer", customer.id, customer.name)
    db.session.commit()
    return jsonify({"customer": customer.to_dict(), "review": result})


@bp.delete("/<int:id>")
@permission_required("customers", "delete")
def delete(id):
    customer = scoped().filter_by(id=id).first_or_404()
    db.session.delete(customer)
    log_activity(current_user().id, "customer_deleted", "customer", id, customer.name)
    db.session.commit()
    return jsonify({"message": "Customer deleted"})
