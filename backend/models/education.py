from datetime import datetime
from extensions import db


class Course(db.Model):
    __tablename__ = "courses"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    category = db.Column(db.Text, default="course")
    duration = db.Column(db.Text)
    fee = db.Column(db.Integer, default=0)
    status = db.Column(db.Text, default="active")
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            c.name: (getattr(self, c.name).isoformat() if hasattr(getattr(self, c.name), "isoformat") else getattr(self, c.name))
            for c in self.__table__.columns
        }


class Batch(db.Model):
    __tablename__ = "batches"

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"))
    name = db.Column(db.Text, nullable=False)
    mentor_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    schedule = db.Column(db.Text)
    capacity = db.Column(db.Integer, default=0)
    status = db.Column(db.Text, default="planned")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    course = db.relationship("Course", foreign_keys=[course_id])
    mentor = db.relationship("User", foreign_keys=[mentor_id])

    def to_dict(self):
        return {
            c.name: (getattr(self, c.name).isoformat() if hasattr(getattr(self, c.name), "isoformat") else getattr(self, c.name))
            for c in self.__table__.columns
        } | {
            "course_name": self.course.name if self.course else None,
            "mentor_name": self.mentor.name if self.mentor else None,
        }


class Student(db.Model):
    __tablename__ = "students"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Text, nullable=False)
    phone = db.Column(db.Text, nullable=False)
    email = db.Column(db.Text)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"))
    batch_id = db.Column(db.Integer, db.ForeignKey("batches.id"))
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"))
    status = db.Column(db.Text, default="enrolled")
    attendance_percent = db.Column(db.Integer, default=0)
    placement_status = db.Column(db.Text, default="not_started")
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    course = db.relationship("Course", foreign_keys=[course_id])
    batch = db.relationship("Batch", foreign_keys=[batch_id])

    def to_dict(self):
        return {
            c.name: (getattr(self, c.name).isoformat() if hasattr(getattr(self, c.name), "isoformat") else getattr(self, c.name))
            for c in self.__table__.columns
        } | {
            "course_name": self.course.name if self.course else None,
            "batch_name": self.batch.name if self.batch else None,
        }
