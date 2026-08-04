from datetime import datetime
from extensions import db


class MeetingInvite(db.Model):
    __tablename__ = "meeting_invites"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    recipient_name = db.Column(db.Text)
    recipient_phone = db.Column(db.Text)
    recipient_email = db.Column(db.Text)
    channel = db.Column(db.Text, default="WhatsApp")
    status = db.Column(db.Text, default="sent")
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    task = db.relationship("Task", foreign_keys=[task_id])
    user = db.relationship("User", foreign_keys=[user_id])

    def to_dict(self):
        return {
            c.name: (getattr(self, c.name).isoformat() if hasattr(getattr(self, c.name), "isoformat") else getattr(self, c.name))
            for c in self.__table__.columns
        }
