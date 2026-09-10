from datetime import datetime

from extensions import db


class WhatsAppTemplate(db.Model):
    __tablename__ = "whatsapp_templates"
    __table_args__ = (
        db.UniqueConstraint("agency_id", "meta_template_id", name="uq_whatsapp_template_agency_meta"),
    )

    id = db.Column(db.Integer, primary_key=True)
    agency_id = db.Column(db.Integer, index=True)
    meta_template_id = db.Column(db.String(190), nullable=False)
    name = db.Column(db.String(190), nullable=False, index=True)
    language = db.Column(db.String(40), nullable=False)
    category = db.Column(db.String(40))
    status = db.Column(db.String(40), nullable=False, index=True)
    components = db.Column(db.JSON, nullable=False, default=list)
    header_type = db.Column(db.String(40))
    body_text = db.Column(db.Text)
    footer_text = db.Column(db.Text)
    buttons = db.Column(db.JSON)
    last_synced_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            column.name: (getattr(self, column.name).isoformat() if hasattr(getattr(self, column.name), "isoformat") else getattr(self, column.name))
            for column in self.__table__.columns
        }
