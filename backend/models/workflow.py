from datetime import datetime
from extensions import db


class WorkflowRule(db.Model):
    __tablename__ = "workflow_rules"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text)
    entity_type = db.Column(db.Text, nullable=False, default="lead")
    trigger_type = db.Column(db.Text, nullable=False, default="status_changed")
    trigger_config = db.Column(db.Text)
    conditions = db.Column(db.Text)
    actions = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Integer, default=1)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    creator = db.relationship("User", foreign_keys=[created_by])

    def to_dict(self):
        return {
            c.name: (getattr(self, c.name).isoformat() if hasattr(getattr(self, c.name), "isoformat") else getattr(self, c.name))
            for c in self.__table__.columns
        } | {
            "is_active": bool(self.is_active),
            "creator_name": self.creator.name if self.creator else None,
        }


class WorkflowRuleRun(db.Model):
    __tablename__ = "workflow_rule_runs"

    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey("workflow_rules.id"), nullable=False)
    entity_type = db.Column(db.Text, nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)
    status = db.Column(db.Text, nullable=False, default="success")
    detail = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    rule = db.relationship("WorkflowRule", foreign_keys=[rule_id])

    def to_dict(self):
        return {
            c.name: (getattr(self, c.name).isoformat() if hasattr(getattr(self, c.name), "isoformat") else getattr(self, c.name))
            for c in self.__table__.columns
        } | {"rule_name": self.rule.name if self.rule else None}
