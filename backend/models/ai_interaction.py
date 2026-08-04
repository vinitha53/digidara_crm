import json
from datetime import datetime
from extensions import db


class AIInteraction(db.Model):
    __tablename__ = "ai_interactions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    conversation_id = db.Column(db.String(64), index=True)
    conversation_title = db.Column(db.String(160))
    prompt = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=False)
    intent = db.Column(db.Text, default="copilot")
    model = db.Column(db.Text)
    status = db.Column(db.Text, default="success")
    sources = db.Column(db.Text)
    response_format = db.Column(db.Text, default="summary")
    response_data = db.Column(db.Text)
    row_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship("User", foreign_keys=[user_id])

    def to_dict(self):
        data = {
            c.name: (getattr(self, c.name).isoformat() if hasattr(getattr(self, c.name), "isoformat") else getattr(self, c.name))
            for c in self.__table__.columns
        } | {"user_name": self.user.name if self.user else None}
        try:
            data["structured"] = json.loads(self.response_data) if self.response_data else None
        except (TypeError, ValueError):
            data["structured"] = None
        data.pop("response_data", None)
        return data
