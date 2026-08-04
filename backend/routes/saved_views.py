import json
from flask import Blueprint, jsonify, request
from extensions import db
from models import SavedView
from .utils import current_user, log_activity, permission_required

bp = Blueprint("saved_views", __name__, url_prefix="/api/saved-views")


@bp.get("/")
@permission_required("leads", "view")
def list_saved_views():
    module = request.args.get("module", "leads")
    rows = SavedView.query.filter_by(user_id=current_user().id, module=module).order_by(SavedView.name).all()
    return jsonify([row.to_dict() | {"filters": json.loads(row.filters or "{}")} for row in rows])


@bp.post("/")
@permission_required("leads", "view")
def create_saved_view():
    data = request.get_json() or {}
    view = SavedView(
        user_id=current_user().id,
        module=data.get("module") or "leads",
        name=data.get("name") or "Untitled view",
        filters=json.dumps(data.get("filters") or {}),
        is_default=bool(data.get("is_default")),
    )
    if view.is_default:
        SavedView.query.filter_by(user_id=view.user_id, module=view.module).update({"is_default": False})
    db.session.add(view)
    log_activity(current_user().id, "saved_view_created", view.module, None, view.name)
    db.session.commit()
    return jsonify(view.to_dict() | {"filters": json.loads(view.filters)}), 201


@bp.delete("/<int:id>")
@permission_required("leads", "view")
def delete_saved_view(id):
    view = SavedView.query.filter_by(id=id, user_id=current_user().id).first_or_404()
    db.session.delete(view)
    db.session.commit()
    return jsonify({"message": "Saved view deleted"})
