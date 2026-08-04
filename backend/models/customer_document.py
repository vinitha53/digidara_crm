from datetime import datetime
from extensions import db


class CustomerDocument(db.Model):
    __tablename__ = "customer_documents"

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    file_name = db.Column(db.Text, nullable=False)
    mime_type = db.Column(db.Text)
    file_size = db.Column(db.Integer, default=0)
    content_base64 = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    customer = db.relationship("Customer", foreign_keys=[customer_id])
    user = db.relationship("User", foreign_keys=[user_id])

    def to_dict(self, include_content=False):
        data = {
            c.name: (getattr(self, c.name).isoformat() if hasattr(getattr(self, c.name), "isoformat") else getattr(self, c.name))
            for c in self.__table__.columns
            if include_content or c.name != "content_base64"
        }
        return data | {"user_name": self.user.name if self.user else None}
