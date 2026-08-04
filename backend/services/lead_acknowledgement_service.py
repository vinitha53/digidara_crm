from flask import current_app

from extensions import db
from models import MessageLog
from services.email_service import send_email
from services.whatsapp_service import send_whatsapp, send_whatsapp_template


def lead_interest(lead):
    return lead.course_name or lead.internship_name or lead.business_requirement or lead.service or "your enquiry"


def lead_acknowledgement_message(lead):
    interest = lead_interest(lead)
    if lead.lead_category == "course":
        subject = f"Course enquiry received - {interest}"
        body = f"Hi {lead.name}, thank you for your interest in {interest}. Our Digidara team will contact you shortly with course details."
    elif lead.lead_category == "internship":
        duration = f"{lead.program_duration} " if lead.program_duration else ""
        subject = f"Internship enquiry received - {interest}"
        body = f"Hi {lead.name}, thank you for your interest in the {duration}{interest} internship. Our team will guide you with the next steps."
    else:
        subject = "Business enquiry received - Digidara Technologies"
        body = f"Hi {lead.name}, thank you for contacting Digidara Technologies about {interest}. Our business team will reach out shortly."
    return subject, " ".join(body.split())


def customer_welcome_message(lead):
    interest = lead_interest(lead)
    if lead.lead_category == "course":
        subject = f"Welcome as a customer - {interest}"
        body = f"Hi {lead.name}, welcome to Digidara Technologies. Your course enquiry for {interest} is confirmed, and our team will share the next steps shortly."
    elif lead.lead_category == "internship":
        duration = f"{lead.program_duration} " if lead.program_duration else ""
        subject = f"Internship onboarding - {interest}"
        body = f"Hi {lead.name}, welcome to Digidara Technologies. Your {duration}{interest} internship is confirmed, and our team will guide you through onboarding."
    else:
        subject = "Business customer onboarding - Digidara Technologies"
        body = f"Hi {lead.name}, welcome to Digidara Technologies. We are happy to start working with you on {interest}. Our business team will contact you with the next steps."
    return subject, " ".join(body.split())


def message_status(result):
    if result.get("ok"):
        return "sent"
    if result.get("skipped"):
        return "skipped"
    return "failed"


def send_lead_acknowledgement(lead, send_email_copy=True):
    subject, body = lead_acknowledgement_message(lead)
    template_name = current_app.config.get("WHATSAPP_LEAD_TEMPLATE_NAME")
    language = current_app.config.get("WHATSAPP_TEMPLATE_LANGUAGE", "en")
    template_params = [lead.name, lead_interest(lead)]
    whatsapp_result = send_whatsapp_template(lead.phone, template_name, language, template_params) if template_name else send_whatsapp(lead.phone, body)
    if not whatsapp_result.get("ok") and not whatsapp_result.get("skipped"):
        fallback = send_whatsapp(lead.phone, body)
        if fallback.get("ok"):
            whatsapp_result = fallback
    db.session.add(MessageLog(
        recipient_type="lead",
        recipient_id=lead.id,
        recipient_name=lead.name,
        channel="WhatsApp",
        message_body=body,
        template_used=template_name or "Lead acknowledgement",
        status=message_status(whatsapp_result),
    ))
    if send_email_copy:
        email_result = send_email(lead.email, subject, f"<p>{body}</p>")
        db.session.add(MessageLog(
            recipient_type="lead",
            recipient_id=lead.id,
            recipient_name=lead.name,
            channel="Email",
            message_body=body,
            template_used="Lead acknowledgement",
            status=message_status(email_result),
        ))
    return whatsapp_result


def send_customer_conversion_welcome(customer, lead, send_email_copy=True):
    subject, body = customer_welcome_message(lead)
    template_name = current_app.config.get("WHATSAPP_CUSTOMER_TEMPLATE_NAME")
    language = current_app.config.get("WHATSAPP_TEMPLATE_LANGUAGE", "en")
    template_params = [customer.name, lead_interest(lead)]
    whatsapp_result = send_whatsapp_template(customer.phone, template_name, language, template_params) if template_name else send_whatsapp(customer.phone, body)
    if not whatsapp_result.get("ok") and not whatsapp_result.get("skipped"):
        fallback = send_whatsapp(customer.phone, body)
        if fallback.get("ok"):
            whatsapp_result = fallback
    db.session.add(MessageLog(
        recipient_type="customer",
        recipient_id=customer.id,
        recipient_name=customer.name,
        channel="WhatsApp",
        message_body=body,
        template_used=template_name or "Customer conversion welcome",
        status=message_status(whatsapp_result),
    ))
    if send_email_copy:
        email_result = send_email(customer.email, subject, f"<p>{body}</p>")
        db.session.add(MessageLog(
            recipient_type="customer",
            recipient_id=customer.id,
            recipient_name=customer.name,
            channel="Email",
            message_body=body,
            template_used="Customer conversion welcome",
            status=message_status(email_result),
        ))
    return whatsapp_result
