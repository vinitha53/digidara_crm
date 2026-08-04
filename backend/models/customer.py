from datetime import datetime
from extensions import db


class Customer(db.Model):
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=False, unique=True)
    name = db.Column(db.Text, nullable=False)
    phone = db.Column(db.Text, nullable=False)
    email = db.Column(db.Text)
    company = db.Column(db.Text)
    service = db.Column(db.Text, nullable=False)
    value = db.Column(db.Integer, default=0)
    status = db.Column(db.Text, default="active")
    assigned_to = db.Column(db.Integer, db.ForeignKey("users.id"))
    last_contact = db.Column(db.Date)
    notes = db.Column(db.Text)
    rating = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    assigned_user = db.relationship("User", foreign_keys=[assigned_to])

    def to_dict(self):
        return {
            c.name: (getattr(self, c.name).isoformat() if hasattr(getattr(self, c.name), "isoformat") else getattr(self, c.name))
            for c in self.__table__.columns
        } | {"assigned_name": self.assigned_user.name if self.assigned_user else None}
