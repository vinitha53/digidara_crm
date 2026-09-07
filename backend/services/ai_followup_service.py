import json
from datetime import datetime

from extensions import db
from models import AIFollowUpHistory, AIFollowUpTemplate, Customer
from services.ai_followup_schedule_service import test_mode_enabled
from services.whatsapp_service import whatsapp_recipient


STOP_STATUSES = {"won", "lost", "converted", "closed", "not_interested"}
SUCCESS_STATUSES = {"sent", "accepted", "delivered", "read"}
SEQUENCE_TEMPERATURES = {"hot", "warm"}
SEQUENCE_LENGTH = 10

DEFAULT_TEMPLATE_BODIES = {
    "hot": [
        "Hi {lead_name}, thanks for your interest in {service}. Would you like help with the next step?",
        "Hi {lead_name}, I’m following up on {service}. Is there anything you would like us to clarify?",
        "Hello {lead_name}, would a quick conversation help you decide how to proceed with {service}?",
        "Hi {lead_name}, we’re available to answer your questions about {service}. What would be most useful?",
        "Hello {lead_name}, checking whether you would like to continue with {service}. I can help with the next step.",
        "Hi {lead_name}, is {service} still a priority for you? Let us know how we can assist.",
        "Hello {lead_name}, I wanted to make sure you have the information you need about {service}.",
        "Hi {lead_name}, we’re ready to help whenever you want to move forward with {service}.",
        "Hello {lead_name}, would you like us to arrange the next step for your {service} enquiry?",
        "Hi {lead_name}, this is our final scheduled follow-up about {service}. Reply anytime if you would like assistance.",
    ],
    "warm": [
        "Hi {lead_name}, thank you for considering {service}. Would you like more information?",
        "Hello {lead_name}, I’m checking in about your interest in {service}. How can we help?",
        "Hi {lead_name}, do you have any questions about {service} that we can answer?",
        "Hello {lead_name}, when the time is right, we can guide you through the next step for {service}.",
        "Hi {lead_name}, I wanted to keep your {service} enquiry moving. What information would help?",
        "Hello {lead_name}, are you still exploring {service}? Our team is available to assist.",
        "Hi {lead_name}, we can help you evaluate the next step for {service} whenever convenient.",
        "Hello {lead_name}, checking whether you need any clarification regarding {service}.",
        "Hi {lead_name}, would you like to reconnect with our team about {service}?",
        "Hello {lead_name}, this is our final scheduled check-in about {service}. You’re welcome to reply anytime.",
    ],
}


def seed_sequence_templates():
    for temperature, bodies in DEFAULT_TEMPLATE_BODIES.items():
        for step, body in enumerate(bodies, 1):
            if not AIFollowUpTemplate.query.filter_by(temperature=temperature, sequence_step=step).first():
                db.session.add(AIFollowUpTemplate(
                    temperature=temperature,
                    sequence_step=step,
                    template_body=body,
                    description=f"{temperature.title()} sequence message {step}",
                    is_active=True,
                ))


def render_template(body, lead):
    values = {
        "lead_name": lead.name or "there",
        "service": lead.service or "your enquiry",
        "owner_name": lead.assigned_user.name if lead.assigned_user else "our team",
        "company": lead.company or "",
    }
    text = str(body or "")
    for key, value in values.items():
        text = text.replace("{" + key + "}", str(value))
    return " ".join(text.split())


def successful_sequence_count(lead_id, temperature=None):
    query = AIFollowUpHistory.query.filter(
        AIFollowUpHistory.lead_id == lead_id,
        AIFollowUpHistory.status.in_(SUCCESS_STATUSES),
        AIFollowUpHistory.sequence_step.isnot(None),
    )
    if temperature:
        query = query.filter(AIFollowUpHistory.temperature_snapshot == temperature)
    return query.count()


def next_sequence_step(lead):
    temperature = (lead.tag or "warm").lower()
    if temperature not in SEQUENCE_TEMPERATURES:
        return None
    return min(successful_sequence_count(lead.id, temperature) + 1, SEQUENCE_LENGTH + 1)


def effective_sequence_limit(settings, temperature):
    if temperature not in SEQUENCE_TEMPERATURES:
        value = int(getattr(settings, "ai_followup_max_count", None) or 10)
        return max(1, value)
    configured = getattr(settings, "ai_followup_max_count", None)
    if configured is None:
        return SEQUENCE_LENGTH
    configured = int(configured)
    if configured == 0:
        return 0
    return min(configured, SEQUENCE_LENGTH)


def automation_stop_reason(lead, settings):
    if not getattr(settings, "ai_followups_enabled", False) and not test_mode_enabled():
        return "AI follow-ups disabled in settings"
    if not lead.ai_followup_enabled:
        return lead.ai_followup_stop_reason or lead.ai_followup_paused_reason or "Automation paused for this lead"
    if (lead.status or "").lower() in STOP_STATUSES:
        return f"Lead status stops automation: {lead.status}"
    if Customer.query.filter_by(lead_id=lead.id).first():
        return "Lead already converted to customer"
    notes = (lead.notes or "").lower()
    if "no further communication" in notes or "do not contact" in notes:
        return "Lead requested no further communication"
    temperature = (lead.tag or "warm").lower()
    limit = effective_sequence_limit(settings, temperature)
    if limit == 0:
        return "Outreach disabled by the configured safety limit"
    count = successful_sequence_count(lead.id, temperature if temperature in SEQUENCE_TEMPERATURES else None)
    if count >= limit:
        return "Sequence completed" if limit == SEQUENCE_LENGTH else f"Administrator safety limit reached ({limit})"
    return None


def cancel_followups(lead, reason, actor_id=None, create_event=True):
    now = datetime.utcnow()
    already_stopped = not lead.ai_followup_enabled and lead.ai_followup_stop_reason == reason
    lead.ai_followup_enabled = False
    lead.ai_next_followup_at = None
    lead.ai_followup_paused_reason = reason
    lead.ai_followup_stop_reason = reason
    lead.ai_followup_stopped_at = now
    AIFollowUpHistory.query.filter(
        AIFollowUpHistory.lead_id == lead.id,
        AIFollowUpHistory.status.in_(["generated", "pending"]),
    ).update({
        AIFollowUpHistory.status: "cancelled",
        AIFollowUpHistory.delivery_status: "cancelled",
        AIFollowUpHistory.stopped_at: now,
        AIFollowUpHistory.stopped_reason: reason,
    }, synchronize_session=False)
    if create_event and not already_stopped:
        db.session.add(AIFollowUpHistory(
            lead_id=lead.id,
            user_id=actor_id or lead.assigned_to,
            channel=lead.ai_preferred_channel or "WhatsApp",
            status="stopped",
            delivery_status="stopped",
            stopped_at=now,
            stopped_reason=reason,
            skip_reason=reason,
            scheduled_for=now,
            idempotency_key=f"lead:{lead.id}:stopped:{now.strftime('%Y%m%d%H%M%S%f')}",
        ))


def provider_details(result):
    data = result.get("data") or {}
    messages = data.get("messages") or [] if isinstance(data, dict) else []
    message_id = messages[0].get("id") if messages and isinstance(messages[0], dict) else None
    status = "accepted" if result.get("ok") else "skipped" if result.get("skipped") else "failed"
    return {
        "provider_message_id": message_id,
        "provider_status": status,
        "provider_response": json.dumps(data, default=str) if data else None,
        "provider_error": result.get("error") or (json.dumps(data, default=str) if not result.get("ok") and data else None),
        "recipient_phone": result.get("recipient_phone"),
    }


def history_recipient(lead):
    return whatsapp_recipient(lead.phone)
