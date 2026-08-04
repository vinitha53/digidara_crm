from datetime import datetime
from extensions import db


class Task(db.Model):
    __tablename__ = "tasks"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.Text, nullable=False)
    notes = db.Column(db.Text)
    related_type = db.Column(db.Text)
    related_id = db.Column(db.Integer)
    related_name = db.Column(db.Text)
    due_date = db.Column(db.Date)
    reminder_at = db.Column(db.DateTime)
    recurrence_rule = db.Column(db.Text)
    recurrence_parent_id = db.Column(db.Integer, db.ForeignKey("tasks.id"))
    recurrence_next_due = db.Column(db.Date)
    reminder_sent_at = db.Column(db.DateTime)
    meeting_invite_sent_at = db.Column(db.DateTime)
    dependency_task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"))
    meeting_start = db.Column(db.DateTime)
    meeting_end = db.Column(db.DateTime)
    meeting_location = db.Column(db.Text)
    assigned_to = db.Column(db.Integer, db.ForeignKey("users.id"))
    priority = db.Column(db.Text, default="Medium")
    status = db.Column(db.Text, default="pending")
    completed_at = db.Column(db.DateTime)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    assigned_user = db.relationship("User", foreign_keys=[assigned_to])
    creator_user = db.relationship("User", foreign_keys=[created_by])
    dependency_task = db.relationship("Task", remote_side=[id], foreign_keys=[dependency_task_id])
    recurrence_parent = db.relationship("Task", remote_side=[id], foreign_keys=[recurrence_parent_id])

    def to_dict(self):
        return {
            c.name: (getattr(self, c.name).isoformat() if hasattr(getattr(self, c.name), "isoformat") else getattr(self, c.name))
            for c in self.__table__.columns
        } | {
            "assigned_name": self.assigned_user.name if self.assigned_user else None,
            "created_by_name": self.creator_user.name if self.creator_user else None,
            "dependency_title": self.dependency_task.title if self.dependency_task else None,
        }
