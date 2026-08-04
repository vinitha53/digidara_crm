from datetime import datetime
from extensions import db


class AIFollowUpHistory(db.Model):
    __tablename__ = "ai_followup_history"

    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    channel = db.Column(db.Text, default="WhatsApp")
    message_type = db.Column(db.Text, default="follow_up")
    generated_message = db.Column(db.Text)
    edited_message = db.Column(db.Text)
    status = db.Column(db.Text, default="generated")
    delivery_status = db.Column(db.Text, default="pending")
    skip_reason = db.Column(db.Text)
    outcome = db.Column(db.Text)
    scheduled_for = db.Column(db.DateTime)
    sent_at = db.Column(db.DateTime)
    idempotency_key = db.Column(db.Text, nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    lead = db.relationship("Lead", foreign_keys=[lead_id])
    user = db.relationship("User", foreign_keys=[user_id])

    def to_dict(self):
        return {
            c.name: (getattr(self, c.name).isoformat() if hasattr(getattr(self, c.name), "isoformat") else getattr(self, c.name))
            for c in self.__table__.columns
        } | {"user_name": self.user.name if self.user else None}


class AIFollowUpPromptLog(db.Model):
    __tablename__ = "ai_followup_prompt_logs"

    id = db.Column(db.Integer, primary_key=True)
    followup_id = db.Column(db.Integer, db.ForeignKey("ai_followup_history.id"))
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=False)
    model = db.Column(db.Text)
    prompt = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text)
    status = db.Column(db.Text, default="success")
    error = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    followup = db.relationship("AIFollowUpHistory", foreign_keys=[followup_id])

    def to_dict(self):
        return {
            c.name: (getattr(self, c.name).isoformat() if hasattr(getattr(self, c.name), "isoformat") else getattr(self, c.name))
            for c in self.__table__.columns
        }
