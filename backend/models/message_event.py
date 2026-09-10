from datetime import datetime

from extensions import db


class MessageEvent(db.Model):
    __tablename__ = "message_events"

    id = db.Column(db.Integer, primary_key=True)
    agency_id = db.Column(db.Integer, index=True)
    provider_message_id = db.Column(db.String(190), index=True)
    campaign_recipient_id = db.Column(db.Integer, db.ForeignKey("campaign_recipients.id", ondelete="SET NULL"), index=True)
    event_type = db.Column(db.String(40), nullable=False, index=True)
    event_timestamp = db.Column(db.DateTime)
    raw_event = db.Column(db.JSON)
    event_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    recipient = db.relationship("CampaignRecipient", foreign_keys=[campaign_recipient_id])
