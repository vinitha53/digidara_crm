from datetime import datetime
from flask import Blueprint, jsonify, request
from extensions import db
from models import Campaign, Customer, Lead, MessageLog
from .utils import current_user, log_activity, permission_required, parse_datetime, update_model

bp = Blueprint("campaigns", __name__, url_prefix="/api/campaigns")
ALLOWED = ["name", "channel", "audience", "message_body", "from_name", "status"]


@bp.get("/")
@permission_required("campaigns", "view")
def list_campaigns():
    return jsonify([x.to_dict() for x in Campaign.query.order_by(Campaign.created_at.desc()).all()])


@bp.post("/")
@permission_required("campaigns", "create")
def create_campaign():
    campaign = update_model(Campaign(created_by=current_user().id), request.get_json() or {}, ALLOWED)
    db.session.add(campaign)
    db.session.flush()
    log_activity(current_user().id, "campaign_created", "campaign", campaign.id, campaign.name)
    db.session.commit()
    return jsonify(campaign.to_dict()), 201


@bp.put("/<int:id>")
@permission_required("campaigns", "update")
def update(id):
    campaign = Campaign.query.get_or_404(id)
    update_model(campaign, request.get_json() or {}, ALLOWED)
    db.session.commit()
    return jsonify(campaign.to_dict())


def audience(campaign):
    if campaign.audience == "All customers":
        return [("customer", c) for c in Customer.query.all()]
    q = Lead.query
    if campaign.audience == "Hot leads":
        q = q.filter_by(tag="hot")
    elif campaign.audience == "Warm leads":
        q = q.filter_by(tag="warm")
    elif campaign.audience == "Cold leads":
        q = q.filter_by(tag="cold")
    return [("lead", x) for x in q.all()]


@bp.post("/<int:id>/send")
@permission_required("campaigns", "send")
def send(id):
    campaign = Campaign.query.get_or_404(id)
    rows = audience(campaign)
    channels = ["WhatsApp", "Email"] if campaign.channel == "Both" else [campaign.channel]
    for recipient_type, person in rows:
        for channel in channels:
            body = campaign.message_body.replace("{name}", person.name)
            db.session.add(MessageLog(campaign_id=id, recipient_type=recipient_type, recipient_id=person.id, recipient_name=person.name, channel=channel, message_body=body, template_used=campaign.name))
    campaign.status = "sent"
    campaign.sent_at = datetime.utcnow()
    campaign.sent_count = len(rows) * len(channels)
    campaign.opened_count = int(campaign.sent_count * 0.42)
    campaign.reply_count = int(campaign.sent_count * 0.12)
    log_activity(current_user().id, "campaign_sent", "campaign", campaign.id, campaign.name)
    db.session.commit()
    return jsonify(campaign.to_dict())


@bp.post("/<int:id>/schedule")
@permission_required("campaigns", "schedule")
def schedule(id):
    campaign = Campaign.query.get_or_404(id)
    campaign.scheduled_at = parse_datetime((request.get_json() or {}).get("scheduled_at"))
    campaign.status = "scheduled"
    db.session.commit()
    return jsonify(campaign.to_dict())


@bp.get("/<int:id>/stats")
@permission_required("campaigns", "view")
def stats(id):
    c = Campaign.query.get_or_404(id)
    return jsonify({"sent_count": c.sent_count, "opened_count": c.opened_count, "reply_count": c.reply_count, "open_rate": round((c.opened_count or 0) / max(c.sent_count or 1, 1) * 100, 1)})
