from flask import current_app

from extensions import db
from models import MessageLog
from services.lead_acknowledgement_service import lead_interest
from services.whatsapp_service import send_whatsapp_template


def assignment_message(lead, staff):
    interest = lead_interest(lead)
    priority = (lead.tag or "new").title()
    body = (
        f"Hello {staff.name}, a new lead has been assigned to you in Digidara CRM. "
        f"Lead: {lead.name}. Interest: {interest}. Phone: {lead.phone}. "
        f"Priority: {priority}. Please log in to the CRM and follow up promptly."
    )
    return " ".join(body.split()), [staff.name, lead.name, interest, lead.phone, priority]


def message_status(result):
    if result.get("ok"):
        return "sent"
    if result.get("skipped"):
        return "skipped"
    return "failed"


def send_lead_assignment_notification(lead, staff):
    body, template_params = assignment_message(lead, staff)
    template_name = current_app.config.get("WHATSAPP_LEAD_ASSIGNMENT_TEMPLATE_NAME")
    language = current_app.config.get("WHATSAPP_TEMPLATE_LANGUAGE", "en")
    result = send_whatsapp_template(
        staff.phone,
        template_name,
        language,
        template_params,
    )
    db.session.add(MessageLog(
        recipient_type="employee",
        recipient_id=staff.id,
        recipient_name=staff.name,
        channel="WhatsApp",
        message_body=body,
        template_used=template_name or "Staff lead assignment",
        status=message_status(result),
    ))
    return result
