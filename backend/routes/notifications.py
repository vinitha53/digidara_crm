import re
from urllib.parse import quote_plus
from flask import Blueprint, jsonify, request
from extensions import db
from models import Customer, Lead, Notification
from .utils import current_user, permission_required

bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")


def notification_href(notification, user):
    text = f"{notification.title or ''} {notification.body or ''}"
    lead_match = re.search(r"lead\s+(.+?)\s+matched", text, re.IGNORECASE)
    name = lead_match.group(1).strip(" .:-") if lead_match else ""
    if notification.type == "workflow":
        if name:
            lead = Lead.query.filter(Lead.assigned_to == user.id, Lead.name.ilike(name)).order_by(Lead.created_at.desc()).first()
            customer = None
            if lead:
                customer = Customer.query.filter_by(lead_id=lead.id, assigned_to=user.id).first()
            if not customer:
                customer = Customer.query.filter(Customer.assigned_to == user.id, Customer.name.ilike(name)).order_by(Customer.created_at.desc()).first()
            if customer:
                return f"/customers?search={quote_plus(customer.name)}"
            if lead:
                return f"/leads?search={quote_plus(lead.name)}"
            return f"/leads?search={quote_plus(name)}"
        return "/leads"
    if notification.type == "campaign_reply":
        reply_match = re.search(r"reply from\s+(.+)$", notification.title or "", re.IGNORECASE)
        return f"/leads?search={quote_plus(reply_match.group(1).strip())}" if reply_match else "/leads"
    if notification.type and notification.type.startswith("task"):
        return "/tasks"
    return None


def serialize_notification(notification, user):
    data = notification.to_dict()
    data["href"] = notification_href(notification, user)
    return data


@bp.get("/")
@permission_required("notifications", "view")
def list_notifications():
    user = current_user()
    try:
        limit = min(max(int(request.args.get("limit", 30)), 1), 100)
    except (TypeError, ValueError):
        limit = 30
    query = Notification.query.filter_by(user_id=user.id)
    if request.args.get("unread") == "1":
        query = query.filter_by(is_read=0)
    return jsonify([
        serialize_notification(x, user)
        for x in query.order_by(Notification.created_at.desc()).limit(limit).all()
    ])


@bp.post("/<int:id>/read")
@permission_required("notifications", "update")
def read_notification(id):
    notification = Notification.query.filter_by(id=id, user_id=current_user().id).first_or_404()
    notification.is_read = 1
    db.session.commit()
    return jsonify(serialize_notification(notification, current_user()))


@bp.post("/read-all")
@permission_required("notifications", "update")
def read_all():
    Notification.query.filter_by(user_id=current_user().id, is_read=0).update({"is_read": 1})
    db.session.commit()
    return jsonify({"message": "All read"})

