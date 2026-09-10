import hashlib
import json
import re
import time
from collections import Counter
from datetime import datetime, timedelta

from flask import current_app
from sqlalchemy import and_, or_

from extensions import db
from models import ActivityLog, Campaign, CampaignRecipient, Lead, MessageEvent, MessageLog, Notification, User
from services.ai_followup_service import cancel_followups
from services.integration_service import configured_agency_id
from services.whatsapp_service import provider_message_id, safe_provider_response, send_whatsapp_template, whatsapp_recipient


FINAL_RECIPIENT_STATUSES = {"read", "replied", "failed", "skipped", "opted_out", "cancelled"}
DELIVERY_RANK = {"queued": 0, "sending": 1, "accepted": 2, "sent": 3, "delivered": 4, "read": 5, "replied": 6}
OPT_OUT_WORDS = {"STOP", "UNSUBSCRIBE", "REMOVE", "CANCEL", "NO MORE", "STOP ALL"}
SAFE_LEAD_FIELDS = {
    "name", "phone", "email", "company", "service", "destination", "city", "deal_value",
    "travel_date", "tag", "status", "source", "branch", "assigned_name", "first_name", "last_name",
}


def normalize_phone(value):
    normalized = whatsapp_recipient(value)
    return normalized if 10 <= len(normalized) <= 15 and normalized.isdigit() else ""


def campaign_query(user):
    agency_id = configured_agency_id()
    # NULL covers campaigns created before agency-ready campaign storage existed.
    query = Campaign.query.filter(or_(Campaign.agency_id == agency_id, Campaign.agency_id.is_(None)))
    return query if user.role == "admin" else query.filter(Campaign.created_by == user.id)


def scoped_leads(user, filters=None):
    filters = filters or {}
    query = Lead.query
    if user.role != "admin":
        query = query.filter(Lead.assigned_to == user.id)
    classification = str(filters.get("classification") or filters.get("audience_type") or "all").lower()
    if classification in {"hot", "warm", "cold"}:
        query = query.filter(Lead.tag == classification)
    if filters.get("status"):
        query = query.filter(Lead.status == str(filters["status"]).lower())
    if filters.get("source"):
        query = query.filter(Lead.source == str(filters["source"]).lower())
    if filters.get("service"):
        query = query.filter(Lead.service.ilike(f"%{str(filters['service']).strip()}%"))
    if filters.get("destination"):
        query = query.filter(Lead.destination.ilike(f"%{str(filters['destination']).strip()}%"))
    if filters.get("city"):
        query = query.filter(Lead.city.ilike(f"%{str(filters['city']).strip()}%"))
    if filters.get("assigned_to"):
        try:
            query = query.filter(Lead.assigned_to == int(filters["assigned_to"]))
        except (TypeError, ValueError):
            query = query.filter(Lead.id == -1)
    if filters.get("branch"):
        query = query.join(User, Lead.assigned_to == User.id).filter(User.branch == filters["branch"])
    if filters.get("created_from"):
        try:
            query = query.filter(Lead.created_at >= datetime.fromisoformat(str(filters["created_from"])[:10]))
        except ValueError:
            query = query.filter(Lead.id == -1)
    if filters.get("created_to"):
        try:
            query = query.filter(Lead.created_at < datetime.fromisoformat(str(filters["created_to"])[:10]) + timedelta(days=1))
        except ValueError:
            query = query.filter(Lead.id == -1)
    search = str(filters.get("search") or "").strip()
    if search:
        term = f"%{search}%"
        query = query.filter(or_(Lead.name.ilike(term), Lead.phone.ilike(term), Lead.email.ilike(term), Lead.company.ilike(term), Lead.service.ilike(term)))
    if str(filters.get("phone_availability") or "").lower() == "missing":
        query = query.filter(or_(Lead.phone.is_(None), Lead.phone == ""))
    elif str(filters.get("phone_availability") or "").lower() == "available":
        query = query.filter(Lead.phone.isnot(None), Lead.phone != "")
    if str(filters.get("opted_out") or "").lower() in {"1", "true", "yes"}:
        query = query.filter(Lead.opted_out.is_(True))
    elif str(filters.get("opted_out") or "").lower() in {"0", "false", "no"}:
        query = query.filter(or_(Lead.opted_out.is_(False), Lead.opted_out.is_(None)))
    consent = str(filters.get("marketing_consent") or "").lower()
    if consent == "granted":
        query = query.filter(or_(Lead.marketing_opt_in.is_(True), Lead.whatsapp_opt_in.is_(True)))
    elif consent == "pending":
        query = query.filter(Lead.marketing_opt_in.isnot(True), Lead.whatsapp_opt_in.isnot(True))
    return query.order_by(Lead.created_at.desc(), Lead.id.desc())


def lead_value(lead, field):
    if field == "first_name":
        return (lead.name or "").split()[0] if lead.name else ""
    if field == "last_name":
        parts = (lead.name or "").split(maxsplit=1)
        return parts[1] if len(parts) > 1 else ""
    if field == "assigned_name":
        return lead.assigned_user.name if lead.assigned_user else ""
    if field == "branch":
        return lead.assigned_user.branch if lead.assigned_user else ""
    if field not in SAFE_LEAD_FIELDS:
        return ""
    value = getattr(lead, field, "")
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")


def required_body_variables(template_snapshot):
    components = (template_snapshot or {}).get("components") or []
    body = next((component.get("text", "") for component in components if component.get("type") == "BODY"), "")
    return sorted({int(value) for value in re.findall(r"\{\{(\d+)\}\}", body)})


def render_template_variables(lead, mapping, template_snapshot):
    mapping = mapping or {}
    body_mapping = mapping.get("body") if isinstance(mapping.get("body"), dict) else mapping
    rendered = {}
    missing = []
    for index in required_body_variables(template_snapshot):
        config = body_mapping.get(str(index), {}) if isinstance(body_mapping, dict) else {}
        if isinstance(config, str):
            config = {"field": config}
        field = str(config.get("field") or "")
        if field == "fixed":
            value = str(config.get("value") or "").strip()
        else:
            value = lead_value(lead, field)
        if not value and config.get("fallback") not in (None, ""):
            value = str(config["fallback"]).strip()
        if not value:
            missing.append(index)
        rendered[str(index)] = value[:1024]
    return rendered, missing


def audience_analysis(user, filters=None, mapping=None, template_snapshot=None, preview_limit=50):
    rows = scoped_leads(user, filters).all()
    require_consent = current_app.config.get("CAMPAIGN_REQUIRE_MARKETING_CONSENT", True)
    seen = set()
    opted_out_phones = {normalize_phone(lead.phone) for lead in rows if lead.opted_out and normalize_phone(lead.phone)}
    eligible = []
    excluded = []
    reasons = Counter()
    for lead in rows:
        phone = normalize_phone(lead.phone)
        reason = None
        rendered, missing = render_template_variables(lead, mapping, template_snapshot or {})
        if not phone:
            reason = "invalid_or_missing_phone"
        elif lead.opted_out or phone in opted_out_phones:
            reason = "opted_out"
        elif require_consent and not (lead.marketing_opt_in or lead.whatsapp_opt_in):
            reason = "consent_required"
        elif phone in seen:
            reason = "duplicate_phone"
        elif missing:
            reason = "missing_template_variable"
        if phone:
            seen.add(phone)
        if reason:
            reasons[reason] += 1
            excluded.append({"lead": lead, "phone": phone or str(lead.phone or ""), "reason": reason, "rendered": rendered})
        else:
            eligible.append({"lead": lead, "phone": phone, "rendered": rendered})
    def public(item):
        lead = item["lead"]
        return {
            "id": lead.id, "name": lead.name, "phone": lead.phone, "normalized_phone": item["phone"],
            "email": lead.email, "company": lead.company, "classification": lead.tag, "status": lead.status,
            "source": lead.source, "service": lead.service, "destination": lead.destination, "city": lead.city,
            "assigned_name": lead.assigned_user.name if lead.assigned_user else None,
            "branch": lead.assigned_user.branch if lead.assigned_user else None,
            "marketing_opt_in": bool(lead.marketing_opt_in or lead.whatsapp_opt_in), "opted_out": bool(lead.opted_out),
            "created_at": lead.created_at.isoformat() if lead.created_at else None,
            "reason": item.get("reason"), "rendered_variables": item.get("rendered") or {},
        }
    return {
        "total_count": len(rows), "eligible_count": len(eligible), "excluded_count": len(excluded),
        "exclusion_reasons": dict(reasons),
        "eligible": eligible, "excluded": excluded,
        "preview": [public(item) for item in (eligible + excluded)[:preview_limit]],
    }


def refresh_campaign_counts(campaign):
    actual = or_(CampaignRecipient.skip_reason.is_(None), CampaignRecipient.skip_reason != "test_recipient")
    base = CampaignRecipient.query.filter_by(campaign_id=campaign.id).filter(actual)
    counts = dict(db.session.query(CampaignRecipient.status, db.func.count(CampaignRecipient.id)).filter_by(campaign_id=campaign.id).filter(actual).group_by(CampaignRecipient.status).all())
    campaign.total_count = sum(counts.values())
    campaign.skipped_count = counts.get("skipped", 0)
    campaign.opted_out_count = counts.get("opted_out", 0)
    campaign.eligible_count = base.filter(CampaignRecipient.queued_at.isnot(None)).count()
    campaign.queued_count = sum(counts.get(key, 0) for key in ("queued", "sending", "retry"))
    campaign.sent_count = base.filter(CampaignRecipient.sent_at.isnot(None)).count()
    campaign.delivered_count = base.filter(CampaignRecipient.delivered_at.isnot(None)).count()
    campaign.read_count = base.filter(or_(CampaignRecipient.read_at.isnot(None), CampaignRecipient.reply_count > 0)).count()
    campaign.replied_count = base.filter(CampaignRecipient.reply_count > 0).count()
    campaign.reply_count = campaign.replied_count
    campaign.failed_count = counts.get("failed", 0)
    campaign.opened_count = 0
    return counts


def snapshot_campaign(campaign, user):
    if campaign.recipients and campaign.status not in {"draft", "validated"}:
        return refresh_campaign_counts(campaign)
    CampaignRecipient.query.filter_by(campaign_id=campaign.id).delete(synchronize_session=False)
    analysis = audience_analysis(user, campaign.audience_filter or {"classification": campaign.audience_type}, campaign.variable_mapping, campaign.template_snapshot)
    now = datetime.utcnow()
    for item in analysis["eligible"]:
        lead = item["lead"]
        db.session.add(CampaignRecipient(
            agency_id=campaign.agency_id, campaign_id=campaign.id, lead_id=lead.id,
            recipient_name=lead.name, recipient_phone=lead.phone, normalized_phone=item["phone"],
            rendered_variables=item["rendered"], status="queued", queued_at=now,
        ))
    for item in analysis["excluded"]:
        lead = item["lead"]
        status = "opted_out" if item["reason"] == "opted_out" else "skipped"
        # Excluded rows are audit records, not send targets. A namespaced key
        # keeps every exclusion visible without violating the one-send-per-phone constraint.
        normalized = f"excluded:{lead.id}:{item['phone'] or 'invalid'}"
        db.session.add(CampaignRecipient(
            agency_id=campaign.agency_id, campaign_id=campaign.id, lead_id=lead.id,
            recipient_name=lead.name, recipient_phone=lead.phone, normalized_phone=normalized,
            rendered_variables=item["rendered"], status=status, skip_reason=item["reason"],
        ))
    campaign.audience_snapshot = {
        "captured_at": now.isoformat(), "total_count": analysis["total_count"],
        "eligible_count": analysis["eligible_count"], "exclusion_reasons": analysis["exclusion_reasons"],
    }
    db.session.flush()
    return refresh_campaign_counts(campaign)


def send_recipient(recipient):
    campaign = recipient.campaign
    if recipient.provider_message_id or recipient.status not in {"queued", "retry"}:
        return False
    now = datetime.utcnow()
    recipient.status = "sending"
    recipient.sending_at = now
    db.session.commit()  # Claim before the network request to prevent double sends.
    values = recipient.rendered_variables or {}
    params = [values[key] for key in sorted(values, key=lambda value: int(value))]
    result = send_whatsapp_template(
        recipient.normalized_phone, campaign.template_name, campaign.template_language,
        params, header_media_id=campaign.media_id if campaign.header_type == "IMAGE" else None,
    )
    now = datetime.utcnow()
    recipient.provider_response = safe_provider_response(result)
    if result.get("ok") and provider_message_id(result):
        recipient.provider_message_id = provider_message_id(result)
        recipient.status = "accepted"
        recipient.accepted_at = now
        recipient.sent_at = now
        if recipient.lead:
            recipient.lead.last_marketing_message_at = now
        db.session.add(MessageLog(
            campaign_id=campaign.id, recipient_type="lead", recipient_id=recipient.lead_id,
            recipient_name=recipient.recipient_name, recipient_phone=recipient.normalized_phone,
            channel="WhatsApp", message_body=campaign.message_body, status="sent",
            template_used=campaign.template_name, provider_message_id=recipient.provider_message_id,
            provider_status="accepted", provider_response=recipient.provider_response,
        ))
    else:
        recipient.retry_count += 1
        recipient.error_code = str(result.get("error_code") or "")[:80] or None
        recipient.error_message = str(result.get("error") or "WhatsApp send failed")[:1000]
        max_retries = current_app.config.get("CAMPAIGN_MAX_RETRIES", 3)
        if result.get("transient") and recipient.retry_count <= max_retries:
            recipient.status = "retry"
            recipient.next_retry_at = now + timedelta(seconds=min(3600, 30 * (2 ** (recipient.retry_count - 1))))
        else:
            recipient.status = "failed"
    db.session.commit()
    refresh_campaign_counts(campaign)
    db.session.commit()
    return True


def quiet_hours_active(now=None):
    start = current_app.config.get("CAMPAIGN_QUIET_HOURS_START")
    end = current_app.config.get("CAMPAIGN_QUIET_HOURS_END")
    if not start or not end:
        return False
    now = (now or datetime.now()).time()
    start_time = datetime.strptime(start, "%H:%M").time()
    end_time = datetime.strptime(end, "%H:%M").time()
    return start_time <= now < end_time if start_time < end_time else now >= start_time or now < end_time


def process_due_campaigns(limit=None):
    if not current_app.config.get("CAMPAIGN_SEND_ENABLED") or quiet_hours_active():
        return {"processed": 0, "disabled": not current_app.config.get("CAMPAIGN_SEND_ENABLED")}
    now = datetime.utcnow()
    # A crash after Meta accepted a request but before the response was stored
    # is deliberately not auto-retried: avoiding a duplicate send is safer.
    CampaignRecipient.query.filter(
        CampaignRecipient.status == "sending",
        CampaignRecipient.provider_message_id.is_(None),
        CampaignRecipient.sending_at < now - timedelta(minutes=15),
    ).update({
        CampaignRecipient.status: "failed",
        CampaignRecipient.error_code: "send_state_unknown",
        CampaignRecipient.error_message: "Worker stopped while awaiting Meta; reconcile before retrying.",
    }, synchronize_session=False)
    db.session.commit()
    due = Campaign.query.filter(
        Campaign.status.in_(["queued", "sending", "scheduled"]),
        or_(Campaign.scheduled_at.is_(None), Campaign.scheduled_at <= now),
    ).order_by(Campaign.created_at).all()
    processed = 0
    batch_size = min(int(limit or current_app.config.get("CAMPAIGN_BATCH_SIZE", 25)), 250)
    for campaign in due:
        if campaign.status == "scheduled":
            campaign.status = "queued"
        campaign.status = "sending"
        campaign.started_at = campaign.started_at or now
        db.session.commit()
        recipients = CampaignRecipient.query.filter(
            CampaignRecipient.campaign_id == campaign.id,
            or_(CampaignRecipient.status == "queued", and_(CampaignRecipient.status == "retry", CampaignRecipient.next_retry_at <= now)),
        ).order_by(CampaignRecipient.id).limit(batch_size - processed).all()
        for recipient in recipients:
            send_recipient(recipient)
            processed += 1
            if current_app.config.get("CAMPAIGN_DELAY_MS", 0):
                time.sleep(current_app.config["CAMPAIGN_DELAY_MS"] / 1000)
            if processed >= batch_size:
                break
        counts = refresh_campaign_counts(campaign)
        pending = sum(counts.get(key, 0) for key in ("queued", "sending", "retry"))
        if not pending:
            campaign.status = "completed"
            campaign.completed_at = datetime.utcnow()
            campaign.sent_at = campaign.sent_at or campaign.completed_at
        db.session.commit()
        if processed >= batch_size:
            break
    return {"processed": processed, "campaigns": len(due)}


def event_time(value):
    try:
        return datetime.utcfromtimestamp(int(value))
    except (TypeError, ValueError, OSError):
        return datetime.utcnow()


def store_event(raw, event_type, provider_id, recipient=None, timestamp=None):
    serialized = json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    event_hash = hashlib.sha256(f"{event_type}:{provider_id}:{serialized}".encode()).hexdigest()
    if MessageEvent.query.filter_by(event_hash=event_hash).first():
        return None
    event = MessageEvent(
        agency_id=recipient.agency_id if recipient else configured_agency_id(),
        provider_message_id=provider_id or None,
        campaign_recipient_id=recipient.id if recipient else None,
        event_type=event_type, event_timestamp=timestamp or datetime.utcnow(),
        raw_event=raw, event_hash=event_hash,
    )
    db.session.add(event)
    return event


def process_webhook_payload(payload):
    processed = 0
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value") or {}
            for status_event in value.get("statuses", []):
                provider_id = str(status_event.get("id") or "")
                status = str(status_event.get("status") or "").lower()
                recipient = CampaignRecipient.query.filter_by(provider_message_id=provider_id).first()
                if not recipient or not store_event(status_event, status, provider_id, recipient, event_time(status_event.get("timestamp"))):
                    continue
                when = event_time(status_event.get("timestamp"))
                if status == "failed":
                    error = (status_event.get("errors") or [{}])[0]
                    recipient.status = "failed"
                    recipient.error_code = str(error.get("code") or "")[:80] or None
                    recipient.error_message = str(error.get("title") or error.get("message") or "Delivery failed")[:1000]
                elif status in DELIVERY_RANK and DELIVERY_RANK[status] >= DELIVERY_RANK.get(recipient.status, 0):
                    recipient.status = status
                    setattr(recipient, f"{status}_at", when)
                recipient.last_event_at = when
                refresh_campaign_counts(recipient.campaign)
                processed += 1
            for message in value.get("messages", []):
                phone = normalize_phone(message.get("from"))
                provider_id = str(message.get("id") or "")
                context_id = str((message.get("context") or {}).get("id") or "")
                recipient = CampaignRecipient.query.filter_by(provider_message_id=context_id).first() if context_id else None
                if not recipient and phone:
                    recipient = CampaignRecipient.query.filter_by(normalized_phone=phone).order_by(CampaignRecipient.accepted_at.desc(), CampaignRecipient.id.desc()).first()
                if not recipient or not store_event(message, "reply", provider_id, recipient, event_time(message.get("timestamp"))):
                    continue
                text = str((message.get("text") or {}).get("body") or "").strip()
                when = event_time(message.get("timestamp"))
                recipient.status = "replied"
                recipient.replied_at = recipient.replied_at or when
                recipient.last_reply_at = when
                recipient.last_reply_text = text[:4000]
                recipient.last_event_at = when
                recipient.reply_count += 1
                lead = recipient.lead
                opted_out = text.upper().strip(" .!?") in OPT_OUT_WORDS
                if opted_out and lead:
                    lead.opted_out = True
                    lead.opted_out_at = when
                    lead.opted_out_reason = text[:255]
                    cancel_followups(lead, "WhatsApp marketing opt-out", actor_id=lead.assigned_to)
                    recipient.status = "opted_out"
                db.session.add(MessageLog(
                    campaign_id=recipient.campaign_id, recipient_type="lead", recipient_id=recipient.lead_id,
                    recipient_name=recipient.recipient_name, recipient_phone=phone, channel="WhatsApp",
                    message_body=text, status="sent", provider_message_id=provider_id,
                    provider_status="received", template_used=recipient.campaign.template_name,
                ))
                if lead:
                    db.session.add(ActivityLog(
                        user_id=lead.assigned_to, action="campaign_reply_received" if not opted_out else "whatsapp_opt_out_received",
                        entity_type="lead", entity_id=lead.id, entity_name=lead.name,
                        meta=f"campaign:{recipient.campaign_id}",
                    ))
                    notify_user_id = lead.assigned_to
                    if not notify_user_id:
                        admin = User.query.filter_by(role="admin", is_active=1).order_by(User.id).first()
                        notify_user_id = admin.id if admin else None
                    if notify_user_id:
                        db.session.add(Notification(
                            user_id=notify_user_id, type="campaign_reply",
                            title=f"WhatsApp reply from {lead.name}",
                            body=("Opted out: " if opted_out else "") + text[:500],
                        ))
                refresh_campaign_counts(recipient.campaign)
                processed += 1
    db.session.commit()
    return {"processed": processed}
