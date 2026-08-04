from datetime import datetime
from extensions import db


class CommunicationSummary(db.Model):
    __tablename__ = "communication_summaries"

    id = db.Column(db.Integer, primary_key=True)
    recipient_type = db.Column(db.Text, nullable=False)
    recipient_id = db.Column(db.Integer, nullable=False)
    recipient_name = db.Column(db.Text)
    channel = db.Column(db.Text, default="Mixed")
    summary_text = db.Column(db.Text, nullable=False)
    key_points = db.Column(db.Text)
    sentiment = db.Column(db.Text, default="neutral")
    next_action = db.Column(db.Text)
    message_count = db.Column(db.Integer, default=0)
    model = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            c.name: (getattr(self, c.name).isoformat() if hasattr(getattr(self, c.name), "isoformat") else getattr(self, c.name))
            for c in self.__table__.columns
        }
