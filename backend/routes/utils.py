from datetime import date, datetime
from functools import wraps
from flask import jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required
from extensions import db
from models import ActivityLog, User
from permissions import has_permission


def current_user():
    identity = get_jwt_identity()
    return User.query.get(int(identity)) if identity else None


def login_required(fn):
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user or not user.is_active:
            return jsonify({"message": "Unauthorized"}), 401
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user or not user.is_active:
            return jsonify({"message": "Unauthorized"}), 401
        if user.role != "admin":
            return jsonify({"message": "Admin access required"}), 403
        return fn(*args, **kwargs)
    return wrapper


def permission_required(page_key, action="view"):
    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user or not user.is_active:
                return jsonify({"message": "Unauthorized"}), 401
            if not has_permission(user, page_key, action):
                return jsonify({"message": "Permission denied"}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return date.fromisoformat(value[:10])


def parse_datetime(value):
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def update_model(model, data, allowed):
    for key in allowed:
        if key in data:
            setattr(model, key, data[key])
    return model


def log_activity(user_id, action, entity_type=None, entity_id=None, entity_name=None, meta=None):
    db.session.add(ActivityLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=entity_name,
        meta=meta,
    ))
