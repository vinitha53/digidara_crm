import json
from flask import Blueprint, jsonify, request
from extensions import db
from models import User, WorkflowRule, WorkflowRuleRun
from .utils import current_user, log_activity, permission_required, update_model

bp = Blueprint("workflows", __name__, url_prefix="/api/workflows")
ALLOWED = ["name", "description", "entity_type", "trigger_type", "trigger_config", "conditions", "actions", "is_active"]


def encode_json(value, fallback):
    if value in (None, ""):
        value = fallback
    return json.dumps(value) if isinstance(value, (dict, list)) else value


def normalize(rule, data):
    update_model(rule, data, ALLOWED)
    rule.entity_type = rule.entity_type or "lead"
    rule.trigger_type = rule.trigger_type or "status_changed"
    rule.trigger_config = encode_json(data.get("trigger_config", rule.trigger_config), {"to_status": "any"})
    rule.conditions = encode_json(data.get("conditions", rule.conditions), {})
    rule.actions = encode_json(data.get("actions", rule.actions), [])
    rule.is_active = 1 if data.get("is_active", rule.is_active if rule.id else 1) else 0
    return rule


@bp.get("/")
@permission_required("workflows", "view")
def list_rules():
    rows = WorkflowRule.query.order_by(WorkflowRule.created_at.desc()).all()
    return jsonify([row.to_dict() for row in rows])


@bp.post("/")
@permission_required("workflows", "manage")
def create_rule():
    data = request.get_json() or {}
    if not data.get("name"):
        return jsonify({"message": "Rule name is required"}), 400
    rule = normalize(WorkflowRule(created_by=current_user().id), data)
    db.session.add(rule)
    db.session.flush()
    log_activity(current_user().id, "workflow_rule_created", "workflow_rule", rule.id, rule.name)
    db.session.commit()
    return jsonify(rule.to_dict()), 201


@bp.put("/<int:id>")
@permission_required("workflows", "manage")
def update_rule(id):
    rule = WorkflowRule.query.get_or_404(id)
    data = request.get_json() or {}
    normalize(rule, data)
    log_activity(current_user().id, "workflow_rule_updated", "workflow_rule", rule.id, rule.name)
    db.session.commit()
    return jsonify(rule.to_dict())


@bp.delete("/<int:id>")
@permission_required("workflows", "manage")
def delete_rule(id):
    rule = WorkflowRule.query.get_or_404(id)
    name = rule.name
    WorkflowRuleRun.query.filter_by(rule_id=id).delete()
    db.session.delete(rule)
    log_activity(current_user().id, "workflow_rule_deleted", "workflow_rule", id, name)
    db.session.commit()
    return jsonify({"message": "Workflow rule deleted"})


@bp.post("/<int:id>/toggle")
@permission_required("workflows", "manage")
def toggle_rule(id):
    rule = WorkflowRule.query.get_or_404(id)
    rule.is_active = 0 if rule.is_active else 1
    log_activity(current_user().id, "workflow_rule_toggled", "workflow_rule", rule.id, rule.name)
    db.session.commit()
    return jsonify(rule.to_dict())


@bp.get("/<int:id>/runs")
@permission_required("workflows", "view")
def rule_runs(id):
    WorkflowRule.query.get_or_404(id)
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    rows = WorkflowRuleRun.query.filter_by(rule_id=id).order_by(WorkflowRuleRun.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({"items": [row.to_dict() for row in rows.items], "total": rows.total, "page": page})


@bp.get("/assignable-users")
@permission_required("workflows", "view")
def assignable_users():
    users = User.query.filter_by(is_active=1).order_by(User.name).all()
    return jsonify([u.to_dict() for u in users])
