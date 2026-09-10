import csv
import hashlib
import hmac
import io
import json
import time
import uuid
from datetime import datetime

from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context
from werkzeug.utils import secure_filename

from extensions import db
from models import Campaign, CampaignRecipient, MessageLog, WhatsAppTemplate
from services.campaign_service import (
    audience_analysis, campaign_query, process_webhook_payload, refresh_campaign_counts,
    required_body_variables, scoped_leads, snapshot_campaign,
)
from services.integration_service import configured_agency_id
from services.whatsapp_service import (
    fetch_approved_templates, provider_message_id, safe_provider_response,
    send_whatsapp_template, upload_whatsapp_media, validate_whatsapp_credentials,
)
from .utils import current_user, log_activity, parse_datetime, permission_required

bp = Blueprint("campaigns", __name__, url_prefix="/api/campaigns")
ALLOWED = {
    "name", "template_name", "template_language", "template_category", "template_snapshot",
    "variable_mapping", "header_type", "media_id", "media_filename", "audience_type",
    "audience_filter", "audience_snapshot", "scheduled_at", "from_name", "message_body",
}
ALLOWED_IMAGE_TYPES = {"image/jpeg": {"jpg", "jpeg"}, "image/png": {"png"}, "image/webp": {"webp"}}


def scoped_campaign(campaign_id):
    return campaign_query(current_user()).filter(Campaign.id == campaign_id).first_or_404()


def filters_from_request():
    values = request.get_json(silent=True) if request.method != "GET" else request.args.to_dict()
    values = values or {}
    nested = values.get("filters") or values.get("audience_filter")
    if isinstance(nested, str):
        try:
            nested = json.loads(nested)
        except ValueError:
            nested = {}
    filters = dict(nested) if isinstance(nested, dict) else {}
    for key in (
        "classification", "status", "source", "service", "destination", "city", "assigned_to",
        "branch", "created_from", "created_to", "search", "phone_availability", "marketing_consent", "opted_out",
    ):
        if values.get(key) not in (None, ""):
            filters[key] = values[key]
    return filters


def template_parts(item):
    components = item.get("components") or []
    header = next((part for part in components if part.get("type") == "HEADER"), {})
    body = next((part for part in components if part.get("type") == "BODY"), {})
    footer = next((part for part in components if part.get("type") == "FOOTER"), {})
    buttons = next((part.get("buttons") for part in components if part.get("type") == "BUTTONS"), []) or []
    return str(header.get("format") or "TEXT").upper(), body.get("text") or "", footer.get("text") or "", buttons


def sync_templates():
    result = fetch_approved_templates(after=request.args.get("after"), limit=request.args.get("limit", 100))
    if not result.get("ok"):
        return None, result
    agency_id = configured_agency_id()
    now = datetime.utcnow()
    synced = []
    paging = result.get("paging") or {}
    if not request.args.get("after") and not paging.get("next"):
        WhatsAppTemplate.query.filter_by(agency_id=agency_id).update({"status": "STALE"}, synchronize_session=False)
    for item in result.get("templates", []):
        meta_id = str(item.get("id") or f"{item.get('name')}:{item.get('language')}")
        row = WhatsAppTemplate.query.filter_by(agency_id=agency_id, meta_template_id=meta_id).first()
        if not row:
            row = WhatsAppTemplate(agency_id=agency_id, meta_template_id=meta_id)
            db.session.add(row)
        header_type, body_text, footer_text, buttons = template_parts(item)
        row.name = str(item.get("name") or "")
        row.language = str(item.get("language") or "en")
        row.category = str(item.get("category") or "")
        row.status = str(item.get("status") or "").upper()
        row.components = item.get("components") or []
        row.header_type = header_type
        row.body_text = body_text
        row.footer_text = footer_text
        row.buttons = buttons
        row.last_synced_at = now
        synced.append(row)
    db.session.commit()
    return synced, result


@bp.get("/")
@permission_required("campaigns", "view")
def list_campaigns():
    rows = campaign_query(current_user()).order_by(Campaign.created_at.desc()).all()
    for campaign in rows:
        refresh_campaign_counts(campaign)
    db.session.commit()
    return jsonify([row.to_dict() for row in rows])


@bp.get("/audience")
@permission_required("campaigns", "view")
def audience_preview():
    try:
        limit = min(max(int(request.args.get("limit", 50)), 1), 200)
    except (TypeError, ValueError):
        limit = 50
    result = audience_analysis(current_user(), filters_from_request(), preview_limit=limit)
    return jsonify({key: value for key, value in result.items() if key not in {"eligible", "excluded"}})


def csv_line(values):
    stream = io.StringIO()
    csv.writer(stream).writerow(values)
    return stream.getvalue()


def lead_export_response(filters, filename="lead-audience.csv"):
    query = scoped_leads(current_user(), filters)

    @stream_with_context
    def rows():
        yield "\ufeff" + csv_line([
            "Name", "Phone", "Email", "Company", "Classification", "Status", "Source", "Service",
            "Destination", "City", "Assigned Staff", "Branch", "Consent", "Opted Out", "Created Date",
        ])
        for lead in query.yield_per(500):
            owner = lead.assigned_user
            yield csv_line([
                lead.name, lead.phone, lead.email, lead.company, lead.tag, lead.status, lead.source, lead.service,
                lead.destination, lead.city, owner.name if owner else "", owner.branch if owner else "",
                "granted" if lead.marketing_opt_in or lead.whatsapp_opt_in else "pending",
                "yes" if lead.opted_out else "no", lead.created_at.isoformat() if lead.created_at else "",
            ])
    log_activity(current_user().id, "campaign_audience_exported", "campaign", meta=json.dumps(filters, default=str)[:1000])
    db.session.commit()
    return Response(rows(), mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@bp.get("/audience/export")
@permission_required("campaigns", "export")
def export_audience():
    return lead_export_response(filters_from_request())


@bp.get("/templates")
@permission_required("campaigns", "view")
def templates():
    query = WhatsAppTemplate.query.filter_by(agency_id=configured_agency_id(), status="APPROVED")
    if request.args.get("category"):
        query = query.filter_by(category=request.args["category"].upper())
    if request.args.get("language"):
        query = query.filter_by(language=request.args["language"])
    search = str(request.args.get("search") or "").strip()
    if search:
        query = query.filter(WhatsAppTemplate.name.ilike(f"%{search}%"))
    rows = query.order_by(WhatsAppTemplate.name, WhatsAppTemplate.language).all()
    return jsonify({
        "items": [row.to_dict() for row in rows], "configuration": validate_whatsapp_credentials(require_waba=False),
        "last_synced_at": max((row.last_synced_at for row in rows), default=None).isoformat() if rows else None,
    })


@bp.post("/templates/refresh")
@permission_required("campaigns", "manage_templates")
def refresh_templates():
    rows, result = sync_templates()
    if rows is None:
        status = int(result.get("status_code") or 502)
        return jsonify({"message": result.get("error") or "Could not synchronize Meta templates", "error_code": result.get("error_code")}), status if 400 <= status < 600 else 502
    log_activity(current_user().id, "whatsapp_templates_refreshed", "campaign", meta=f"approved:{len(rows)}")
    db.session.commit()
    return jsonify({"items": [row.to_dict() for row in rows], "count": len(rows), "paging": result.get("paging") or {}})


@bp.post("/")
@permission_required("campaigns", "create")
def create_campaign():
    data = request.get_json() or {}
    name = str(data.get("name") or "").strip()
    if not name:
        return jsonify({"message": "Campaign name is required"}), 400
    campaign = Campaign(
        agency_id=configured_agency_id(), created_by=current_user().id, name=name,
        channel="WhatsApp", audience=str(data.get("audience") or data.get("audience_type") or "All leads"),
        message_body=str(data.get("message_body") or ""), status="draft",
    )
    for key in ALLOWED:
        if key in data and key != "name":
            setattr(campaign, key, data[key])
    campaign.audience_type = str(campaign.audience_type or "all").lower()
    campaign.audience_filter = campaign.audience_filter or {"classification": campaign.audience_type}
    db.session.add(campaign)
    db.session.flush()
    log_activity(current_user().id, "campaign_created", "campaign", campaign.id, campaign.name)
    db.session.commit()
    return jsonify(campaign.to_dict()), 201


@bp.get("/<int:campaign_id>")
@permission_required("campaigns", "view")
def get_campaign(campaign_id):
    campaign = scoped_campaign(campaign_id)
    refresh_campaign_counts(campaign)
    db.session.commit()
    return jsonify(campaign.to_dict())


@bp.put("/<int:campaign_id>")
@permission_required("campaigns", "update")
def update_campaign(campaign_id):
    campaign = scoped_campaign(campaign_id)
    if campaign.status not in {"draft", "validated", "paused"}:
        return jsonify({"message": "Only draft, validated, or paused campaigns can be edited"}), 409
    data = request.get_json() or {}
    for key in ALLOWED:
        if key in data:
            setattr(campaign, key, data[key])
    if not str(campaign.name or "").strip():
        return jsonify({"message": "Campaign name is required"}), 400
    log_activity(current_user().id, "campaign_updated", "campaign", campaign.id, campaign.name)
    db.session.commit()
    return jsonify(campaign.to_dict())


@bp.delete("/<int:campaign_id>")
@permission_required("campaigns", "update")
def delete_campaign(campaign_id):
    campaign = scoped_campaign(campaign_id)
    if campaign.status not in {"draft", "cancelled", "failed"}:
        return jsonify({"message": "Active or completed campaigns cannot be deleted"}), 409
    db.session.delete(campaign)
    db.session.commit()
    return "", 204


def campaign_analysis(campaign):
    result = audience_analysis(current_user(), campaign.audience_filter or {"classification": campaign.audience_type}, campaign.variable_mapping, campaign.template_snapshot)
    return {key: value for key, value in result.items() if key not in {"eligible", "excluded"}}


@bp.post("/<int:campaign_id>/preview")
@permission_required("campaigns", "view")
def preview_campaign(campaign_id):
    campaign = scoped_campaign(campaign_id)
    return jsonify({"campaign": campaign.to_dict(), "audience": campaign_analysis(campaign)})


def validate_campaign(campaign):
    errors = []
    template = WhatsAppTemplate.query.filter_by(
        agency_id=campaign.agency_id, name=campaign.template_name,
        language=campaign.template_language, status="APPROVED",
    ).first()
    if not template:
        errors.append("Select an approved Meta WhatsApp template")
    else:
        # Meta's cached approved snapshot is authoritative; browser input may not alter it.
        campaign.template_category = template.category
        campaign.template_snapshot = template.to_dict()
        campaign.header_type = template.header_type
        campaign.message_body = template.body_text or ""
        required = {str(value) for value in required_body_variables(campaign.template_snapshot)}
        body_mapping = (campaign.variable_mapping or {}).get("body", campaign.variable_mapping or {})
        supplied = {str(key) for key in body_mapping if str(key).isdigit()} if isinstance(body_mapping, dict) else set()
        if supplied != required:
            errors.append(f"Template requires exactly {len(required)} body variable mapping(s)")
    if campaign.header_type == "IMAGE" and not campaign.media_id:
        errors.append("Upload the required image header")
    analysis = campaign_analysis(campaign)
    if not analysis["eligible_count"]:
        errors.append("The selected audience has no eligible recipients")
    return errors, analysis


@bp.post("/<int:campaign_id>/validate")
@permission_required("campaigns", "update")
def validate(campaign_id):
    campaign = scoped_campaign(campaign_id)
    errors, analysis = validate_campaign(campaign)
    if not errors:
        campaign.status = "validated"
        campaign.audience_snapshot = {key: analysis[key] for key in ("total_count", "eligible_count", "excluded_count", "exclusion_reasons")}
        db.session.commit()
    return jsonify({"valid": not errors, "errors": errors, "audience": analysis}), 200 if not errors else 400


@bp.post("/<int:campaign_id>/media")
@permission_required("campaigns", "update")
def upload_media(campaign_id):
    campaign = scoped_campaign(campaign_id)
    if campaign.header_type != "IMAGE":
        return jsonify({"message": "The selected template does not support an image header"}), 400
    upload = request.files.get("file")
    if not upload or not upload.filename:
        return jsonify({"message": "Choose an image file"}), 400
    filename = secure_filename(upload.filename)
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    allowed_extensions = ALLOWED_IMAGE_TYPES.get(upload.mimetype)
    if not allowed_extensions or extension not in allowed_extensions:
        return jsonify({"message": "Only JPG, PNG, and WEBP images are allowed"}), 400
    content = upload.read(current_app.config["CAMPAIGN_MEDIA_MAX_BYTES"] + 1)
    if len(content) > current_app.config["CAMPAIGN_MEDIA_MAX_BYTES"]:
        return jsonify({"message": "Image exceeds the configured upload size limit"}), 413
    safe_name = f"{uuid.uuid4().hex}.{extension}"
    result = upload_whatsapp_media(io.BytesIO(content), upload.mimetype, safe_name)
    if not result.get("ok") or not result.get("media_id"):
        return jsonify({"message": result.get("error") or "Meta media upload failed"}), 502
    campaign.media_id = result["media_id"]
    campaign.media_filename = safe_name
    db.session.commit()
    return jsonify({"media_id": campaign.media_id, "filename": safe_name})


@bp.post("/<int:campaign_id>/test")
@permission_required("campaigns", "send")
def test_campaign(campaign_id):
    campaign = scoped_campaign(campaign_id)
    data = request.get_json() or {}
    phone = str(data.get("phone") or "").strip()
    params = data.get("body_params") or []
    if not phone:
        return jsonify({"message": "Test recipient phone is required"}), 400
    result = send_whatsapp_template(phone, campaign.template_name, campaign.template_language, params, header_media_id=campaign.media_id if campaign.header_type == "IMAGE" else None)
    tracked = CampaignRecipient(
        agency_id=campaign.agency_id, campaign_id=campaign.id, recipient_name="Test recipient",
        recipient_phone=phone, normalized_phone=f"test:{uuid.uuid4().hex}", rendered_variables={str(i + 1): value for i, value in enumerate(params)},
        status="accepted" if result.get("ok") else "failed", provider_message_id=provider_message_id(result) or None,
        provider_response=safe_provider_response(result), accepted_at=datetime.utcnow() if result.get("ok") else None,
        error_message=None if result.get("ok") else str(result.get("error") or "Test send failed")[:1000], skip_reason="test_recipient",
    )
    db.session.add(tracked)
    db.session.commit()
    return jsonify({"ok": bool(result.get("ok")), "recipient": tracked.to_dict(), "message": result.get("error")}), 200 if result.get("ok") else 502


def launch_response(campaign, scheduled_at=None):
    data = request.get_json() or {}
    if data.get("confirmed") is not True:
        return jsonify({"message": "Confirm contact eligibility and approved-template compliance before launch"}), 400
    if campaign.status in {"queued", "sending", "completed", "sent"}:
        return jsonify({"message": "Campaign has already been launched", "campaign": campaign.to_dict()}), 409
    errors, analysis = validate_campaign(campaign)
    if errors:
        return jsonify({"message": "Campaign validation failed", "errors": errors, "audience": analysis}), 400
    snapshot_campaign(campaign, current_user())
    campaign.scheduled_at = scheduled_at
    campaign.status = "scheduled" if scheduled_at else "queued"
    log_activity(current_user().id, "campaign_scheduled" if scheduled_at else "campaign_launched", "campaign", campaign.id, campaign.name)
    db.session.commit()
    return jsonify(campaign.to_dict())


@bp.post("/<int:campaign_id>/launch")
@permission_required("campaigns", "send")
def launch(campaign_id):
    return launch_response(scoped_campaign(campaign_id))


@bp.post("/<int:campaign_id>/send")
@permission_required("campaigns", "send")
def backward_compatible_send(campaign_id):
    return launch_response(scoped_campaign(campaign_id))


@bp.post("/<int:campaign_id>/schedule")
@permission_required("campaigns", "schedule")
def schedule(campaign_id):
    scheduled_at = parse_datetime(str((request.get_json() or {}).get("scheduled_at") or ""))
    if not scheduled_at or scheduled_at <= datetime.utcnow():
        return jsonify({"message": "Choose a future schedule date and time"}), 400
    return launch_response(scoped_campaign(campaign_id), scheduled_at)


@bp.post("/<int:campaign_id>/pause")
@permission_required("campaigns", "pause")
def pause(campaign_id):
    campaign = scoped_campaign(campaign_id)
    if campaign.status not in {"queued", "sending", "scheduled"}:
        return jsonify({"message": "Only active campaigns can be paused"}), 409
    campaign.status = "paused"
    campaign.paused_at = datetime.utcnow()
    log_activity(current_user().id, "campaign_paused", "campaign", campaign.id, campaign.name)
    db.session.commit()
    return jsonify(campaign.to_dict())


@bp.post("/<int:campaign_id>/resume")
@permission_required("campaigns", "pause")
def resume(campaign_id):
    campaign = scoped_campaign(campaign_id)
    if campaign.status != "paused":
        return jsonify({"message": "Campaign is not paused"}), 409
    campaign.status = "queued"
    campaign.paused_at = None
    log_activity(current_user().id, "campaign_resumed", "campaign", campaign.id, campaign.name)
    db.session.commit()
    return jsonify(campaign.to_dict())


@bp.post("/<int:campaign_id>/cancel")
@permission_required("campaigns", "cancel")
def cancel(campaign_id):
    campaign = scoped_campaign(campaign_id)
    if campaign.status in {"completed", "sent", "cancelled"}:
        return jsonify({"message": "Campaign is already final"}), 409
    CampaignRecipient.query.filter_by(campaign_id=campaign.id, status="queued").update({"status": "cancelled", "skip_reason": "campaign_cancelled"})
    campaign.status = "cancelled"
    campaign.cancelled_at = datetime.utcnow()
    refresh_campaign_counts(campaign)
    log_activity(current_user().id, "campaign_cancelled", "campaign", campaign.id, campaign.name)
    db.session.commit()
    return jsonify(campaign.to_dict())


@bp.post("/<int:campaign_id>/retry")
@permission_required("campaigns", "send")
def retry_failed(campaign_id):
    campaign = scoped_campaign(campaign_id)
    if campaign.status in {"sending", "queued", "scheduled"}:
        return jsonify({"message": "Wait for the active campaign run to finish or pause it first"}), 409
    rows = CampaignRecipient.query.filter_by(campaign_id=campaign.id, status="failed").filter(
        CampaignRecipient.provider_message_id.is_(None),
        db.or_(CampaignRecipient.error_code.is_(None), CampaignRecipient.error_code != "send_state_unknown"),
    ).all()
    now = datetime.utcnow()
    for row in rows:
        row.status = "queued"
        row.queued_at = now
        row.next_retry_at = None
        row.error_code = None
        row.error_message = None
    if rows:
        campaign.status = "queued"
        campaign.completed_at = None
    refresh_campaign_counts(campaign)
    log_activity(current_user().id, "campaign_failed_recipients_retried", "campaign", campaign.id, campaign.name, f"recipients:{len(rows)}")
    db.session.commit()
    return jsonify({"retried": len(rows), "campaign": campaign.to_dict()})


@bp.get("/<int:campaign_id>/stats")
@permission_required("campaigns", "view")
def stats(campaign_id):
    campaign = scoped_campaign(campaign_id)
    refresh_campaign_counts(campaign)
    db.session.commit()
    data = campaign.to_dict()
    data["read_rate"] = round(campaign.read_count / max(campaign.sent_count, 1) * 100, 1)
    data["reply_rate"] = round(campaign.replied_count / max(campaign.sent_count, 1) * 100, 1)
    data.pop("opened_count", None)
    return jsonify(data)


@bp.get("/<int:campaign_id>/recipients")
@permission_required("campaigns", "view")
def recipients(campaign_id):
    campaign = scoped_campaign(campaign_id)
    query = CampaignRecipient.query.filter_by(campaign_id=campaign.id)
    if request.args.get("status"):
        query = query.filter_by(status=request.args["status"])
    search = str(request.args.get("search") or "").strip()
    if search:
        query = query.filter(db.or_(CampaignRecipient.recipient_name.ilike(f"%{search}%"), CampaignRecipient.recipient_phone.ilike(f"%{search}%")))
    page = max(int(request.args.get("page", 1)), 1)
    per_page = min(max(int(request.args.get("per_page", 50)), 1), 200)
    pagination = query.order_by(CampaignRecipient.id).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({"items": [row.to_dict() for row in pagination.items], "total": pagination.total, "page": page, "pages": pagination.pages})


@bp.get("/<int:campaign_id>/replies")
@permission_required("campaigns", "view")
def replies(campaign_id):
    campaign = scoped_campaign(campaign_id)
    rows = CampaignRecipient.query.filter_by(campaign_id=campaign.id).filter(CampaignRecipient.reply_count > 0).order_by(CampaignRecipient.last_reply_at.desc()).all()
    return jsonify([row.to_dict() for row in rows])


@bp.get("/<int:campaign_id>/export")
@permission_required("campaigns", "export")
def export_campaign(campaign_id):
    campaign = scoped_campaign(campaign_id)

    @stream_with_context
    def rows():
        yield "\ufeff" + csv_line(["Lead", "Phone", "Status", "Skip Reason", "Error Code", "Error Message", "Sent At", "Delivered At", "Read At", "Reply", "Reply At"])
        for row in CampaignRecipient.query.filter_by(campaign_id=campaign.id).order_by(CampaignRecipient.id).yield_per(500):
            yield csv_line([row.recipient_name, row.recipient_phone, row.status, row.skip_reason, row.error_code, row.error_message, row.sent_at, row.delivered_at, row.read_at, row.last_reply_text, row.last_reply_at])
    log_activity(current_user().id, "campaign_results_exported", "campaign", campaign.id, campaign.name)
    db.session.commit()
    return Response(rows(), mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="campaign-{campaign.id}-results.csv"'})


def verify_internal_webhook():
    secret = current_app.config.get("CRM_INTEGRATION_SIGNING_SECRET") or ""
    timestamp = request.headers.get("X-CRM-Timestamp", "")
    try:
        valid_time = abs(int(time.time()) - int(timestamp)) <= 300
    except ValueError:
        valid_time = False
    expected = hmac.new(secret.encode(), timestamp.encode() + b"." + request.get_data(), hashlib.sha256).hexdigest() if secret else ""
    return valid_time and bool(secret) and hmac.compare_digest(request.headers.get("X-CRM-Signature", ""), expected)


@bp.post("/webhook-events")
def webhook_events():
    if not verify_internal_webhook():
        return jsonify({"message": "Invalid webhook forward signature"}), 401
    return jsonify(process_webhook_payload(request.get_json(silent=True) or {}))
