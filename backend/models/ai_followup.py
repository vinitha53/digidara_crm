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
    final_message = db.Column(db.Text)
    sequence_step = db.Column(db.Integer)
    temperature_snapshot = db.Column(db.Text)
    recipient_phone = db.Column(db.Text)
    original_phone = db.Column(db.Text)
    template_id = db.Column(db.Integer, db.ForeignKey("ai_followup_templates.id"))
    template_text = db.Column(db.Text)
    status = db.Column(db.Text, default="generated")
    delivery_status = db.Column(db.Text, default="pending")
    skip_reason = db.Column(db.Text)
    outcome = db.Column(db.Text)
    scheduled_for = db.Column(db.DateTime)
    sent_at = db.Column(db.DateTime)
    generated_at = db.Column(db.DateTime)
    stopped_at = db.Column(db.DateTime)
    stopped_reason = db.Column(db.Text)
    provider_message_id = db.Column(db.Text)
    provider_status = db.Column(db.Text)
    provider_response = db.Column(db.Text)
    provider_error = db.Column(db.Text)
    automation_mode = db.Column(db.Text, default="automatic")
    response_received_at = db.Column(db.DateTime)
    claimed_at = db.Column(db.DateTime)
    idempotency_key = db.Column(db.Text, nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    lead = db.relationship("Lead", foreign_keys=[lead_id])
    user = db.relationship("User", foreign_keys=[user_id])

    def to_dict(self):
        return {
            c.name: (getattr(self, c.name).isoformat() if hasattr(getattr(self, c.name), "isoformat") else getattr(self, c.name))
            for c in self.__table__.columns
        } | {
            "user_name": self.user.name if self.user else None,
            "lead_name": self.lead.name if self.lead else None,
            "lead_phone": self.lead.phone if self.lead else None,
            "lead_temperature": self.lead.tag if self.lead else None,
            "lead_status": self.lead.status if self.lead else None,
            "owner_name": self.lead.assigned_user.name if self.lead and self.lead.assigned_user else None,
        }


class AIFollowUpTemplate(db.Model):
    __tablename__ = "ai_followup_templates"
    __table_args__ = (db.UniqueConstraint("temperature", "sequence_step", name="uq_ai_followup_template_step"),)

    id = db.Column(db.Integer, primary_key=True)
    temperature = db.Column(db.Text, nullable=False)
    sequence_step = db.Column(db.Integer, nullable=False)
    template_body = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    description = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            c.name: (getattr(self, c.name).isoformat() if hasattr(getattr(self, c.name), "isoformat") else getattr(self, c.name))
            for c in self.__table__.columns
        }


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
