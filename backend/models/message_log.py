from datetime import datetime
from extensions import db


class MessageLog(db.Model):
    __tablename__ = "message_logs"

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id"))
    recipient_type = db.Column(db.Text)
    recipient_id = db.Column(db.Integer)
    recipient_name = db.Column(db.Text)
    channel = db.Column(db.Text)
    message_body = db.Column(db.Text)
    status = db.Column(db.Text, default="sent")
    template_used = db.Column(db.Text)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            c.name: (getattr(self, c.name).isoformat() if hasattr(getattr(self, c.name), "isoformat") else getattr(self, c.name))
            for c in self.__table__.columns
        }
