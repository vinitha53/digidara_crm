from datetime import datetime
from extensions import db


class Campaign(db.Model):
    __tablename__ = "campaigns"

    id = db.Column(db.Integer, primary_key=True)
    agency_id = db.Column(db.Integer, index=True)
    name = db.Column(db.Text, nullable=False)
    channel = db.Column(db.Text, nullable=False, default="WhatsApp")
    audience = db.Column(db.Text, nullable=False, default="All leads")
    message_body = db.Column(db.Text, nullable=False, default="")
    from_name = db.Column(db.Text, default="Digidara Technologies")
    template_name = db.Column(db.Text)
    template_language = db.Column(db.Text)
    template_category = db.Column(db.Text)
    template_snapshot = db.Column(db.JSON)
    variable_mapping = db.Column(db.JSON)
    header_type = db.Column(db.Text)
    media_id = db.Column(db.Text)
    media_filename = db.Column(db.Text)
    audience_type = db.Column(db.Text, default="all")
    audience_filter = db.Column(db.JSON)
    audience_snapshot = db.Column(db.JSON)
    status = db.Column(db.Text, default="draft")
    scheduled_at = db.Column(db.DateTime)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    paused_at = db.Column(db.DateTime)
    cancelled_at = db.Column(db.DateTime)
    sent_at = db.Column(db.DateTime)
    total_count = db.Column(db.Integer, default=0)
    eligible_count = db.Column(db.Integer, default=0)
    queued_count = db.Column(db.Integer, default=0)
    sent_count = db.Column(db.Integer, default=0)
    delivered_count = db.Column(db.Integer, default=0)
    read_count = db.Column(db.Integer, default=0)
    replied_count = db.Column(db.Integer, default=0)
    failed_count = db.Column(db.Integer, default=0)
    skipped_count = db.Column(db.Integer, default=0)
    opted_out_count = db.Column(db.Integer, default=0)
    # Backward-compatible legacy counters. opened_count is no longer populated.
    opened_count = db.Column(db.Integer, default=0)
    reply_count = db.Column(db.Integer, default=0)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    recipients = db.relationship("CampaignRecipient", back_populates="campaign", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            c.name: (getattr(self, c.name).isoformat() if hasattr(getattr(self, c.name), "isoformat") else getattr(self, c.name))
            for c in self.__table__.columns
        }
