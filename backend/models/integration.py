from datetime import datetime

from extensions import db


class Integration(db.Model):
    __tablename__ = "integrations"
    __table_args__ = (
        db.UniqueConstraint("agency_id", "type", name="uq_integrations_agency_type"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(40), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    config = db.Column(db.JSON, nullable=False, default=dict)
    agency_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
