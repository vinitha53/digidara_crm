from datetime import datetime, timedelta
from flask import Blueprint, current_app, has_request_context, jsonify, request
from sqlalchemy import or_
from extensions import db
from models import AIFollowUpHistory, AIFollowUpPromptLog, ActivityLog, CompanySettings, Customer, Lead, MessageLog, Task
from permissions import has_permission
from services.ai_service import generate_followup_message
from services.ai_followup_schedule_service import schedule_next_followup, test_mode_enabled
from services.email_service import send_email
from services.lead_acknowledgement_service import lead_interest
from services.whatsapp_service import send_whatsapp, send_whatsapp_template
from .utils import current_user, log_activity, permission_required

bp = Blueprint("ai_followups", __name__, url_prefix="/api/ai-followups")
STOP_STATUSES = {"won", "lost", "converted", "closed", "not_interested"}


def visible_lead(lead_id):
    user = current_user()
    query = Lead.query.filter(Lead.id == lead_id)
    if user.role != "admin":
        query = query.filter(Lead.assigned_to == user.id)
    return query.first_or_404()


def settings_row():
    row = CompanySettings.query.get(1)
    if not row:
        row = CompanySettings(id=1)
        db.session.add(row)
        db.session.flush()
    return row


def channel_for(lead, settings):
    return lead.ai_preferred_channel or settings.ai_followup_preferred_channel or "WhatsApp"


def message_status(result):
    if result.get("ok"):
        return "sent"
    if result.get("skipped"):
        return "skipped"
    return "failed"


def build_context(lead):
    messages = MessageLog.query.filter_by(recipient_type="lead", recipient_id=lead.id).order_by(MessageLog.sent_at.desc()).limit(10).all()
    tasks = Task.query.filter(
        (Task.related_type == "lead") & ((Task.related_id == lead.id) | (Task.related_name == lead.name))
    ).order_by(Task.created_at.desc()).limit(8).all()
    activity = ActivityLog.query.filter_by(entity_type="lead", entity_id=lead.id).order_by(ActivityLog.created_at.desc()).limit(8).all()
    followups = AIFollowUpHistory.query.filter_by(lead_id=lead.id).order_by(AIFollowUpHistory.created_at.desc()).limit(8).all()
    lines = [
        f"Notes: {lead.notes or '-'}",
        f"Previous messages: " + " | ".join([f"{m.channel} {m.status}: {m.message_body}" for m in messages])[:2500],
        f"Open tasks: " + " | ".join([f"{t.title} ({t.status}, due {t.due_date})" for t in tasks if t.status != "done"])[:1200],
        f"Recent CRM activity: " + " | ".join([a.action for a in activity])[:1200],
        f"Previous AI follow-ups: " + " | ".join([f"{f.status}: {f.edited_message or f.generated_message or f.skip_reason}" for f in followups])[:1800],
    ]
    return "\n".join(lines)


def stop_reason(lead, settings):
    if not settings.ai_followups_enabled and not test_mode_enabled():
        return "AI follow-ups disabled in settings"
    if not lead.ai_followup_enabled:
        return lead.ai_followup_paused_reason or "Automation paused for this lead"
    if (lead.status or "").lower() in STOP_STATUSES:
        return f"Lead status stops automation: {lead.status}"
    if Customer.query.filter_by(lead_id=lead.id).first():
        return "Lead already converted to customer"
    if "no further communication" in (lead.notes or "").lower() or "do not contact" in (lead.notes or "").lower():
        return "Lead requested no further communication"
    if int(lead.ai_followup_count or 0) >= int(settings.ai_followup_max_count or 0):
        return "Maximum follow-up count reached"
    return None


def skip_reason(lead):
    automated_templates = [value for value in {
        current_app.config.get("WHATSAPP_AI_FOLLOWUP_TEMPLATE_NAME"),
        current_app.config.get("WHATSAPP_LEAD_TEMPLATE_NAME"),
        "AI Follow-up",
        "Lead acknowledgement",
    } if value]
    recent_manual = MessageLog.query.filter(
        MessageLog.recipient_type == "lead",
        MessageLog.recipient_id == lead.id,
        or_(
            MessageLog.template_used.is_(None),
            ~MessageLog.template_used.in_(automated_templates),
        ),
    ).order_by(MessageLog.sent_at.desc()).first()
    if recent_manual and recent_manual.sent_at and recent_manual.sent_at >= datetime.utcnow() - timedelta(hours=24):
        return "Recent salesperson communication exists"
    open_task = Task.query.filter(
        (Task.related_type == "lead") &
        ((Task.related_id == lead.id) | (Task.related_name == lead.name)) &
        (Task.status != "done")
    ).first()
    if open_task:
        return f"Open task exists: {open_task.title}"
    return None


def schedule_next(lead, settings, base=None):
    return schedule_next_followup(lead, settings, base)


def create_history(lead, settings, status, delivery_status="pending", message=None, skip=None, scheduled_for=None):
    key = f"{lead.id}:{(scheduled_for or datetime.utcnow()).strftime('%Y%m%d%H%M%S%f')}:{status}"
    existing = AIFollowUpHistory.query.filter_by(idempotency_key=key).first()
    if existing:
        return existing
    row = AIFollowUpHistory(
        lead_id=lead.id,
        user_id=lead.assigned_to,
        channel=channel_for(lead, settings),
        generated_message=message,
        status=status,
        delivery_status=delivery_status,
        skip_reason=skip,
        scheduled_for=scheduled_for or lead.ai_next_followup_at or datetime.utcnow(),
        idempotency_key=key,
    )
    db.session.add(row)
    db.session.flush()
    return row


def generate_for_lead(lead, settings):
    context = build_context(lead)
    variation_index = AIFollowUpHistory.query.filter_by(lead_id=lead.id).count()
    result = generate_followup_message(lead, context, settings, variation_index=variation_index)
    history = create_history(lead, settings, "generated", message=result["message"])
    db.session.add(AIFollowUpPromptLog(
        followup_id=history.id,
        lead_id=lead.id,
        model=result["model"],
        prompt=result["prompt"],
        response=result["message"],
        status=result["status"],
        error=result["error"],
    ))
    return history


def send_history(history, body=None, actor_id=None):
    lead = Lead.query.get(history.lead_id)
    settings = settings_row()
    message = body or history.edited_message or history.generated_message
    if not message:
        return history
    channel = history.channel or channel_for(lead, settings)
    if channel == "Email":
        result = send_email(lead.email, "Follow-up from Digidara Technologies", f"<p>{message}</p>")
    else:
        template_name = current_app.config.get("WHATSAPP_AI_FOLLOWUP_TEMPLATE_NAME")
        language = current_app.config.get("WHATSAPP_TEMPLATE_LANGUAGE", "en")
        result = send_whatsapp_template(lead.phone, template_name, language, [lead.name, lead_interest(lead), message]) if template_name else send_whatsapp(lead.phone, message)
        if not result.get("ok") and not result.get("skipped"):
            fallback = send_whatsapp(lead.phone, message)
            if fallback.get("ok"):
                result = fallback
    status = message_status(result)
    history.status = "sent" if status == "sent" else "failed" if status == "failed" else "skipped"
    history.delivery_status = status
    history.sent_at = datetime.utcnow()
    db.session.add(MessageLog(
        recipient_type="lead",
        recipient_id=lead.id,
        recipient_name=lead.name,
        channel=channel,
        message_body=message,
        template_used=current_app.config.get("WHATSAPP_AI_FOLLOWUP_TEMPLATE_NAME") if channel != "Email" else "AI Follow-up",
        status=status,
    ))
    lead.ai_last_followup_at = history.sent_at
    lead.ai_followup_count = int(lead.ai_followup_count or 0) + (1 if status in {"sent", "skipped"} else 0)
    lead.ai_engagement_score = min(100, int(lead.ai_engagement_score or 0) + (8 if status == "sent" else 1))
    schedule_next(lead, settings, history.sent_at)
    actor = current_user() if has_request_context() else None
    log_activity(actor_id or (actor.id if actor else lead.assigned_to), f"ai_followup_{history.status}", "lead", lead.id, lead.name)
    return history


def lead_queue_row(lead, settings):
    reason = stop_reason(lead, settings)
    waiting_for_test_schedule = test_mode_enabled() and lead.ai_next_followup_at is None
    last = AIFollowUpHistory.query.filter_by(lead_id=lead.id).order_by(AIFollowUpHistory.created_at.desc()).first()
    return {
        "id": lead.id,
        "name": lead.name,
        "phone": lead.phone,
        "email": lead.email,
        "company": lead.company,
        "status": lead.status,
        "tag": lead.tag,
        "source": lead.source,
        "service": lead.service,
        "assigned_to": lead.assigned_to,
        "ai_followup_enabled": bool(lead.ai_followup_enabled),
        "ai_followup_count": lead.ai_followup_count or 0,
        "ai_engagement_score": lead.ai_engagement_score or 0,
        "ai_next_followup_at": lead.ai_next_followup_at.isoformat() if lead.ai_next_followup_at else None,
        "ai_last_followup_at": lead.ai_last_followup_at.isoformat() if lead.ai_last_followup_at else None,
        "channel": channel_for(lead, settings),
        "automation_status": "stopped" if reason else "not scheduled" if waiting_for_test_schedule else "ready",
        "stop_reason": reason or ("Edit and save this lead to enroll it in the local minute test." if waiting_for_test_schedule else None),
        "last_message": last.to_dict() if last else None,
    }


@bp.get("/lead/<int:lead_id>")
@permission_required("leads", "view")
def lead_followups(lead_id):
    lead = visible_lead(lead_id)
    rows = AIFollowUpHistory.query.filter_by(lead_id=lead.id).order_by(AIFollowUpHistory.created_at.desc()).limit(25).all()
    return jsonify({"lead": lead.to_dict(), "history": [row.to_dict() for row in rows]})


@bp.post("/lead/<int:lead_id>/pause")
@permission_required("ai_followups", "generate")
def pause(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    data = request.get_json() or {}
    lead.ai_followup_enabled = False
    lead.ai_followup_paused_reason = data.get("reason") or "Paused manually"
    create_history(lead, settings_row(), "paused", "skipped", skip=lead.ai_followup_paused_reason)
    log_activity(current_user().id, "ai_followup_paused", "lead", lead.id, lead.name)
    db.session.commit()
    return jsonify(lead.to_dict())


@bp.post("/lead/<int:lead_id>/resume")
@permission_required("ai_followups", "generate")
def resume(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    settings = settings_row()
    lead.ai_followup_enabled = True
    lead.ai_followup_paused_reason = None
    schedule_next(lead, settings, datetime.utcnow())
    log_activity(current_user().id, "ai_followup_resumed", "lead", lead.id, lead.name)
    db.session.commit()
    return jsonify(lead.to_dict())


@bp.post("/lead/<int:lead_id>/generate")
@permission_required("ai_followups", "generate")
def generate(lead_id):
    # Reload the record on every click so recently edited notes are always used.
    lead = visible_lead(lead_id)
    db.session.refresh(lead)
    history = generate_for_lead(lead, settings_row())
    db.session.commit()
    return jsonify(history.to_dict()), 201


@bp.post("/history/<int:id>/send")
@permission_required("ai_followups", "send")
def send(id):
    history = AIFollowUpHistory.query.get_or_404(id)
    data = request.get_json() or {}
    if data.get("message"):
        history.edited_message = data["message"]
    send_history(history)
    db.session.commit()
    return jsonify(history.to_dict())


@bp.post("/lead/<int:lead_id>/manual")
@permission_required("ai_followups", "generate")
def manual(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    data = request.get_json() or {}
    history = create_history(lead, settings_row(), "manual", "skipped", message=data.get("note") or "Manual follow-up completed")
    history.outcome = data.get("outcome") or "manual_followup"
    lead.ai_followup_outcome = history.outcome
    schedule_next(lead, settings_row(), datetime.utcnow())
    log_activity(current_user().id, "manual_followup_marked", "lead", lead.id, lead.name)
    db.session.commit()
    return jsonify(history.to_dict()), 201


@bp.post("/run")
@permission_required("ai_followups", "run")
def run_scheduler():
    limit = int((request.get_json() or {}).get("limit") or 25)
    return jsonify(process_due_followups(limit=limit, actor_id=current_user().id))


def process_due_followups(limit=25, actor_id=None):
    settings = settings_row()
    now = datetime.utcnow()
    query = Lead.query.filter(
        Lead.ai_followup_enabled == 1,
        Lead.status.in_(["new", "contacted", "qualified"]),
        ((Lead.ai_next_followup_at == None) | (Lead.ai_next_followup_at <= now)),
    )
    # Local minute mode only enrolls explicitly scheduled leads. This prevents
    # old CRM records with a null schedule from being messaged during testing.
    if test_mode_enabled():
        query = query.filter(Lead.ai_next_followup_at.isnot(None))
    leads = query.limit(limit).all()
    result = {"sent": 0, "skipped": 0, "failed": 0, "generated": 0}
    for lead in leads:
        reason = stop_reason(lead, settings) or skip_reason(lead)
        if reason:
            create_history(lead, settings, "skipped", "skipped", skip=reason, scheduled_for=now)
            schedule_next(lead, settings, now)
            result["skipped"] += 1
            continue
        history = generate_for_lead(lead, settings)
        result["generated"] += 1
        send_history(history, actor_id=actor_id)
        if history.status == "sent":
            result["sent"] += 1
        elif history.status == "failed":
            result["failed"] += 1
        else:
            result["skipped"] += 1
    db.session.commit()
    return result


@bp.get("/workbench")
@permission_required("ai_followups", "view")
def workbench():
    settings = settings_row()
    today = datetime.utcnow().date()
    active_statuses = ["new", "contacted", "qualified"]
    leads = Lead.query.filter(Lead.status.in_(active_statuses)).order_by(
        Lead.ai_next_followup_at.is_(None),
        Lead.ai_next_followup_at.asc(),
        Lead.created_at.desc(),
    ).limit(100).all()
    history = AIFollowUpHistory.query.order_by(AIFollowUpHistory.created_at.desc()).limit(100).all()
    generated = AIFollowUpHistory.query.filter_by(status="generated").count()
    sent = AIFollowUpHistory.query.filter_by(status="sent").count()
    failed = AIFollowUpHistory.query.filter_by(status="failed").count()
    skipped = AIFollowUpHistory.query.filter_by(status="skipped").count()
    due_today = Lead.query.filter(
        Lead.ai_followup_enabled == 1,
        Lead.status.in_(active_statuses),
        Lead.ai_next_followup_at >= datetime.combine(today, datetime.min.time()),
        Lead.ai_next_followup_at <= datetime.combine(today, datetime.max.time()),
    ).count()
    ready_query = Lead.query.filter(
        Lead.ai_followup_enabled == 1,
        Lead.status.in_(active_statuses),
        ((Lead.ai_next_followup_at == None) | (Lead.ai_next_followup_at <= datetime.utcnow())),
    )
    if test_mode_enabled():
        ready_query = ready_query.filter(Lead.ai_next_followup_at.isnot(None))
    ready_now = ready_query.count()
    return jsonify({
        "settings": {
            "enabled": bool(settings.ai_followups_enabled or test_mode_enabled()),
            "test_mode": test_mode_enabled(),
            "test_intervals_minutes": {
                "hot": current_app.config.get("AI_FOLLOWUP_TEST_HOT_MINUTES"),
                "warm": current_app.config.get("AI_FOLLOWUP_TEST_WARM_MINUTES"),
                "cold": current_app.config.get("AI_FOLLOWUP_TEST_COLD_MINUTES"),
            } if test_mode_enabled() else None,
            "hot_interval_days": settings.ai_followup_hot_interval_days,
            "warm_interval_days": settings.ai_followup_warm_interval_days,
            "cold_interval_days": settings.ai_followup_cold_interval_days,
            "preferred_channel": settings.ai_followup_preferred_channel,
            "model": settings.ai_followup_llm_model,
        },
        "metrics": {
            "active_leads": len(leads),
            "ready_now": ready_now,
            "due_today": due_today,
            "generated": generated,
            "sent": sent,
            "failed": failed,
            "skipped": skipped,
        },
        "leads": [lead_queue_row(lead, settings) for lead in leads],
        "history": [row.to_dict() for row in history],
    })


@bp.get("/analytics")
@permission_required("dashboard", "view")
def analytics():
    today = datetime.utcnow().date()
    total = AIFollowUpHistory.query.count()
    sent = AIFollowUpHistory.query.filter_by(status="sent").count()
    failed = AIFollowUpHistory.query.filter_by(status="failed").count()
    pending = Lead.query.filter(Lead.ai_followup_enabled == 1, Lead.status.in_(["new", "contacted", "qualified"])).count()
    today_due = Lead.query.filter(Lead.ai_next_followup_at >= datetime.combine(today, datetime.min.time()), Lead.ai_next_followup_at <= datetime.combine(today, datetime.max.time())).count()
    temps = dict(db.session.query(Lead.tag, db.func.count(Lead.id)).group_by(Lead.tag).all())
    return jsonify({
        "total_followups": total,
        "sent": sent,
        "failed": failed,
        "pending_leads": pending,
        "today_scheduled": today_due,
        "successful_deliveries": sent,
        "failed_deliveries": failed,
        "response_rate": 0,
        "conversion_rate_after_followup": 0,
        "average_time_to_conversion_days": 0,
        "temperature_distribution": temps,
    })
