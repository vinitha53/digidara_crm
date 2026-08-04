from datetime import datetime
from extensions import db


class Campaign(db.Model):
    __tablename__ = "campaigns"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    channel = db.Column(db.Text, nullable=False)
    audience = db.Column(db.Text, nullable=False)
    message_body = db.Column(db.Text, nullable=False)
    from_name = db.Column(db.Text, default="Digidara Technologies")
    status = db.Column(db.Text, default="draft")
    scheduled_at = db.Column(db.DateTime)
    sent_at = db.Column(db.DateTime)
    sent_count = db.Column(db.Integer, default=0)
    opened_count = db.Column(db.Integer, default=0)
    reply_count = db.Column(db.Integer, default=0)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            c.name: (getattr(self, c.name).isoformat() if hasattr(getattr(self, c.name), "isoformat") else getattr(self, c.name))
            for c in self.__table__.columns
        }
