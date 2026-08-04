import json
from extensions import db
from models import MessageLog, Notification, User, WorkflowRule, WorkflowRuleRun
from routes.utils import log_activity
from services.email_service import send_email
from services.whatsapp_service import send_whatsapp


def load_json(value, fallback):
    if not value:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def message_status(result):
    if result.get("ok"):
        return "sent"
    if result.get("skipped"):
        return "skipped"
    return "failed"


def render_template(template, lead):
    values = lead.to_dict()
    text = template or ""
    for key, value in values.items():
        text = text.replace("{" + key + "}", "" if value is None else str(value))
    return text


def trigger_matches(rule, old_status, new_status):
    config = load_json(rule.trigger_config, {})
    to_status = config.get("to_status", "any")
    return old_status != new_status and (to_status in ("", "any", None) or to_status == new_status)


def conditions_match(lead, conditions):
    for field, expected in (conditions or {}).items():
        actual = getattr(lead, field, None)
        if isinstance(expected, str) and expected.startswith("contains:"):
            needle = expected.split(":", 1)[1].lower()
            if needle not in str(actual or "").lower():
                return False
        elif str(actual or "") != str(expected):
            return False
    return True


def notification_user(action, lead):
    target = action.get("target", "assignee")
    if target == "specific_user":
        return User.query.get(action.get("user_id"))
    if lead.assigned_to:
        return User.query.get(lead.assigned_to)
    return None


def execute_action(action, lead, actor_user):
    action_type = action.get("type")
    if action_type == "assign_to_user":
        user = User.query.get(action.get("user_id"))
        if not user or not user.is_active:
            raise ValueError("Assign action user_id is invalid")
        lead.assigned_to = user.id
        return f"Assigned to {user.name}"

    if action_type == "create_notification":
        user = notification_user(action, lead)
        if not user:
            raise ValueError("Notification target user is invalid")
        title = render_template(action.get("title") or "Workflow notification", lead)
        body = render_template(action.get("body") or f"Lead {lead.name} matched a workflow rule.", lead)
        db.session.add(Notification(user_id=user.id, type="workflow", title=title, body=body))
        return f"Notification created for {user.name}"

    if action_type == "send_whatsapp":
        body = render_template(action.get("template") or "", lead)
        result = send_whatsapp(lead.phone, body)
        db.session.add(MessageLog(
            recipient_type="lead",
            recipient_id=lead.id,
            recipient_name=lead.name,
            channel="WhatsApp",
            message_body=body,
            template_used="Workflow automation",
            status=message_status(result),
        ))
        if not result.get("ok") and not result.get("skipped"):
            raise ValueError(result.get("error") or "WhatsApp send failed")
        return f"WhatsApp {message_status(result)}"

    if action_type == "send_email":
        subject = render_template(action.get("subject") or "Digidara CRM update", lead)
        body = render_template(action.get("template") or "", lead)
        result = send_email(lead.email, subject, f"<p>{body}</p>")
        db.session.add(MessageLog(
            recipient_type="lead",
            recipient_id=lead.id,
            recipient_name=lead.name,
            channel="Email",
            message_body=body,
            template_used="Workflow automation",
            status=message_status(result),
        ))
        if not result.get("ok") and not result.get("skipped"):
            raise ValueError(result.get("error") or "Email send failed")
        return f"Email {message_status(result)}"

    raise ValueError(f"Unsupported workflow action: {action_type}")


def record_run(rule, lead, status, detail):
    db.session.add(WorkflowRuleRun(
        rule_id=rule.id,
        entity_type="lead",
        entity_id=lead.id,
        status=status,
        detail=detail,
    ))


def run_lead_workflows(lead, old_status, new_status, actor_user):
    rules = WorkflowRule.query.filter_by(
        entity_type="lead",
        trigger_type="status_changed",
        is_active=1,
    ).all()
    matching = [rule for rule in rules if trigger_matches(rule, old_status, new_status)]
    if not matching:
        return

    for rule in matching:
        try:
            conditions = load_json(rule.conditions, {})
            if not conditions_match(lead, conditions):
                record_run(rule, lead, "skipped", "Conditions did not match")
                continue
            details = []
            for action in load_json(rule.actions, []):
                details.append(execute_action(action, lead, actor_user))
            detail = "; ".join(details) or "No actions configured"
            record_run(rule, lead, "success", detail)
            log_activity(
                actor_user.id if actor_user else None,
                "workflow_rule_executed",
                "lead",
                lead.id,
                lead.name,
                json.dumps({"rule_id": rule.id, "rule_name": rule.name, "detail": detail}),
            )
        except Exception as exc:
            record_run(rule, lead, "error", str(exc))
