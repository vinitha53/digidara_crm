import re

from flask import Blueprint, jsonify, request

from extensions import db
from models import (
    AIFollowUpHistory, AIInteraction, ActivityLog, Batch, Campaign, CommunicationSummary,
    Customer, CustomerDocument, CustomerNote, Lead, LoginOtpChallenge, MeetingInvite,
    MessageLog, Notification, Role, RolePermission, SavedView, Task, User, WorkflowRule,
)
from permissions import PERMISSION_PAGES, default_allowed, permission_role, serialize_permissions
from .utils import admin_required, current_user, permission_required, update_model

bp = Blueprint("employees", __name__, url_prefix="/api/employees")


def make_login_id(name, email):
    base = (email or "").split("@")[0] or (name or "")
    base = "".join(ch.lower() for ch in base if ch.isalnum())[:24] or "employee"
    candidate, suffix = base, 2
    while User.query.filter_by(login_id=candidate).first():
        candidate, suffix = f"{base}{suffix}", suffix + 1
    return candidate


def role_key(label):
    key = re.sub(r"[^a-z0-9]+", "_", (label or "").strip().lower()).strip("_")[:30]
    return key


def role_for(value, active_only=True):
    key = permission_role(value)
    query = Role.query.filter_by(key=key)
    if active_only:
        query = query.filter_by(is_active=1)
    return query.first()


def employee_dict(user):
    data = user.to_dict()
    role = role_for(user.role, active_only=False)
    data["role_key"] = role.key if role else permission_role(user.role)
    data["role_label"] = role.label if role else ("Administrator" if user.role == "admin" else "Staff")
    return data


def role_dict(role):
    data = role.to_dict()
    aliases = [role.key] + (["employee"] if role.key == "staff" else [])
    data["user_count"] = User.query.filter(User.role.in_(aliases)).count()
    data["active_user_count"] = User.query.filter(User.role.in_(aliases), User.is_active == 1).count()
    data["permissions"] = serialize_permissions(role.key)
    return data


def save_role_permissions(key, permissions=None, template="staff"):
    template_permissions = serialize_permissions(template if role_for(template) else "staff")
    incoming = permissions if isinstance(permissions, dict) else template_permissions
    actor = current_user()
    for page in PERMISSION_PAGES:
        page_key = page["key"]
        page_actions = incoming.get(page_key) or {}
        view_allowed = key == "admin" or bool(page_actions.get("view", default_allowed(key, page_key, "view")))
        for action in page["actions"]:
            row = RolePermission.query.filter_by(role=key, page_key=page_key, action=action).first()
            if not row:
                row = RolePermission(role=key, page_key=page_key, action=action)
                db.session.add(row)
            requested = bool(page_actions.get(action, default_allowed(key, page_key, action)))
            row.allowed = 1 if key == "admin" or (view_allowed and requested) else 0
            row.updated_by = actor.id if actor else row.updated_by


def valid_role_or_error(value):
    role = role_for(value)
    return role, None if role else (jsonify({"message": "Select an active CRM role."}), 400)


def delete_employee_records(user_id):
    """Physically remove a user while preserving non-personal CRM business records."""
    Lead.query.filter_by(assigned_to=user_id).update({Lead.assigned_to: None}, synchronize_session=False)
    Customer.query.filter_by(assigned_to=user_id).update({Customer.assigned_to: None}, synchronize_session=False)
    Task.query.filter_by(assigned_to=user_id).update({Task.assigned_to: None}, synchronize_session=False)
    Task.query.filter_by(created_by=user_id).update({Task.created_by: None}, synchronize_session=False)
    Task.query.filter_by(related_type="employee", related_id=user_id).update(
        {Task.related_id: None, Task.related_name: "Deleted employee"}, synchronize_session=False,
    )
    Campaign.query.filter_by(created_by=user_id).update({Campaign.created_by: None}, synchronize_session=False)
    WorkflowRule.query.filter_by(created_by=user_id).update({WorkflowRule.created_by: None}, synchronize_session=False)
    CommunicationSummary.query.filter_by(created_by=user_id).update({CommunicationSummary.created_by: None}, synchronize_session=False)
    Batch.query.filter_by(mentor_id=user_id).update({Batch.mentor_id: None}, synchronize_session=False)
    AIFollowUpHistory.query.filter_by(user_id=user_id).update({AIFollowUpHistory.user_id: None}, synchronize_session=False)
    CustomerNote.query.filter_by(user_id=user_id).update({CustomerNote.user_id: None}, synchronize_session=False)
    CustomerDocument.query.filter_by(user_id=user_id).update({CustomerDocument.user_id: None}, synchronize_session=False)
    MeetingInvite.query.filter_by(user_id=user_id).update({MeetingInvite.user_id: None}, synchronize_session=False)
    ActivityLog.query.filter_by(user_id=user_id).update({ActivityLog.user_id: None}, synchronize_session=False)
    ActivityLog.query.filter_by(entity_type="employee", entity_id=user_id).update(
        {ActivityLog.entity_id: None, ActivityLog.entity_name: "Deleted employee", ActivityLog.meta: None},
        synchronize_session=False,
    )
    RolePermission.query.filter_by(updated_by=user_id).update({RolePermission.updated_by: None}, synchronize_session=False)

    MessageLog.query.filter_by(recipient_type="employee", recipient_id=user_id).delete(synchronize_session=False)
    CommunicationSummary.query.filter_by(recipient_type="employee", recipient_id=user_id).delete(synchronize_session=False)
    Notification.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    SavedView.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    AIInteraction.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    LoginOtpChallenge.query.filter_by(user_id=user_id).delete(synchronize_session=False)


@bp.get("/")
@permission_required("employees", "view")
def list_employees():
    rows = User.query.order_by(User.is_active.desc(), User.name).all()
    return jsonify([employee_dict(user) for user in rows])


@bp.get("/roles")
@permission_required("employees", "view")
def list_roles():
    roles = Role.query.order_by(Role.is_system.desc(), Role.is_active.desc(), Role.label).all()
    return jsonify({"roles": [role_dict(role) for role in roles], "pages": PERMISSION_PAGES})


@bp.post("/roles")
@admin_required
def create_role():
    data = request.get_json() or {}
    label = str(data.get("label") or "").strip()
    key = role_key(label)
    if len(label) < 2 or not key:
        return jsonify({"message": "Enter a role name with at least two characters."}), 400
    if key in {"admin", "staff", "employee"} or Role.query.filter_by(key=key).first():
        return jsonify({"message": "A role with this name already exists."}), 409
    role = Role(key=key, label=label[:80], description=str(data.get("description") or "").strip()[:255], is_system=0, is_active=1)
    db.session.add(role)
    db.session.flush()
    save_role_permissions(key, data.get("permissions"), data.get("template") or "staff")
    db.session.commit()
    return jsonify(role_dict(role)), 201


@bp.put("/roles/<string:key>")
@admin_required
def update_role(key):
    role = Role.query.filter_by(key=key).first_or_404()
    data = request.get_json() or {}
    if role.is_system and any(field in data for field in ("label", "description", "is_active")):
        return jsonify({"message": "System role identity cannot be changed."}), 400
    if "is_active" in data and not data["is_active"] and User.query.filter_by(role=key, is_active=1).count():
        return jsonify({"message": "Move active employees to another role before deactivating this role."}), 400
    if not role.is_system:
        if "label" in data and str(data["label"]).strip():
            role.label = str(data["label"]).strip()[:80]
        if "description" in data:
            role.description = str(data["description"] or "").strip()[:255]
        if "is_active" in data:
            role.is_active = 1 if data["is_active"] else 0
    if "permissions" in data:
        save_role_permissions(key, data["permissions"])
    db.session.commit()
    return jsonify(role_dict(role))


@bp.post("/")
@permission_required("employees", "create")
def create_employee():
    data = request.get_json() or {}
    password = data.get("password", "")
    required_fields = ("name", "phone", "email", "branch", "department", "role")
    if any(not str(data.get(field, "")).strip() for field in required_fields) or not password:
        return jsonify({"message": "Please complete all employee fields."}), 400
    if password != data.get("confirm_password", ""):
        return jsonify({"message": "Passwords do not match."}), 400
    if len(password) < 8:
        return jsonify({"message": "Password must contain at least 8 characters."}), 400
    role, error = valid_role_or_error(data.get("role"))
    if error:
        return error
    if current_user().role != "admin" and role.key != "staff":
        return jsonify({"message": "Only an administrator can assign elevated or custom roles."}), 403
    email = data.get("email", "").strip().lower()
    if User.query.filter_by(email=email).first():
        return jsonify({"message": "Email already exists."}), 409
    user = update_model(User(), data, ["name", "phone", "branch", "department", "avatar_color"])
    user.role = role.key
    user.email = email
    user.login_id = make_login_id(user.name, user.email)
    user.avatar_initials = "".join(part[0] for part in user.name.split()[:2]).upper()
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return jsonify(employee_dict(user)), 201


@bp.put("/<int:id>")
@permission_required("employees", "update")
def update(id):
    user = User.query.get_or_404(id)
    data = request.get_json() or {}
    actor = current_user()
    if user.id == actor.id and (data.get("is_active") is False or ("role" in data and permission_role(data["role"]) != permission_role(user.role))):
        return jsonify({"message": "You cannot deactivate or change your own role."}), 400
    if "role" in data:
        role, error = valid_role_or_error(data["role"])
        if error:
            return error
        if actor.role != "admin" and permission_role(role.key) != permission_role(user.role):
            return jsonify({"message": "Only an administrator can change CRM roles."}), 403
        data["role"] = role.key
    if user.role == "admin" and (data.get("is_active") is False or data.get("role", "admin") != "admin"):
        if User.query.filter_by(role="admin", is_active=1).count() <= 1:
            return jsonify({"message": "At least one active administrator is required."}), 400
    update_model(user, data, ["name", "phone", "role", "branch", "department", "avatar_color", "is_active"])
    user.avatar_initials = "".join(part[0] for part in user.name.split()[:2]).upper()
    db.session.commit()
    return jsonify(employee_dict(user))


@bp.delete("/<int:id>")
@permission_required("employees", "delete")
def delete_employee(id):
    user = User.query.get_or_404(id)
    if user.id == current_user().id:
        return jsonify({"message": "You cannot delete your own account."}), 400
    if user.role == "admin" and user.is_active and User.query.filter_by(role="admin", is_active=1).count() <= 1:
        return jsonify({"message": "At least one active administrator is required."}), 400
    employee_name = user.name
    delete_employee_records(user.id)
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": f"{employee_name} was permanently deleted from the database."})
