from datetime import datetime
from extensions import db


class RolePermission(db.Model):
    __tablename__ = "role_permissions"

    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.Text, nullable=False)
    page_key = db.Column(db.Text, nullable=False)
    action = db.Column(db.Text, nullable=False)
    allowed = db.Column(db.Integer, nullable=False, default=0)
    updated_by = db.Column(db.Integer)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("role", "page_key", "action", name="uq_role_permissions_scope"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "role": self.role,
            "page_key": self.page_key,
            "action": self.action,
            "allowed": bool(self.allowed),
            "updated_by": self.updated_by,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
