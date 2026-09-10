from datetime import datetime

from extensions import db


class CampaignRecipient(db.Model):
    __tablename__ = "campaign_recipients"
    __table_args__ = (
        db.UniqueConstraint("campaign_id", "normalized_phone", name="uq_campaign_recipient_phone"),
    )

    id = db.Column(db.Integer, primary_key=True)
    agency_id = db.Column(db.Integer, index=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id", ondelete="SET NULL"), index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id", ondelete="SET NULL"), index=True)
    recipient_name = db.Column(db.Text)
    recipient_phone = db.Column(db.Text)
    normalized_phone = db.Column(db.String(32), nullable=False)
    rendered_variables = db.Column(db.JSON)
    provider_message_id = db.Column(db.String(190), unique=True, index=True)
    provider_response = db.Column(db.Text)
    status = db.Column(db.String(40), nullable=False, default="queued", index=True)
    skip_reason = db.Column(db.Text)
    error_code = db.Column(db.String(80))
    error_message = db.Column(db.Text)
    queued_at = db.Column(db.DateTime)
    sending_at = db.Column(db.DateTime)
    accepted_at = db.Column(db.DateTime)
    sent_at = db.Column(db.DateTime)
    delivered_at = db.Column(db.DateTime)
    read_at = db.Column(db.DateTime)
    replied_at = db.Column(db.DateTime)
    last_event_at = db.Column(db.DateTime)
    reply_count = db.Column(db.Integer, nullable=False, default=0)
    last_reply_text = db.Column(db.Text)
    last_reply_at = db.Column(db.DateTime)
    retry_count = db.Column(db.Integer, nullable=False, default=0)
    next_retry_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    campaign = db.relationship("Campaign", back_populates="recipients")
    lead = db.relationship("Lead", foreign_keys=[lead_id])
    customer = db.relationship("Customer", foreign_keys=[customer_id])

    def to_dict(self):
        result = {
            column.name: (getattr(self, column.name).isoformat() if hasattr(getattr(self, column.name), "isoformat") else getattr(self, column.name))
            for column in self.__table__.columns
        }
        result["assigned_name"] = self.lead.assigned_user.name if self.lead and self.lead.assigned_user else None
        return result
