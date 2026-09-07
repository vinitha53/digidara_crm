import json
from datetime import datetime, timedelta

from flask import Blueprint, current_app, has_request_context, jsonify, request
from sqlalchemy import case, func, or_
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import AIFollowUpHistory, AIFollowUpPromptLog, AIFollowUpTemplate, ActivityLog, CompanySettings, Customer, Lead, MessageLog, Task, User
from services.ai_followup_schedule_service import schedule_next_followup, test_mode_enabled
from services.ai_followup_service import DEFAULT_TEMPLATE_BODIES, SEQUENCE_LENGTH, SUCCESS_STATUSES, automation_stop_reason, cancel_followups, effective_sequence_limit, history_recipient, next_sequence_step, provider_details, render_template, seed_sequence_templates, successful_sequence_count
from services.ai_service import generate_followup_message
from services.email_service import send_email
from services.lead_acknowledgement_service import lead_interest
from services.whatsapp_service import send_whatsapp, send_whatsapp_template
from .utils import current_user, log_activity, parse_datetime, permission_required

bp = Blueprint("ai_followups", __name__, url_prefix="/api/ai-followups")
ACTIVE_STATUSES = ["new", "contacted", "qualified"]


def visible_lead(lead_id):
    user = current_user()
    query = Lead.query.filter(Lead.id == lead_id)
    if user.role != "admin":
        query = query.filter(Lead.assigned_to == user.id)
    return query.first_or_404()


def scoped_leads(user=None):
    user = user or current_user()
    query = Lead.query
    return query if user.role == "admin" else query.filter(Lead.assigned_to == user.id)


def scoped_history(user=None):
    user = user or current_user()
    query = AIFollowUpHistory.query.join(Lead, AIFollowUpHistory.lead_id == Lead.id)
    return query if user.role == "admin" else query.filter(Lead.assigned_to == user.id)


def settings_row():
    row = db.session.get(CompanySettings, 1)
    if not row:
        row = CompanySettings(id=1)
        db.session.add(row)
        db.session.flush()
    return row


def channel_for(lead, settings):
    return lead.ai_preferred_channel or settings.ai_followup_preferred_channel or "WhatsApp"


def message_status(result):
    return "sent" if result.get("ok") else "skipped" if result.get("skipped") else "failed"


def build_context(lead):
    messages = MessageLog.query.filter_by(recipient_type="lead", recipient_id=lead.id).order_by(MessageLog.sent_at.desc()).limit(10).all()
    tasks = Task.query.filter((Task.related_type == "lead") & ((Task.related_id == lead.id) | (Task.related_name == lead.name))).order_by(Task.created_at.desc()).limit(8).all()
    activity = ActivityLog.query.filter_by(entity_type="lead", entity_id=lead.id).order_by(ActivityLog.created_at.desc()).limit(8).all()
    followups = AIFollowUpHistory.query.filter_by(lead_id=lead.id).order_by(AIFollowUpHistory.created_at.desc()).limit(8).all()
    return "\n".join([
        f"Notes: {lead.notes or '-'}",
        f"Customer-facing interest: {lead.service or '-'}",
        "Previous messages: " + " | ".join([f"{m.channel} {m.status}: {m.message_body}" for m in messages])[:2500],
        "Open tasks: " + " | ".join([f"{t.title} ({t.status}, due {t.due_date})" for t in tasks if t.status != "done"])[:1200],
        "Recent CRM activity types: " + " | ".join([a.action for a in activity])[:1200],
        "Previous AI follow-ups: " + " | ".join([f"{f.status}: {f.final_message or f.generated_message or f.skip_reason}" for f in followups])[:1800],
    ])


def stop_reason(lead, settings):
    return automation_stop_reason(lead, settings)


def skip_reason(lead):
    automated_templates = [value for value in {current_app.config.get("WHATSAPP_AI_FOLLOWUP_TEMPLATE_NAME"), current_app.config.get("WHATSAPP_LEAD_TEMPLATE_NAME"), "AI Follow-up", "AI Follow-up text fallback", "Lead acknowledgement"} if value]
    recent_manual = MessageLog.query.filter(
        MessageLog.recipient_type == "lead", MessageLog.recipient_id == lead.id,
        or_(MessageLog.template_used.is_(None), ~MessageLog.template_used.in_(automated_templates)),
    ).order_by(MessageLog.sent_at.desc()).first()
    if recent_manual and recent_manual.sent_at and recent_manual.sent_at >= datetime.utcnow() - timedelta(hours=24):
        return "Recent salesperson communication exists"
    open_task = Task.query.filter((Task.related_type == "lead") & ((Task.related_id == lead.id) | (Task.related_name == lead.name)) & (Task.status != "done")).first()
    return f"Open task exists: {open_task.title}" if open_task else None


def schedule_next(lead, settings, base=None):
    return schedule_next_followup(lead, settings, base)


def template_for(lead, step):
    temperature = (lead.tag or "warm").lower()
    if temperature not in {"hot", "warm"} or not step:
        return None
    return AIFollowUpTemplate.query.filter_by(temperature=temperature, sequence_step=step).first()


def create_history(lead, settings, status, delivery_status="pending", message=None, skip=None, scheduled_for=None, sequence_step=None, template=None, automation_mode="manual", key=None):
    moment = scheduled_for or lead.ai_next_followup_at or datetime.utcnow()
    key = key or f"{lead.id}:{moment.strftime('%Y%m%d%H%M%S%f')}:{status}"
    existing = AIFollowUpHistory.query.filter_by(idempotency_key=key).first()
    if existing:
        return existing
    row = AIFollowUpHistory(
        lead_id=lead.id, user_id=lead.assigned_to, channel=channel_for(lead, settings), generated_message=message,
        sequence_step=sequence_step, temperature_snapshot=(lead.tag or "warm").lower(), recipient_phone=history_recipient(lead),
        original_phone=lead.phone, template_id=template.id if template else None, template_text=template.template_body if template else None,
        status=status, delivery_status=delivery_status, skip_reason=skip,
        stopped_reason=skip if status in {"stopped", "cancelled"} else None,
        stopped_at=datetime.utcnow() if status in {"stopped", "cancelled"} else None,
        scheduled_for=moment, automation_mode=automation_mode, idempotency_key=key,
    )
    db.session.add(row)
    db.session.flush()
    return row


def generate_for_lead(lead, settings, automation_mode="manual", history=None):
    reason = stop_reason(lead, settings)
    if reason:
        raise ValueError(reason)
    step = next_sequence_step(lead)
    template = template_for(lead, step)
    if template and not template.is_active:
        raise ValueError(f"Sequence message {step} is inactive")
    source_text = render_template(template.template_body, lead) if template else None
    variation_index = max(step - 1, 0) if step else AIFollowUpHistory.query.filter_by(lead_id=lead.id).count()
    generate_kwargs = {"variation_index": variation_index}
    if source_text:
        generate_kwargs["template_body"] = source_text
    result = generate_followup_message(lead, build_context(lead), settings, **generate_kwargs)
    history = history or create_history(lead, settings, "generated", message=result["message"], sequence_step=step, template=template, automation_mode=automation_mode)
    history.generated_message = result["message"]
    history.generated_at = datetime.utcnow()
    history.status = "generated"
    history.delivery_status = "pending"
    history.template_id = template.id if template else None
    history.template_text = template.template_body if template else None
    db.session.add(AIFollowUpPromptLog(followup_id=history.id, lead_id=lead.id, model=result["model"], prompt=result["prompt"], response=result["message"], status=result["status"], error=result["error"]))
    return history


def upsert_attempt_log(history, lead, channel, message, template_used, result):
    details = provider_details(result)
    row = MessageLog.query.filter_by(followup_id=history.id, template_used=template_used).first()
    if not row:
        row = MessageLog(followup_id=history.id, recipient_type="lead", recipient_id=lead.id)
        db.session.add(row)
    row.recipient_name = lead.name
    row.recipient_phone = details["recipient_phone"] or history_recipient(lead)
    row.channel = channel
    row.message_body = message
    row.template_used = template_used
    row.status = message_status(result)
    row.provider_status = details["provider_status"]
    row.provider_message_id = details["provider_message_id"]
    row.provider_response = details["provider_response"]
    row.error_message = details["provider_error"]
    row.sent_at = datetime.utcnow()


def send_history(history, body=None, actor_id=None):
    lead = db.session.get(Lead, history.lead_id)
    settings = settings_row()
    reason = stop_reason(lead, settings)
    if reason:
        history.status = "cancelled"
        history.delivery_status = "cancelled"
        history.stopped_reason = reason
        history.stopped_at = datetime.utcnow()
        return history
    if history.status in SUCCESS_STATUSES:
        return history
    message = " ".join(str(body or history.edited_message or history.generated_message or "").split())
    if not message:
        raise ValueError("A message is required before sending")
    channel = history.channel or channel_for(lead, settings)
    template_used = "AI Follow-up"
    if channel == "Email":
        result = send_email(lead.email, "Follow-up from Digidara Technologies", f"<p>{message}</p>")
        result["recipient_phone"] = lead.email
        upsert_attempt_log(history, lead, channel, message, template_used, result)
    else:
        template_name = current_app.config.get("WHATSAPP_AI_FOLLOWUP_TEMPLATE_NAME")
        language = current_app.config.get("WHATSAPP_TEMPLATE_LANGUAGE", "en")
        if template_name:
            result = send_whatsapp_template(lead.phone, template_name, language, [lead.name, lead_interest(lead), message])
            upsert_attempt_log(history, lead, channel, message, template_name, result)
            template_used = template_name
            if not result.get("ok") and not result.get("skipped"):
                result = send_whatsapp(lead.phone, message)
                template_used = "AI Follow-up text fallback"
                upsert_attempt_log(history, lead, channel, message, template_used, result)
        else:
            result = send_whatsapp(lead.phone, message)
            upsert_attempt_log(history, lead, channel, message, template_used, result)
    details = provider_details(result)
    status = message_status(result)
    history.final_message = message
    history.edited_message = body if body and body != history.generated_message else history.edited_message
    history.recipient_phone = details["recipient_phone"] or history_recipient(lead)
    history.provider_message_id = details["provider_message_id"]
    history.provider_status = details["provider_status"]
    history.provider_response = details["provider_response"]
    history.provider_error = details["provider_error"]
    history.status = status
    history.delivery_status = details["provider_status"]
    history.sent_at = datetime.utcnow()
    if status == "sent":
        lead.ai_last_followup_at = history.sent_at
        lead.ai_followup_count = successful_sequence_count(lead.id, history.temperature_snapshot)
        lead.ai_engagement_score = min(100, int(lead.ai_engagement_score or 0) + 8)
        limit = effective_sequence_limit(settings, history.temperature_snapshot)
        if history.sequence_step and history.sequence_step >= limit:
            cancel_followups(lead, "Sequence completed" if limit == SEQUENCE_LENGTH else f"Administrator safety limit reached ({limit})", actor_id, create_event=True)
        else:
            schedule_next(lead, settings, history.sent_at)
    else:
        schedule_next(lead, settings, history.sent_at)
    actor = current_user() if has_request_context() else None
    log_activity(actor_id or (actor.id if actor else lead.assigned_to), f"ai_followup_{history.status}", "lead", lead.id, lead.name)
    return history


def lead_queue_row(lead, settings):
    reason = stop_reason(lead, settings)
    waiting = test_mode_enabled() and lead.ai_next_followup_at is None
    last = AIFollowUpHistory.query.filter_by(lead_id=lead.id).order_by(AIFollowUpHistory.created_at.desc()).first()
    temperature = (lead.tag or "warm").lower()
    count = successful_sequence_count(lead.id, temperature if temperature in {"hot", "warm"} else None)
    return {
        **lead.to_dict(), "normalized_phone": history_recipient(lead), "owner": lead.assigned_user.name if lead.assigned_user else "Unassigned",
        "successful_messages": count, "sequence_step": min(count + 1, SEQUENCE_LENGTH),
        "sequence_length": SEQUENCE_LENGTH if temperature in {"hot", "warm"} else effective_sequence_limit(settings, "cold"),
        "channel": channel_for(lead, settings),
        "automation_status": "stopped" if reason else "not_scheduled" if waiting else "due" if lead.ai_next_followup_at and lead.ai_next_followup_at <= datetime.utcnow() else "scheduled",
        "stop_reason": reason or ("Edit and save this lead to enroll it in local minute testing." if waiting else None),
        "last_message": last.to_dict() if last else None,
    }


@bp.get("/lead/<int:lead_id>")
@permission_required("ai_followups", "view")
def lead_followups(lead_id):
    lead = visible_lead(lead_id)
    rows = AIFollowUpHistory.query.filter_by(lead_id=lead.id).order_by(AIFollowUpHistory.created_at.asc()).all()
    return jsonify({"lead": lead_queue_row(lead, settings_row()), "history": [row.to_dict() for row in rows]})


@bp.post("/lead/<int:lead_id>/pause")
@permission_required("ai_followups", "generate")
def pause(lead_id):
    lead = visible_lead(lead_id)
    reason = (request.get_json() or {}).get("reason") or "Paused manually"
    cancel_followups(lead, reason, current_user().id)
    log_activity(current_user().id, "ai_followup_paused", "lead", lead.id, lead.name)
    db.session.commit()
    return jsonify(lead_queue_row(lead, settings_row()))


@bp.post("/lead/<int:lead_id>/resume")
@permission_required("ai_followups", "generate")
def resume(lead_id):
    lead = visible_lead(lead_id)
    if (lead.status or "").lower() not in ACTIVE_STATUSES or Customer.query.filter_by(lead_id=lead.id).first():
        return jsonify({"message": "Converted or closed leads must be reopened before automation can resume."}), 409
    lead.ai_followup_enabled = True
    lead.ai_followup_paused_reason = None
    lead.ai_followup_stop_reason = None
    lead.ai_followup_stopped_at = None
    schedule_next(lead, settings_row(), datetime.utcnow())
    log_activity(current_user().id, "ai_followup_resumed", "lead", lead.id, lead.name)
    db.session.commit()
    return jsonify(lead_queue_row(lead, settings_row()))


@bp.post("/lead/<int:lead_id>/generate")
@permission_required("ai_followups", "generate")
def generate(lead_id):
    lead = visible_lead(lead_id)
    db.session.refresh(lead)
    try:
        history = generate_for_lead(lead, settings_row())
        db.session.commit()
        return jsonify(history.to_dict()), 201
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"message": str(exc)}), 409


@bp.post("/lead/<int:lead_id>/preview")
@permission_required("ai_followups", "generate")
def preview(lead_id):
    lead = visible_lead(lead_id)
    settings = settings_row()
    reason = stop_reason(lead, settings)
    if reason:
        return jsonify({"message": reason}), 409
    step = next_sequence_step(lead)
    template = template_for(lead, step)
    source = render_template(template.template_body, lead) if template else None
    result = generate_followup_message(lead, build_context(lead), settings, max((step or 1) - 1, 0), source)
    return jsonify({"sequence_step": step, "recipient_phone": history_recipient(lead), "template": template.to_dict() if template else None, "generated_message": result["message"]})


@bp.post("/history/<int:id>/send")
@permission_required("ai_followups", "send")
def send(id):
    history = AIFollowUpHistory.query.get_or_404(id)
    visible_lead(history.lead_id)
    if history.status in SUCCESS_STATUSES:
        return jsonify({"message": "This follow-up has already been sent."}), 409
    try:
        send_history(history, (request.get_json() or {}).get("message"), current_user().id)
        db.session.commit()
        return jsonify(history.to_dict())
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"message": str(exc)}), 409


@bp.get("/history/<int:id>")
@permission_required("ai_followups", "view")
def history_detail(id):
    history = AIFollowUpHistory.query.get_or_404(id)
    visible_lead(history.lead_id)
    attempts = MessageLog.query.filter_by(followup_id=history.id).order_by(MessageLog.sent_at.asc()).all()
    return jsonify({"history": history.to_dict(), "attempts": [row.to_dict() for row in attempts]})


@bp.post("/history/<int:id>/delivery")
@permission_required("ai_followups", "run")
def update_delivery(id):
    history = AIFollowUpHistory.query.get_or_404(id)
    visible_lead(history.lead_id)
    data = request.get_json() or {}
    provider_status = str(data.get("provider_status") or "").lower()
    if provider_status not in {"accepted", "sent", "delivered", "read", "failed"}:
        return jsonify({"message": "A valid provider_status is required"}), 400
    history.provider_status = provider_status
    history.delivery_status = provider_status
    history.provider_message_id = data.get("provider_message_id") or history.provider_message_id
    history.provider_response = json.dumps(data.get("provider_response"), default=str) if data.get("provider_response") is not None else history.provider_response
    history.provider_error = data.get("provider_error") if provider_status == "failed" else history.provider_error
    if provider_status in {"delivered", "read"}:
        history.status = provider_status
    MessageLog.query.filter_by(followup_id=history.id).update({
        MessageLog.provider_status: provider_status,
        MessageLog.status: "failed" if provider_status == "failed" else "sent",
        MessageLog.provider_message_id: history.provider_message_id,
        MessageLog.error_message: history.provider_error,
    }, synchronize_session=False)
    db.session.commit()
    return jsonify(history.to_dict())


@bp.post("/lead/<int:lead_id>/manual")
@permission_required("ai_followups", "generate")
def manual(lead_id):
    lead = visible_lead(lead_id)
    data = request.get_json() or {}
    history = create_history(lead, settings_row(), "manual", "skipped", message=data.get("note") or "Manual follow-up completed")
    history.outcome = data.get("outcome") or "manual_followup"
    lead.ai_followup_outcome = history.outcome
    schedule_next(lead, settings_row(), datetime.utcnow())
    log_activity(current_user().id, "manual_followup_marked", "lead", lead.id, lead.name)
    db.session.commit()
    return jsonify(history.to_dict()), 201


@bp.post("/lead/<int:lead_id>/cancel")
@permission_required("ai_followups", "generate")
def cancel(lead_id):
    lead = visible_lead(lead_id)
    cancel_followups(lead, (request.get_json() or {}).get("reason") or "Cancelled manually", current_user().id)
    db.session.commit()
    return jsonify(lead_queue_row(lead, settings_row()))


@bp.get("/templates")
@permission_required("ai_followups", "view")
def templates():
    seed_sequence_templates()
    db.session.commit()
    rows = AIFollowUpTemplate.query.order_by(AIFollowUpTemplate.temperature, AIFollowUpTemplate.sequence_step).all()
    return jsonify([row.to_dict() for row in rows])


@bp.put("/templates/<int:id>")
@permission_required("settings", "update")
def update_template(id):
    row = AIFollowUpTemplate.query.get_or_404(id)
    data = request.get_json() or {}
    body = " ".join(str(data.get("template_body", row.template_body)).split())
    if not body:
        return jsonify({"message": "Template text is required"}), 400
    row.template_body = body
    row.description = data.get("description", row.description)
    row.is_active = bool(data.get("is_active", row.is_active))
    row.updated_by = current_user().id
    db.session.commit()
    return jsonify(row.to_dict())


@bp.post("/templates/<int:id>/restore")
@permission_required("settings", "update")
def restore_template(id):
    row = AIFollowUpTemplate.query.get_or_404(id)
    row.template_body = DEFAULT_TEMPLATE_BODIES[row.temperature][row.sequence_step - 1]
    row.description = f"{row.temperature.title()} sequence message {row.sequence_step}"
    row.is_active = True
    row.updated_by = current_user().id
    db.session.commit()
    return jsonify(row.to_dict())


@bp.post("/run")
@permission_required("ai_followups", "run")
def run_scheduler():
    limit = min(max(int((request.get_json() or {}).get("limit") or 25), 1), 100)
    return jsonify(process_due_followups(limit=limit, actor_id=current_user().id))


def process_due_followups(limit=25, actor_id=None):
    settings = settings_row()
    now = datetime.utcnow()
    query = Lead.query.filter(Lead.ai_followup_enabled == 1, Lead.status.in_(ACTIVE_STATUSES), Lead.ai_next_followup_at <= now)
    actor = db.session.get(User, actor_id) if actor_id else None
    if actor and actor.role != "admin":
        query = query.filter(Lead.assigned_to == actor.id)
    leads = query.order_by(Lead.ai_next_followup_at.asc()).with_for_update(skip_locked=True).limit(limit).all()
    result = {"sent": 0, "skipped": 0, "failed": 0, "generated": 0, "claimed": 0}
    for lead in leads:
        db.session.refresh(lead)
        reason = stop_reason(lead, settings)
        if reason:
            cancel_followups(lead, reason, actor_id, create_event=True)
            result["skipped"] += 1
            continue
        reason = skip_reason(lead)
        if reason:
            create_history(lead, settings, "skipped", "skipped", skip=reason, scheduled_for=now, automation_mode="automatic")
            schedule_next(lead, settings, now)
            result["skipped"] += 1
            continue
        step = next_sequence_step(lead)
        template = template_for(lead, step)
        if template and not template.is_active:
            create_history(lead, settings, "skipped", "skipped", skip=f"Sequence message {step} is inactive", scheduled_for=now, sequence_step=step, template=template, automation_mode="automatic")
            schedule_next(lead, settings, now)
            result["skipped"] += 1
            continue
        key = f"lead:{lead.id}:{(lead.tag or 'warm').lower()}:step:{step}" if step else f"lead:{lead.id}:cold:{now.strftime('%Y%m%d%H%M')}"
        history = AIFollowUpHistory.query.filter_by(idempotency_key=key).first()
        if history and history.status in SUCCESS_STATUSES | {"pending", "generated"}:
            result["skipped"] += 1
            continue
        if history:
            history.status = "pending"
            history.delivery_status = "pending"
            history.claimed_at = now
            history.provider_error = None
        else:
            try:
                history = create_history(lead, settings, "pending", sequence_step=step, template=template, automation_mode="automatic", key=key)
                history.claimed_at = now
                db.session.flush()
            except IntegrityError:
                db.session.rollback()
                result["skipped"] += 1
                continue
        db.session.commit()
        result["claimed"] += 1
        lead = db.session.get(Lead, lead.id)
        history = db.session.get(AIFollowUpHistory, history.id)
        if stop_reason(lead, settings):
            history.status = "cancelled"
            history.delivery_status = "cancelled"
            result["skipped"] += 1
            db.session.commit()
            continue
        generate_for_lead(lead, settings, "automatic", history)
        db.session.commit()
        result["generated"] += 1
        lead = db.session.get(Lead, lead.id)
        history = db.session.get(AIFollowUpHistory, history.id)
        send_history(history, actor_id=actor_id)
        db.session.commit()
        result["sent" if history.status == "sent" else "failed" if history.status == "failed" else "skipped"] += 1
    return result


def apply_workbench_filters(lead_query, history_query):
    temperature = request.args.get("temperature")
    if temperature:
        lead_query = lead_query.filter(Lead.tag == temperature)
        history_query = history_query.filter(AIFollowUpHistory.temperature_snapshot == temperature)
    status = request.args.get("status")
    if status:
        if status == "converted":
            lead_query = lead_query.filter(Lead.status.in_(["won", "converted"]), Lead.ai_followup_count > 0)
            history_query = history_query.filter(Lead.status.in_(["won", "converted"]), Lead.ai_followup_count > 0)
        elif status in {"stopped", "paused"}:
            lead_query = lead_query.filter(Lead.ai_followup_enabled == 0)
            history_query = history_query.filter(or_(AIFollowUpHistory.status == status, AIFollowUpHistory.delivery_status == status))
        else:
            history_query = history_query.filter(or_(AIFollowUpHistory.status == status, AIFollowUpHistory.delivery_status == status))
    owner = request.args.get("owner")
    if owner:
        lead_query = lead_query.filter(Lead.assigned_to == int(owner))
        history_query = history_query.filter(Lead.assigned_to == int(owner))
    source = request.args.get("source")
    if source:
        lead_query = lead_query.filter(Lead.source == source)
        history_query = history_query.filter(Lead.source == source)
    search = request.args.get("search")
    if search:
        like = f"%{search.strip()}%"
        lead_query = lead_query.filter(or_(Lead.name.ilike(like), Lead.phone.ilike(like)))
        history_query = history_query.filter(or_(Lead.name.ilike(like), Lead.phone.ilike(like), AIFollowUpHistory.recipient_phone.ilike(like)))
    date_from = parse_datetime(request.args.get("date_from"))
    date_to = parse_datetime(request.args.get("date_to"))
    if date_from:
        history_query = history_query.filter(AIFollowUpHistory.created_at >= date_from)
    if date_to:
        history_query = history_query.filter(AIFollowUpHistory.created_at <= date_to + timedelta(days=1))
    due = request.args.get("due")
    now = datetime.utcnow()
    if due == "now":
        lead_query = lead_query.filter(Lead.ai_next_followup_at <= now)
    elif due == "today":
        lead_query = lead_query.filter(Lead.ai_next_followup_at >= datetime.combine(now.date(), datetime.min.time()), Lead.ai_next_followup_at <= datetime.combine(now.date(), datetime.max.time()))
    return lead_query, history_query


def scoped_metrics(user):
    now = datetime.utcnow()
    today_start = datetime.combine(now.date(), datetime.min.time())
    today_end = datetime.combine(now.date(), datetime.max.time())
    leads = scoped_leads(user)
    history = scoped_history(user)
    active = leads.filter(Lead.ai_followup_enabled == 1, Lead.status.in_(ACTIVE_STATUSES))
    sent = history.filter(AIFollowUpHistory.status.in_(SUCCESS_STATUSES))
    converted = leads.filter(Lead.status.in_(["won", "converted"]), Lead.ai_followup_count > 0)
    total_sent = sent.count()
    delivered = history.filter(AIFollowUpHistory.delivery_status.in_(["delivered", "read"])).count()
    converted_count = converted.count()
    return {
        "active_leads": active.count(), "hot_active": active.filter(Lead.tag == "hot").count(), "warm_active": active.filter(Lead.tag == "warm").count(),
        "ready_now": active.filter(Lead.ai_next_followup_at <= now).count(), "due_today": active.filter(Lead.ai_next_followup_at >= today_start, Lead.ai_next_followup_at <= today_end).count(),
        "sent": total_sent, "sent_today": sent.filter(AIFollowUpHistory.sent_at >= today_start, AIFollowUpHistory.sent_at <= today_end).count(),
        "delivered": delivered, "failed": history.filter(AIFollowUpHistory.status == "failed").count(),
        "failed_today": history.filter(AIFollowUpHistory.status == "failed", AIFollowUpHistory.sent_at >= today_start, AIFollowUpHistory.sent_at <= today_end).count(),
        "paused_stopped": leads.filter(Lead.ai_followup_enabled == 0).count(), "sequence_completed": leads.filter(Lead.ai_followup_stop_reason == "Sequence completed").count(),
        "converted_after_followup": converted_count, "delivery_success_rate": round(delivered / max(total_sent, 1) * 100, 1),
        "generated": history.filter(AIFollowUpHistory.status == "generated").count(),
        "skipped": history.filter(AIFollowUpHistory.status == "skipped").count(),
        "followup_conversion_rate": round(converted_count / max(active.count() + converted_count, 1) * 100, 1),
        "average_messages_before_conversion": round(db.session.query(func.avg(Lead.ai_followup_count)).filter(Lead.id.in_(converted.with_entities(Lead.id))).scalar() or 0, 1),
    }


def scoped_performance(user):
    history = scoped_history(user)
    def rows_for(label_column, key_column=None):
        key_column = key_column or label_column
        rows = history.with_entities(
            key_column, label_column, func.count(AIFollowUpHistory.id),
            func.sum(case((AIFollowUpHistory.status.in_(SUCCESS_STATUSES), 1), else_=0)),
            func.sum(case((AIFollowUpHistory.delivery_status.in_(["delivered", "read"]), 1), else_=0)),
            func.sum(case((AIFollowUpHistory.status == "failed", 1), else_=0)),
        ).group_by(key_column, label_column).all()
        return [{"key": key or "unknown", "name": label or "Unknown", "total": total, "sent": sent or 0, "delivered": delivered or 0, "failed": failed or 0} for key, label, total, sent, delivered, failed in rows]
    owner_query = history.join(User, Lead.assigned_to == User.id).with_entities(
        User.id, User.name, func.count(AIFollowUpHistory.id),
        func.sum(case((AIFollowUpHistory.status.in_(SUCCESS_STATUSES), 1), else_=0)),
        func.sum(case((AIFollowUpHistory.delivery_status.in_(["delivered", "read"]), 1), else_=0)),
        func.sum(case((AIFollowUpHistory.status == "failed", 1), else_=0)),
    ).group_by(User.id, User.name).all()
    owners = [{"key": key, "name": name, "total": total, "sent": sent or 0, "delivered": delivered or 0, "failed": failed or 0} for key, name, total, sent, delivered, failed in owner_query]
    return {
        "owners": owners,
        "sources": rows_for(Lead.source),
        "temperatures": rows_for(AIFollowUpHistory.temperature_snapshot),
    }


@bp.get("/workbench")
@permission_required("ai_followups", "view")
def workbench():
    settings = settings_row()
    user = current_user()
    lead_query = scoped_leads(user).filter(Lead.status.in_(ACTIVE_STATUSES + ["won", "lost", "converted", "closed", "not_interested"]))
    history_query = scoped_history(user)
    lead_query, history_query = apply_workbench_filters(lead_query, history_query)
    page = max(int(request.args.get("page", 1)), 1)
    per_page = min(max(int(request.args.get("per_page", 25)), 1), 100)
    history_page = history_query.order_by(AIFollowUpHistory.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    leads = lead_query.order_by(Lead.ai_next_followup_at.is_(None), Lead.ai_next_followup_at.asc(), Lead.created_at.desc()).limit(200).all()
    owners = User.query.filter(User.id.in_(scoped_leads(user).with_entities(Lead.assigned_to))).order_by(User.name).all()
    return jsonify({
        "settings": {**settings.to_dict(), "enabled": bool(settings.ai_followups_enabled or test_mode_enabled()), "test_mode": test_mode_enabled(), "sequence_length": SEQUENCE_LENGTH},
        "metrics": scoped_metrics(user), "leads": [lead_queue_row(lead, settings) for lead in leads], "history": [row.to_dict() for row in history_page.items],
        "pagination": {"page": page, "per_page": per_page, "total": history_page.total, "pages": history_page.pages},
        "owners": [{"id": row.id, "name": row.name} for row in owners],
    })


@bp.get("/analytics")
@permission_required("dashboard", "view")
def analytics():
    user = current_user()
    history = scoped_history(user)
    by_owner = db.session.query(User.id, User.name, func.count(AIFollowUpHistory.id)).join(Lead, Lead.assigned_to == User.id).join(AIFollowUpHistory, AIFollowUpHistory.lead_id == Lead.id)
    if user.role != "admin":
        by_owner = by_owner.filter(User.id == user.id)
    owner_rows = by_owner.group_by(User.id, User.name).all()
    return jsonify({
        **scoped_metrics(user), **scoped_performance(user), "total_followups": history.count(),
        "temperature_distribution": [{"name": key or "Unknown", "value": value} for key, value in history.with_entities(AIFollowUpHistory.temperature_snapshot, func.count(AIFollowUpHistory.id)).group_by(AIFollowUpHistory.temperature_snapshot).all()],
        "by_source": [{"name": key or "Unknown", "value": value} for key, value in history.with_entities(Lead.source, func.count(AIFollowUpHistory.id)).group_by(Lead.source).all()],
        "by_owner": [{"id": key, "name": name, "value": value} for key, name, value in owner_rows],
    })
