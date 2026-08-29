from datetime import datetime
from extensions import db


class Lead(db.Model):
    __tablename__ = "leads"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    phone = db.Column(db.Text, nullable=False)
    email = db.Column(db.Text)
    company = db.Column(db.Text)
    service = db.Column(db.Text, nullable=False)
    lead_category = db.Column(db.Text, default="course")
    qualification = db.Column(db.Text)
    program_duration = db.Column(db.Text)
    course_name = db.Column(db.Text)
    internship_name = db.Column(db.Text)
    business_name = db.Column(db.Text)
    business_requirement = db.Column(db.Text)
    source = db.Column(db.Text, default="website")
    tag = db.Column(db.Text, default="new")
    status = db.Column(db.Text, default="new")
    deal_value = db.Column(db.Integer, default=0)
    probability = db.Column(db.Integer, default=10)
    expected_close_date = db.Column(db.Date)
    lost_reason = db.Column(db.Text)
    lost_reason_detail = db.Column(db.Text)
    assigned_to = db.Column(db.Integer, db.ForeignKey("users.id"))
    notes = db.Column(db.Text)
    ai_score = db.Column(db.Integer)
    ai_reason = db.Column(db.Text)
    ai_score_factors = db.Column(db.Text)
    ai_scored_at = db.Column(db.DateTime)
    ai_next_best_action = db.Column(db.Text)
    city = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_contacted = db.Column(db.DateTime)
    ai_followup_enabled = db.Column(db.Boolean, default=True)
    ai_followup_paused_reason = db.Column(db.Text)
    ai_preferred_channel = db.Column(db.Text)
    ai_last_followup_at = db.Column(db.DateTime)
    ai_next_followup_at = db.Column(db.DateTime)
    ai_followup_count = db.Column(db.Integer, default=0)
    ai_engagement_score = db.Column(db.Integer, default=0)
    ai_followup_outcome = db.Column(db.Text)
    source_system = db.Column(db.Text)
    external_id = db.Column(db.Text)
    external_created_at = db.Column(db.DateTime)
    assigned_user = db.relationship("User", foreign_keys=[assigned_to])

    def to_dict(self):
        return {
            c.name: (getattr(self, c.name).isoformat() if hasattr(getattr(self, c.name), "isoformat") else getattr(self, c.name))
            for c in self.__table__.columns
        } | {"assigned_name": self.assigned_user.name if self.assigned_user else None}
