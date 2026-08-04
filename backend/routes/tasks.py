from datetime import date, datetime, timedelta
from flask import Blueprint, jsonify, request
from extensions import db
from models import MeetingInvite, MessageLog, Notification, Task, User
from permissions import has_permission
from services.email_service import send_email
from services.whatsapp_service import send_whatsapp
from .utils import current_user, log_activity, permission_required, parse_date, parse_datetime, update_model

bp = Blueprint("tasks", __name__, url_prefix="/api/tasks")
ALLOWED = [
    "title", "notes", "related_type", "related_id", "related_name", "assigned_to",
    "priority", "status", "recurrence_rule", "dependency_task_id", "meeting_location"
]
RECURRENCE_DAYS = {"daily": 1, "weekly": 7}


def scoped():
    user = current_user()
    q = Task.query
    if has_permission(user, "tasks", "assign"):
        return q
    return q.filter(Task.assigned_to == user.id)


def message_status(result):
    if result.get("ok"):
        return "sent"
    if result.get("skipped"):
        return "skipped"
    return "failed"


def recurrence_delta(rule):
    if rule in RECURRENCE_DAYS:
        return timedelta(days=RECURRENCE_DAYS[rule])
    if rule == "monthly":
        return timedelta(days=30)
    return None


def shift_datetime(value, delta):
    return value + delta if value and delta else None


def task_reminder_message(task, assignee):
    due = task.due_date.isoformat() if task.due_date else "No due date"
    meeting = f" Meeting: {task.meeting_start.isoformat()} at {task.meeting_location or 'TBD'}." if task.meeting_start else ""
    return f"Hi {assignee.name}, reminder for task: {task.title}. Due: {due}. Priority: {task.priority}.{meeting}"


def meeting_invite_message(task, assignee):
    start = task.meeting_start.isoformat(sep=" ", timespec="minutes") if task.meeting_start else "Not scheduled"
    end = f" to {task.meeting_end.isoformat(sep=' ', timespec='minutes')}" if task.meeting_end else ""
    return f"Hi {assignee.name}, meeting invite: {task.title}. Time: {start}{end}. Location: {task.meeting_location or 'TBD'}. Notes: {task.notes or '-'}"


def task_assignment_message(task, assignee, actor):
    due = task.due_date.isoformat() if task.due_date else "No due date"
    related = f" Related to: {task.related_name}." if task.related_name else ""
    notes = f" Notes: {task.notes}" if task.notes else ""
    return f"Hi {assignee.name}, {actor.name} assigned you a task: {task.title}. Due: {due}. Priority: {task.priority}.{related}{notes}"


def notify_assignment(task, actor):
    assignee = task.assigned_user or User.query.get(task.assigned_to)
    if not assignee:
        return
    due = task.due_date.isoformat() if task.due_date else "No due date"
    body = f"{actor.name} assigned you: {task.title}. Due: {due}. Priority: {task.priority}."
    db.session.add(Notification(
        user_id=assignee.id,
        type="task_assigned",
        title="Task assigned to you",
        body=body,
    ))


def send_task_reminder(task):
    assignee = task.assigned_user or User.query.get(task.assigned_to)
    if not assignee:
        return False
    body = task_reminder_message(task, assignee)
    db.session.add(Notification(user_id=assignee.id, type="task_reminder", title="Task reminder", body=body))
    result = send_whatsapp(assignee.phone, body)
    db.session.add(MessageLog(
        recipient_type="employee",
        recipient_id=assignee.id,
        recipient_name=assignee.name,
        channel="WhatsApp",
        message_body=body,
        template_used="Task reminder",
        status=message_status(result),
    ))
    task.reminder_sent_at = datetime.utcnow()
    return True


def send_meeting_invite(task):
    assignee = task.assigned_user or User.query.get(task.assigned_to)
    if not assignee or not task.meeting_start:
        return None
    body = meeting_invite_message(task, assignee)
    whatsapp_result = send_whatsapp(assignee.phone, body)
    email_result = send_email(assignee.email, f"Meeting invite - {task.title}", f"<p>{body}</p>")
    status = "sent" if whatsapp_result.get("ok") or email_result.get("ok") else "skipped" if whatsapp_result.get("skipped") and email_result.get("skipped") else "failed"
    db.session.add(Notification(user_id=assignee.id, type="meeting_invite", title="Meeting invite", body=body))
    db.session.add(MessageLog(
        recipient_type="employee",
        recipient_id=assignee.id,
        recipient_name=assignee.name,
        channel="Both",
        message_body=body,
        template_used="Meeting invite",
        status=status,
    ))
    invite = MeetingInvite(
        task_id=task.id,
        user_id=assignee.id,
        recipient_name=assignee.name,
        recipient_phone=assignee.phone,
        recipient_email=assignee.email,
        channel="Both",
        status=status,
    )
    db.session.add(invite)
    task.meeting_invite_sent_at = datetime.utcnow()
    return invite


def create_next_recurrence(task):
    delta = recurrence_delta(task.recurrence_rule)
    if not delta or not task.due_date:
        return None
    next_due = task.due_date + delta
    existing = Task.query.filter_by(recurrence_parent_id=task.id, due_date=next_due).first()
    if existing:
        return existing
    next_task = Task(
        title=task.title,
        notes=task.notes,
        related_type=task.related_type,
        related_id=task.related_id,
        related_name=task.related_name,
        due_date=next_due,
        reminder_at=shift_datetime(task.reminder_at, delta),
        recurrence_rule=task.recurrence_rule,
        recurrence_parent_id=task.id,
        recurrence_next_due=next_due + delta,
        dependency_task_id=task.dependency_task_id,
        meeting_start=shift_datetime(task.meeting_start, delta),
        meeting_end=shift_datetime(task.meeting_end, delta),
        meeting_location=task.meeting_location,
        assigned_to=task.assigned_to,
        priority=task.priority,
        status="pending",
        created_by=current_user().id,
    )
    task.recurrence_next_due = next_due
    db.session.add(next_task)
    db.session.flush()
    notify_assignment(next_task, current_user())
    return next_task
    whatsapp_body = task_assignment_message(task, assignee, actor)
    result = send_whatsapp(assignee.phone, whatsapp_body)
    db.session.add(MessageLog(
        recipient_type="employee",
        recipient_id=assignee.id,
        recipient_name=assignee.name,
        channel="WhatsApp",
        message_body=whatsapp_body,
        template_used="Task assignment",
        status=message_status(result),
    ))


@bp.get("/")
@permission_required("tasks", "view")
def list_tasks():
    q = scoped()
    for key in ("status", "assigned_to", "priority"):
        if request.args.get(key):
            q = q.filter(getattr(Task, key) == request.args[key])
    view = request.args.get("view")
    today = date.today()
    if view == "today":
        q = q.filter(Task.due_date == today, Task.status != "done")
    elif view == "upcoming":
        q = q.filter(Task.due_date > today, Task.status != "done")
    elif view == "overdue":
        q = q.filter(Task.due_date < today, Task.status != "done")
    return jsonify([x.to_dict() for x in q.order_by(Task.due_date.is_(None), Task.due_date.asc(), Task.created_at.desc()).all()])


@bp.get("/calendar")
@permission_required("calendar", "view")
def calendar_items():
    q = scoped().filter(Task.due_date.isnot(None))
    start = parse_date(request.args["start"]) if request.args.get("start") else None
    end = parse_date(request.args["end"]) if request.args.get("end") else None
    if start:
        q = q.filter(Task.due_date >= start)
    if end:
        q = q.filter(Task.due_date <= end)
    rows = q.order_by(Task.due_date.asc(), Task.priority.asc()).all()
    return jsonify([row.to_dict() for row in rows])


@bp.post("/send-due-reminders")
@permission_required("calendar", "schedule")
def send_due_reminders():
    now = datetime.utcnow()
    rows = scoped().filter(
        Task.status != "done",
        Task.reminder_at.isnot(None),
        Task.reminder_at <= now,
        Task.reminder_sent_at.is_(None),
    ).all()
    sent = 0
    for task in rows:
        if send_task_reminder(task):
            sent += 1
    log_activity(current_user().id, "task_reminders_sent", "task", None, f"{sent} reminders sent")
    db.session.commit()
    return jsonify({"sent": sent})


@bp.get("/assignees")
@permission_required("tasks", "view")
def assignees():
    user = current_user()
    users = User.query.filter_by(is_active=1).order_by(User.name).all() if has_permission(user, "tasks", "assign") else [user]
    return jsonify([u.to_dict() for u in users])


@bp.post("/")
@permission_required("tasks", "create")
def create_task():
    data = request.get_json() or {}
    user = current_user()
    task = update_model(Task(created_by=user.id), data, ALLOWED)
    if not has_permission(user, "tasks", "assign"):
        task.assigned_to = user.id
    if data.get("due_date"):
        task.due_date = parse_date(data["due_date"])
    for key in ("reminder_at", "meeting_start", "meeting_end"):
        if key in data:
            setattr(task, key, parse_datetime(data[key]) if data.get(key) else None)
    if not task.assigned_to:
        task.assigned_to = user.id
    if task.recurrence_rule and task.due_date:
        delta = recurrence_delta(task.recurrence_rule)
        task.recurrence_next_due = task.due_date + delta if delta else None
    db.session.add(task)
    db.session.flush()
    notify_assignment(task, user)
    log_activity(user.id, "task_created", "task", task.id, task.title)
    db.session.commit()
    return jsonify(task.to_dict()), 201


@bp.put("/<int:id>")
@permission_required("tasks", "update")
def update(id):
    task = scoped().filter_by(id=id).first_or_404()
    data = request.get_json() or {}
    old_assigned_to = task.assigned_to
    update_model(task, data, ALLOWED)
    if not has_permission(current_user(), "tasks", "assign"):
        task.assigned_to = old_assigned_to
    if "due_date" in data:
        task.due_date = parse_date(data["due_date"]) if data.get("due_date") else None
    for key in ("reminder_at", "meeting_start", "meeting_end"):
        if key in data:
            setattr(task, key, parse_datetime(data[key]) if data.get(key) else None)
    if task.status != "done":
        task.completed_at = None
    if task.recurrence_rule and task.due_date:
        delta = recurrence_delta(task.recurrence_rule)
        task.recurrence_next_due = task.due_date + delta if delta else None
    db.session.flush()
    if task.assigned_to and task.assigned_to != old_assigned_to:
        notify_assignment(task, current_user())
    log_activity(current_user().id, "task_updated", "task", task.id, task.title)
    db.session.commit()
    return jsonify(task.to_dict())


@bp.delete("/<int:id>")
@permission_required("tasks", "delete")
def delete(id):
    task = scoped().filter_by(id=id).first_or_404()
    db.session.delete(task)
    log_activity(current_user().id, "task_deleted", "task", id, task.title)
    db.session.commit()
    return jsonify({"message": "Task deleted"})


@bp.post("/<int:id>/complete")
@permission_required("tasks", "complete")
def complete(id):
    task = scoped().filter_by(id=id).first_or_404()
    if task.dependency_task and task.dependency_task.status != "done":
        return jsonify({"message": f"Complete dependency first: {task.dependency_task.title}"}), 400
    task.status = "done"
    task.completed_at = datetime.utcnow()
    next_task = create_next_recurrence(task)
    log_activity(current_user().id, "task_completed", "task", task.id, task.title)
    db.session.commit()
    return jsonify(task.to_dict() | {"next_recurring_task": next_task.to_dict() if next_task else None})


@bp.post("/<int:id>/send-reminder")
@permission_required("calendar", "schedule")
def send_single_reminder(id):
    task = scoped().filter_by(id=id).first_or_404()
    sent = send_task_reminder(task)
    db.session.commit()
    return jsonify({"sent": sent, "task": task.to_dict()})


@bp.post("/<int:id>/send-invite")
@permission_required("calendar", "schedule")
def send_invite(id):
    task = scoped().filter_by(id=id).first_or_404()
    invite = send_meeting_invite(task)
    db.session.commit()
    if not invite:
        return jsonify({"message": "Meeting start and assignee are required"}), 400
    return jsonify(invite.to_dict()), 201
