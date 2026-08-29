from datetime import datetime

from models import MessageLog, Task
from services.ai_service import classify_lead
from services.ai_followup_schedule_service import schedule_next_followup, test_mode_enabled


VALID_TEMPERATURES = {"hot", "warm", "cold"}


def lead_scoring_signature(lead):
    """Return the fields whose meaning can change a lead's sales priority."""
    return tuple(str(value or "").strip() for value in (
        lead.lead_category,
        lead.course_name,
        lead.internship_name,
        lead.business_requirement,
        lead.service,
        lead.source,
        lead.status,
        lead.deal_value,
        lead.notes,
    ))


def score_and_apply_lead(lead):
    """Classify a lead and persist the complete scoring result on the model."""
    messages = MessageLog.query.filter_by(recipient_type="lead", recipient_id=lead.id).all() if lead.id else []
    open_tasks = Task.query.filter(
        (Task.related_type == "lead") &
        ((Task.related_id == lead.id) | (Task.related_name == lead.name)) &
        (Task.status != "done")
    ).count() if lead.id else 0
    result = classify_lead(
        lead,
        message_count=len(messages),
        successful_messages=len([message for message in messages if message.status == "sent"]),
        open_tasks=open_tasks,
    )
    tag = str(result.get("tag") or "").strip().lower()
    previous_tag = lead.tag
    lead.tag = tag if tag in VALID_TEMPERATURES else "cold"
    lead.ai_score = max(0, min(100, int(result.get("score") or 0)))
    lead.ai_reason = str(result.get("reason") or "Lead classified from the available CRM information.").strip()
    factors = result.get("factors")
    lead.ai_score_factors = "; ".join(map(str, factors)) if isinstance(factors, list) else str(factors or "").strip()
    lead.ai_next_best_action = str(result.get("next_best_action") or "Review the lead and confirm the next step.").strip()
    lead.ai_scored_at = datetime.utcnow()
    if test_mode_enabled() and lead.ai_followup_enabled is not False and (
        lead.ai_next_followup_at is None or previous_tag != lead.tag
    ):
        schedule_next_followup(lead)
    return result


def rescore_if_changed(lead, previous_signature=None, force=False):
    if force or previous_signature is None or lead_scoring_signature(lead) != previous_signature:
        score_and_apply_lead(lead)
        return True
    return False
