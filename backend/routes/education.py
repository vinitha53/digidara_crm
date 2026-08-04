from flask import Blueprint, jsonify, request
from extensions import db
from models import Batch, Course, Student, User
from .utils import current_user, log_activity, permission_required, parse_date, update_model

bp = Blueprint("education", __name__, url_prefix="/api/education")
COURSE_ALLOWED = ["name", "category", "duration", "fee", "status", "description"]
BATCH_ALLOWED = ["course_id", "name", "mentor_id", "schedule", "capacity", "status"]
STUDENT_ALLOWED = ["name", "phone", "email", "course_id", "batch_id", "lead_id", "status", "attendance_percent", "placement_status", "notes"]


def clean_ids(model, fields):
    for field in fields:
        if getattr(model, field) in ("", 0, "0"):
            setattr(model, field, None)


@bp.get("/courses")
@permission_required("education", "view")
def courses():
    return jsonify([row.to_dict() for row in Course.query.order_by(Course.name).all()])


@bp.post("/courses")
@permission_required("education", "manage")
def create_course():
    course = update_model(Course(), request.get_json() or {}, COURSE_ALLOWED)
    db.session.add(course)
    log_activity(current_user().id, "course_created", "course", None, course.name)
    db.session.commit()
    return jsonify(course.to_dict()), 201


@bp.get("/batches")
@permission_required("education", "view")
def batches():
    return jsonify([row.to_dict() for row in Batch.query.order_by(Batch.start_date.is_(None), Batch.start_date.desc()).all()])


@bp.post("/batches")
@permission_required("education", "manage")
def create_batch():
    data = request.get_json() or {}
    batch = update_model(Batch(), data, BATCH_ALLOWED)
    clean_ids(batch, ["course_id", "mentor_id"])
    for key in ("start_date", "end_date"):
        if data.get(key):
            setattr(batch, key, parse_date(data[key]))
    db.session.add(batch)
    log_activity(current_user().id, "batch_created", "batch", None, batch.name)
    db.session.commit()
    return jsonify(batch.to_dict()), 201


@bp.get("/students")
@permission_required("education", "view")
def students():
    return jsonify([row.to_dict() for row in Student.query.order_by(Student.created_at.desc()).all()])


@bp.post("/students")
@permission_required("education", "manage")
def create_student():
    student = update_model(Student(), request.get_json() or {}, STUDENT_ALLOWED)
    clean_ids(student, ["course_id", "batch_id", "lead_id"])
    db.session.add(student)
    log_activity(current_user().id, "student_created", "student", None, student.name)
    db.session.commit()
    return jsonify(student.to_dict()), 201


@bp.get("/mentors")
@permission_required("education", "view")
def mentors():
    return jsonify([user.to_dict() for user in User.query.filter_by(is_active=1).order_by(User.name).all()])
