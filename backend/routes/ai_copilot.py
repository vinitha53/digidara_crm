import json
import re
import uuid
from datetime import date, datetime, time, timedelta

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import and_, or_

from extensions import db
from models import (
    AIFollowUpHistory, AIInteraction, Campaign, Customer, Lead, MessageLog, Notification, Task, User,
    WorkflowRule, WorkflowRuleRun,
)
from permissions import has_permission
from .utils import current_user, log_activity, permission_required

bp = Blueprint("ai_chat", __name__, url_prefix="/api/ai-chat")
OPEN_LEAD_STATUSES = ("new", "contacted", "qualified")
TABLE_LIMIT = 100


def scoped_query(model):
    user = current_user()
    query = model.query
    if model in (Lead, Customer) and not has_permission(user, "leads", "assign"):
        return query.filter(model.assigned_to == user.id)
    if model is Task and not has_permission(user, "tasks", "assign"):
        return query.filter(Task.assigned_to == user.id)
    if model is Notification:
        return query.filter(Notification.user_id == user.id)
    return query


def allowed_sources():
    user = current_user()
    sources = ["leads", "customers", "tasks", "notifications"]
    for page, source in (("communication", "communications"), ("ai_followups", "ai_followups"), ("campaigns", "campaigns"), ("employees", "employees"), ("workflows", "workflows")):
        if has_permission(user, page, "view"):
            sources.append(source)
    return sources


def period_from_prompt(prompt):
    today = date.today()
    if "yesterday" in prompt:
        start = today - timedelta(days=1)
        return "yesterday", start, start
    if "this week" in prompt:
        return "this week", today - timedelta(days=today.weekday()), today
    if "this month" in prompt:
        return "this month", today.replace(day=1), today
    match = re.search(r"last\s+(\d{1,3})\s+days?", prompt)
    if match:
        days = min(int(match.group(1)), 365)
        return f"last {days} days", today - timedelta(days=max(days - 1, 0)), today
    if "today" in prompt:
        return "today", today, today
    return "all time", None, None


def apply_datetime_period(query, column, start, end):
    if start:
        query = query.filter(column >= datetime.combine(start, time.min))
    if end:
        query = query.filter(column < datetime.combine(end + timedelta(days=1), time.min))
    return query


def wants_table(prompt):
    return bool(re.search(r"\b(table|tabular)\b", prompt))


def wants_details(prompt):
    return wants_table(prompt) or any(phrase in prompt for phrase in ("list", "details", "which", "show me", "display", "show "))


def fmt_date(value):
    if not value:
        return "-"
    return value.strftime("%d %b %Y" + (", %I:%M %p" if isinstance(value, datetime) else ""))


def result(answer, title, sources, metrics=None, columns=None, rows=None, notes=None, scope=None, intent="database_query", points=None, sections=None):
    rows = rows or []
    metrics = metrics or []
    answer_points = points or [f"{metric['label']}: {metric['value']}" for metric in metrics]
    structured = {
        "title": title,
        "metrics": metrics,
        "points": answer_points,
        "sections": sections or ([{"title": "Key details", "points": answer_points}] if answer_points else []),
        "table": {"columns": columns or [], "rows": rows},
        "notes": notes or [],
        "scope": scope or ("All authorized CRM records" if current_user().role == "admin" else "Records assigned or visible to you"),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    return {
        "answer": answer, "structured": structured, "sources": ",".join(sources),
        "format": "table" if rows else "summary", "row_count": len(rows), "intent": intent,
    }


def lead_answer(prompt):
    label, start, end = period_from_prompt(prompt)
    query = scoped_query(Lead)
    query = apply_datetime_period(query, Lead.created_at, start, end)
    category = None
    if "academic" in prompt:
        query, category = query.filter(Lead.lead_category.in_(("course", "internship"))), "academic"
    elif "internship" in prompt:
        query, category = query.filter(Lead.lead_category == "internship"), "internship"
    elif "course" in prompt:
        query, category = query.filter(Lead.lead_category == "course"), "course"
    elif "project" in prompt or "business" in prompt:
        query, category = query.filter(Lead.lead_category.in_(("business", "project"))), "project"
    status = next((s for s in ("new", "contacted", "qualified", "won", "lost") if re.search(rf"\b{s}\b", prompt)), None)
    if status:
        query = query.filter(Lead.status == status)
    if "unassigned" in prompt:
        query = query.filter(Lead.assigned_to.is_(None))
    if "hot" in prompt:
        query = query.filter(Lead.tag == "hot")
    total = query.count()
    open_count = query.filter(Lead.status.in_(OPEN_LEAD_STATUSES)).count()
    won_count = query.filter(Lead.status == "won").count()
    lost_count = query.filter(Lead.status == "lost").count()
    course_count = query.filter(Lead.lead_category == "course").count()
    internship_count = query.filter(Lead.lead_category == "internship").count()
    project_count = query.filter(Lead.lead_category.in_(("business", "project"))).count()
    unassigned_count = query.filter(Lead.assigned_to.is_(None), Lead.status.in_(OPEN_LEAD_STATUSES)).count()
    hot_count = query.filter(Lead.tag == "hot", Lead.status.in_(OPEN_LEAD_STATUSES)).count()
    today = date.today()
    today_count = apply_datetime_period(query, Lead.created_at, today, today).count()
    week_count = apply_datetime_period(query, Lead.created_at, today - timedelta(days=today.weekday()), today).count()
    month_count = apply_datetime_period(query, Lead.created_at, today.replace(day=1), today).count()
    qualifier = " ".join(x for x in (category, status, "leads") if x)
    answer = f"There {'is' if total == 1 else 'are'} {total} {qualifier} for {label}."
    metrics = [{"label": "Matching leads", "value": total}, {"label": "Open", "value": open_count}, {"label": "Won", "value": won_count}, {"label": "Lost", "value": lost_count}]
    columns, rows, points = [], [], []
    if wants_details(prompt):
        records = query.order_by(Lead.created_at.desc()).limit(TABLE_LIMIT).all()
        detail_rows = [{"id": x.id, "name": x.name, "category": "Project" if x.lead_category in ("business", "project") else (x.lead_category or "Course").title(), "interest": x.course_name or x.internship_name or x.business_requirement or x.service or "-", "stage": (x.status or "new").title(), "source": (x.source or "-").replace("_", " ").title(), "owner": x.assigned_user.name if x.assigned_user else "Unassigned", "created": fmt_date(x.created_at)} for x in records]
        points = [f"#{row['id']} {row['name']} — {row['category']}, {row['stage']}, assigned staff: {row['owner']}." for row in detail_rows[:10]]
        if wants_table(prompt):
            columns = [{"key": k, "label": v} for k, v in (("id", "ID"), ("name", "Lead"), ("category", "Category"), ("interest", "Interest"), ("stage", "Stage"), ("source", "Source"), ("owner", "Assigned Staff"), ("created", "Created"))]
            rows = detail_rows
    notes = [f"Showing the newest {len(rows)} of {total} matching records."] if total > len(rows) and rows else []
    owner_points = []
    if unassigned_count:
        owner_points.append(f"Assign staff to {unassigned_count} open lead{'s' if unassigned_count != 1 else ''} so follow-up accountability is clear.")
    if hot_count:
        owner_points.append(f"Prioritize {hot_count} hot open lead{'s' if hot_count != 1 else ''} for immediate contact.")
    if lost_count:
        owner_points.append(f"Review the lost reasons for {lost_count} lead{'s' if lost_count != 1 else ''} and address repeat objections.")
    if not owner_points:
        owner_points.append("No immediate assignment or hot-lead exception is visible in this result set.")
    sections = [
        {"title": "Business breakdown", "points": [f"Pipeline position: {open_count} open, {won_count} won and {lost_count} lost.", f"Demand mix: {course_count} course, {internship_count} internship and {project_count} project leads."]},
        {"title": "Recent movement", "points": [f"Added today: {today_count}.", f"Added this week: {week_count}.", f"Added this month: {month_count}."]},
        {"title": "Priority attention", "points": owner_points},
    ]
    if points:
        sections.append({"title": "Matching records", "points": points})
    return result(answer, f"{qualifier.title()} · {label.title()}", ["leads"], metrics, columns, rows, notes, points=points, sections=sections)


def conversion_answer(prompt):
    label, start, end = period_from_prompt(prompt)
    query = apply_datetime_period(scoped_query(Lead), Lead.created_at, start, end)
    if "academic" in prompt:
        query = query.filter(Lead.lead_category.in_(("course", "internship")))
    elif "project" in prompt or "business" in prompt:
        query = query.filter(Lead.lead_category.in_(("business", "project")))
    total = query.count()
    won = query.filter(Lead.status == "won").count()
    lost = query.filter(Lead.status == "lost").count()
    rate = round(won / total * 100, 1) if total else 0
    metrics = [{"label": "Leads", "value": total}, {"label": "Won", "value": won}, {"label": "Lost", "value": lost}, {"label": "Conversion", "value": f"{rate}%"}]
    categories = (("Course", ("course",)), ("Internship", ("internship",)), ("Projects", ("business", "project")))
    rows = []
    for name, values in categories:
        category_total = query.filter(Lead.lead_category.in_(values)).count()
        category_won = query.filter(Lead.lead_category.in_(values), Lead.status == "won").count()
        rows.append({"segment": name, "leads": category_total, "won": category_won, "lost": query.filter(Lead.lead_category.in_(values), Lead.status == "lost").count(), "conversion": f"{round(category_won / category_total * 100, 1) if category_total else 0}%"})
    columns = [{"key": "segment", "label": "Business line"}, {"key": "leads", "label": "Leads"}, {"key": "won", "label": "Won"}, {"key": "lost", "label": "Lost"}, {"key": "conversion", "label": "Conversion"}]
    points = [f"{row['segment']}: {row['leads']} leads, {row['won']} won, {row['lost']} lost, {row['conversion']} conversion." for row in rows]
    best = max(rows, key=lambda row: float(row["conversion"].rstrip("%")))
    owner_points = [f"Use {best['segment'].lower()} as the current conversion benchmark at {best['conversion']}." if total else "There are no leads in this period, so conversion performance cannot yet be evaluated."]
    if lost:
        owner_points.append(f"Review the lost reasons for {lost} lead{'s' if lost != 1 else ''} before increasing lead volume.")
    sections = [{"title": "Business-line performance", "points": points}, {"title": "Priority attention", "points": owner_points}]
    return result(f"The lead conversion rate for {label} is {rate}%: {won} won from {total} leads.", f"Lead conversion · {label.title()}", ["leads"], metrics, columns if wants_table(prompt) else [], rows if wants_table(prompt) else [], ["Conversion = won leads ÷ leads created in the selected period."], points=points, sections=sections)


def demand_answer(prompt):
    label, start, end = period_from_prompt(prompt)
    query = apply_datetime_period(scoped_query(Lead), Lead.created_at, start, end)
    definitions = (("Courses", ("course",)), ("Internships", ("internship",)), ("Projects", ("business", "project")))
    rows = []
    for name, categories in definitions:
        segment = query.filter(Lead.lead_category.in_(categories))
        total = segment.count()
        won = segment.filter(Lead.status == "won").count()
        rows.append({"segment": name, "leads": total, "open": segment.filter(Lead.status.in_(OPEN_LEAD_STATUSES)).count(), "won": won, "lost": segment.filter(Lead.status == "lost").count(), "conversion": f"{round(won / total * 100, 1) if total else 0}%"})
    leading = max(rows, key=lambda row: row["leads"])
    metrics = [{"label": "Academic demand", "value": rows[0]["leads"] + rows[1]["leads"]}, {"label": "Project demand", "value": rows[2]["leads"]}, {"label": "Highest demand", "value": leading["segment"]}]
    columns = [{"key": "segment", "label": "Business line"}, {"key": "leads", "label": "Leads"}, {"key": "open", "label": "Open"}, {"key": "won", "label": "Won"}, {"key": "lost", "label": "Lost"}, {"key": "conversion", "label": "Conversion"}]
    points = [f"{row['segment']}: {row['leads']} leads, {row['open']} open, {row['won']} won, {row['lost']} lost, {row['conversion']} conversion." for row in rows]
    sections = [{"title": "Demand breakdown", "points": points}, {"title": "Priority attention", "points": [f"Allocate follow-up capacity first to {leading['segment'].lower()}, which currently have the largest enquiry volume.", f"There are {sum(row['open'] for row in rows)} open opportunities across all business lines."]}]
    return result(f"For {label}, {leading['segment'].lower()} have the highest demand with {leading['leads']} leads.", f"Business demand · {label.title()}", ["leads"], metrics, columns if wants_table(prompt) else [], rows if wants_table(prompt) else [], ["Academic demand combines course and internship enquiries; projects combine business and project enquiries."], points=points, sections=sections)


def customer_answer(prompt):
    label, start, end = period_from_prompt(prompt)
    query = apply_datetime_period(scoped_query(Customer), Customer.created_at, start, end)
    status = next((s for s in ("active", "inactive", "completed", "on hold") if s in prompt), None)
    if status:
        query = query.filter(Customer.status == status)
    if "academic" in prompt:
        query = query.join(Lead, Customer.lead_id == Lead.id).filter(Lead.lead_category.in_(("course", "internship")))
    elif "project" in prompt or "business" in prompt:
        query = query.join(Lead, Customer.lead_id == Lead.id).filter(Lead.lead_category.in_(("business", "project")))
    total = query.count()
    active_count = query.filter(Customer.status == "active").count()
    followup_count = query.filter(Customer.status == "followup").count()
    inactive_count = query.filter(Customer.status == "inactive").count()
    cutoff = date.today() - timedelta(days=7)
    contact_overdue = query.filter(Customer.status.in_(("active", "followup")), or_(Customer.last_contact.is_(None), Customer.last_contact <= cutoff)).count()
    unassigned_count = query.filter(Customer.assigned_to.is_(None)).count()
    academic_ids = Lead.query.filter(Lead.lead_category.in_(("course", "internship"))).with_entities(Lead.id)
    project_ids = Lead.query.filter(Lead.lead_category.in_(("business", "project"))).with_entities(Lead.id)
    academic_count = query.filter(Customer.lead_id.in_(academic_ids)).count()
    project_count = query.filter(Customer.lead_id.in_(project_ids)).count()
    today = date.today()
    today_count = apply_datetime_period(query, Customer.created_at, today, today).count()
    week_count = apply_datetime_period(query, Customer.created_at, today - timedelta(days=today.weekday()), today).count()
    month_count = apply_datetime_period(query, Customer.created_at, today.replace(day=1), today).count()
    answer = f"There {'is' if total == 1 else 'are'} {total} matching customers for {label}."
    columns, rows, points = [], [], []
    if wants_details(prompt):
        records = query.order_by(Customer.created_at.desc()).limit(TABLE_LIMIT).all()
        detail_rows = [{"id": x.id, "name": x.name, "service": x.service or "-", "status": (x.status or "active").title(), "owner": x.assigned_user.name if x.assigned_user else "Unassigned", "last_contact": fmt_date(x.last_contact), "created": fmt_date(x.created_at)} for x in records]
        points = [f"#{row['id']} {row['name']} — {row['service']}, {row['status']}, assigned staff: {row['owner']}." for row in detail_rows[:10]]
        if wants_table(prompt):
            columns = [{"key": k, "label": v} for k, v in (("id", "ID"), ("name", "Customer"), ("service", "Service"), ("status", "Status"), ("owner", "Assigned Staff"), ("last_contact", "Last contact"), ("created", "Created"))]
            rows = detail_rows
    owner_points = []
    if contact_overdue:
        owner_points.append(f"Contact is overdue for {contact_overdue} active/follow-up customer{'s' if contact_overdue != 1 else ''}; schedule relationship follow-ups.")
    if followup_count:
        owner_points.append(f"{followup_count} customer{'s are' if followup_count != 1 else ' is'} explicitly marked for follow-up.")
    if unassigned_count:
        owner_points.append(f"Assign a staff contact to {unassigned_count} customer{'s' if unassigned_count != 1 else ''}.")
    if not owner_points:
        owner_points.append("No overdue-contact or assignment exception is visible in this result set.")
    sections = [
        {"title": "Relationship health", "points": [f"Status mix: {active_count} active, {followup_count} follow-up and {inactive_count} inactive.", f"Business mix: {academic_count} academic and {project_count} project customers."]},
        {"title": "Recent additions", "points": [f"Added today: {today_count}.", f"Added this week: {week_count}.", f"Added this month: {month_count}."]},
        {"title": "Priority attention", "points": owner_points},
    ]
    if points:
        sections.append({"title": "Matching records", "points": points})
    return result(answer, f"Customers · {label.title()}", ["customers"], [{"label": "Matching customers", "value": total}], columns, rows, [f"Showing the newest {len(rows)} of {total} matching records."] if rows and total > len(rows) else [], points=points, sections=sections)


def task_answer(prompt):
    label, start, end = period_from_prompt(prompt)
    query = scoped_query(Task)
    today = date.today()
    if "calendar" in prompt or "agenda" in prompt:
        if not start:
            start, end, label = today, today, "today"
        query = query.filter(Task.due_date >= start, Task.due_date <= end)
    elif "overdue" in prompt:
        query, label = query.filter(Task.status != "done", Task.due_date < today), "overdue"
    elif "due today" in prompt or "today's task" in prompt or "tasks today" in prompt:
        query, label = query.filter(Task.status != "done", Task.due_date == today), "due today"
    elif "completed" in prompt or "done" in prompt:
        query = query.filter(Task.status == "done")
        query = apply_datetime_period(query, Task.completed_at, start, end)
    else:
        query = apply_datetime_period(query, Task.created_at, start, end)
        if "open" in prompt or not start:
            query = query.filter(Task.status != "done")
    total = query.count()
    open_count = query.filter(Task.status != "done").count()
    completed_count = query.filter(Task.status == "done").count()
    overdue_count = query.filter(Task.status != "done", Task.due_date < today).count()
    due_today_count = query.filter(Task.status != "done", Task.due_date == today).count()
    high_priority_count = query.filter(Task.status != "done", db.func.lower(Task.priority) == "high").count()
    unassigned_count = query.filter(Task.status != "done", Task.assigned_to.is_(None)).count()
    answer = f"There {'is' if total == 1 else 'are'} {total} {label} task{'s' if total != 1 else ''}."
    columns, rows, points = [], [], []
    if wants_details(prompt):
        records = query.order_by(Task.due_date.asc(), Task.created_at.desc()).limit(TABLE_LIMIT).all()
        detail_rows = [{"id": x.id, "title": x.title, "priority": x.priority or "Medium", "status": "Completed" if x.status == "done" else ("Overdue" if x.due_date and x.due_date < today else "Open"), "due": fmt_date(x.due_date), "owner": x.assigned_user.name if x.assigned_user else "Unassigned", "related": x.related_name or "Internal work"} for x in records]
        points = [f"#{row['id']} {row['title']} — {row['status']}, due {row['due']}, assigned to {row['owner']}." for row in detail_rows[:10]]
        if wants_table(prompt):
            columns = [{"key": k, "label": v} for k, v in (("id", "ID"), ("title", "Task"), ("priority", "Priority"), ("status", "Status"), ("due", "Due"), ("owner", "Assigned to"), ("related", "Related to"))]
            rows = detail_rows
    owner_points = []
    if overdue_count:
        owner_points.append(f"Escalate {overdue_count} overdue task{'s' if overdue_count != 1 else ''} and confirm a new completion commitment.")
    if high_priority_count:
        owner_points.append(f"Protect execution time for {high_priority_count} open high-priority task{'s' if high_priority_count != 1 else ''}.")
    if unassigned_count:
        owner_points.append(f"Assign {unassigned_count} open task{'s' if unassigned_count != 1 else ''} before work is missed.")
    if not owner_points:
        owner_points.append("No overdue, high-priority or unassigned exception is visible in this result set.")
    sections = [
        {"title": "Execution breakdown", "points": [f"Task status: {open_count} open and {completed_count} completed.", f"Time pressure: {due_today_count} due today and {overdue_count} overdue."]},
        {"title": "Priority attention", "points": owner_points},
    ]
    if points:
        sections.append({"title": "Matching tasks", "points": points})
    return result(answer, f"Tasks · {label.title()}", ["tasks"], [{"label": "Matching tasks", "value": total}], columns, rows, points=points, sections=sections)


def followup_answer(prompt):
    if not has_permission(current_user(), "ai_followups", "view"):
        return result("You do not have permission to read AI follow-up data.", "AI follow-ups unavailable", [], notes=["Ask an administrator to grant view permission."], intent="permission_limited")
    label, start, end = period_from_prompt(prompt)
    lead_query = scoped_query(Lead)
    if "due" in prompt or "scheduled" in prompt:
        if not start:
            start, end, label = date.today(), date.today(), "today"
        query = apply_datetime_period(lead_query.filter(Lead.ai_followup_enabled == 1), Lead.ai_next_followup_at, start, end)
        total = query.count()
        columns, rows, points = [], [], []
        if wants_details(prompt):
            records = query.order_by(Lead.ai_next_followup_at.asc()).limit(TABLE_LIMIT).all()
            detail_rows = [{"id": x.id, "lead": x.name, "category": "Project" if x.lead_category in ("business", "project") else (x.lead_category or "Course").title(), "next_followup": fmt_date(x.ai_next_followup_at), "channel": x.ai_preferred_channel or "WhatsApp", "owner": x.assigned_user.name if x.assigned_user else "Unassigned"} for x in records]
            points = [f"#{row['id']} {row['lead']} — {row['channel']} follow-up at {row['next_followup']}, assigned staff: {row['owner']}." for row in detail_rows[:10]]
            if wants_table(prompt):
                columns = [{"key": k, "label": v} for k, v in (("id", "Lead ID"), ("lead", "Lead"), ("category", "Category"), ("next_followup", "Next follow-up"), ("channel", "Channel"), ("owner", "Assigned Staff"))]
                rows = detail_rows
        return result(f"There are {total} AI follow-ups due {label}.", f"AI follow-ups due · {label.title()}", ["leads", "ai_followups"], [{"label": "Due follow-ups", "value": total}], columns, rows, points=points)
    allowed_ids = lead_query.with_entities(Lead.id)
    query = AIFollowUpHistory.query.filter(AIFollowUpHistory.lead_id.in_(allowed_ids))
    query = apply_datetime_period(query, AIFollowUpHistory.created_at, start, end)
    status = next((s for s in ("generated", "sent", "failed", "skipped") if s in prompt), None)
    if status:
        query = query.filter(AIFollowUpHistory.status == status)
    total = query.count()
    sent = query.filter(AIFollowUpHistory.status == "sent").count()
    failed = query.filter(AIFollowUpHistory.status == "failed").count()
    columns, rows, points = [], [], []
    if wants_details(prompt):
        records = query.order_by(AIFollowUpHistory.created_at.desc()).limit(TABLE_LIMIT).all()
        detail_rows = [{"id": x.id, "lead": x.lead.name if x.lead else f"Lead #{x.lead_id}", "channel": x.channel or "-", "status": (x.status or "-").title(), "delivery": (x.delivery_status or "-").title(), "scheduled": fmt_date(x.scheduled_for), "sent_at": fmt_date(x.sent_at)} for x in records]
        points = [f"#{row['id']} {row['lead']} — {row['channel']}, {row['status']}, delivery: {row['delivery']}." for row in detail_rows[:10]]
        if wants_table(prompt):
            columns = [{"key": k, "label": v} for k, v in (("id", "ID"), ("lead", "Lead"), ("channel", "Channel"), ("status", "Status"), ("delivery", "Delivery"), ("scheduled", "Scheduled"), ("sent_at", "Sent"))]
            rows = detail_rows
    return result(f"For {label}, {total} AI follow-ups match: {sent} sent and {failed} failed.", f"AI follow-up activity · {label.title()}", ["ai_followups"], [{"label": "Follow-ups", "value": total}, {"label": "Sent", "value": sent}, {"label": "Failed", "value": failed}], columns, rows, points=points)


def message_query():
    user = current_user()
    query = MessageLog.query
    if has_permission(user, "leads", "assign"):
        return query
    lead_ids = scoped_query(Lead).with_entities(Lead.id)
    customer_ids = scoped_query(Customer).with_entities(Customer.id)
    return query.filter(or_(and_(MessageLog.recipient_type == "lead", MessageLog.recipient_id.in_(lead_ids)), and_(MessageLog.recipient_type == "customer", MessageLog.recipient_id.in_(customer_ids)), and_(MessageLog.recipient_type == "employee", MessageLog.recipient_id == user.id)))


def communication_answer(prompt):
    label, start, end = period_from_prompt(prompt)
    query = apply_datetime_period(message_query(), MessageLog.sent_at, start, end)
    status = next((s for s in ("sent", "failed", "skipped") if s in prompt), None)
    if status:
        query = query.filter(MessageLog.status == status)
    total = query.count()
    sent = query.filter(MessageLog.status == "sent").count()
    failed = query.filter(MessageLog.status == "failed").count()
    answer = f"For {label}, {total} messages match: {sent} sent and {failed} failed."
    columns, rows, points = [], [], []
    if wants_details(prompt):
        records = query.order_by(MessageLog.sent_at.desc()).limit(TABLE_LIMIT).all()
        detail_rows = [{"id": x.id, "recipient": x.recipient_name or f"Record #{x.recipient_id}", "type": (x.recipient_type or "-").title(), "channel": x.channel or "-", "status": (x.status or "-").title(), "template": x.template_used or "Custom", "sent_at": fmt_date(x.sent_at)} for x in records]
        points = [f"#{row['id']} {row['recipient']} — {row['channel']}, {row['status']}, sent {row['sent_at']}." for row in detail_rows[:10]]
        if wants_table(prompt):
            columns = [{"key": k, "label": v} for k, v in (("id", "ID"), ("recipient", "Recipient"), ("type", "Type"), ("channel", "Channel"), ("status", "Status"), ("template", "Template"), ("sent_at", "Sent"))]
            rows = detail_rows
    delivery_rate = round(sent / total * 100, 1) if total else 0
    summary_points = [f"Delivery result: {sent} sent, {failed} failed and {max(total - sent - failed, 0)} skipped or pending.", f"Successful-delivery rate: {delivery_rate}% of matching messages."]
    owner_points = [f"Investigate and retry {failed} failed message{'s' if failed != 1 else ''}." if failed else "No failed delivery requires escalation in this result set."]
    if points:
        summary_sections = [{"title": "Delivery performance", "points": summary_points}, {"title": "Priority attention", "points": owner_points}, {"title": "Matching messages", "points": points}]
    else:
        summary_sections = [{"title": "Delivery performance", "points": summary_points}, {"title": "Priority attention", "points": owner_points}]
    return result(answer, f"Communication · {label.title()}", ["communications"], [{"label": "Messages", "value": total}, {"label": "Sent", "value": sent}, {"label": "Failed", "value": failed}], columns, rows, points=points, sections=summary_sections)


def simple_module_answer(prompt, model, source, date_column, columns_map, row_builder, permission_page=None):
    if permission_page and not has_permission(current_user(), permission_page, "view"):
        return result(f"You do not have permission to read {source} data.", f"{source.title()} unavailable", [], notes=["Ask an administrator to grant view permission."], intent="permission_limited")
    label, start, end = period_from_prompt(prompt)
    query = apply_datetime_period(scoped_query(model), date_column, start, end)
    total = query.count()
    cols, rows, points = [], [], []
    if wants_details(prompt):
        records = query.order_by(date_column.desc()).limit(TABLE_LIMIT).all()
        detail_rows = [row_builder(x) for x in records]
        points = [" — ".join(str(value) for value in row.values() if value not in (None, "-")) for row in detail_rows[:10]]
        if wants_table(prompt):
            cols = [{"key": key, "label": label_text} for key, label_text in columns_map]
            rows = detail_rows
    breakdown, owner_points = [], []
    if model is User:
        active = query.filter(User.is_active == 1).count()
        inactive = total - active
        breakdown = [f"Access status: {active} active and {inactive} inactive employees.", f"Role mix: {query.filter(User.role == 'admin').count()} administrators and {query.filter(User.role != 'admin').count()} staff members."]
        owner_points = [f"Review whether {inactive} inactive account{'s' if inactive != 1 else ''} should remain retained." if inactive else "All employee accounts in this result set are active."]
    elif model is Campaign:
        draft = query.filter(Campaign.status == "draft").count()
        scheduled = query.filter(Campaign.status == "scheduled").count()
        sent_count = query.filter(Campaign.status == "sent").count()
        breakdown = [f"Campaign status: {draft} draft, {scheduled} scheduled and {sent_count} sent.", f"Recorded recipients sent: {sum(row.sent_count or 0 for row in query.all())}."]
        owner_points = [f"Review and approve {draft} draft campaign{'s' if draft != 1 else ''}." if draft else "No draft campaign is waiting for approval."]
    elif model is Notification:
        unread = query.filter(Notification.is_read == 0).count()
        breakdown = [f"Read status: {unread} unread and {total - unread} read notifications."]
        owner_points = [f"Review {unread} unread notification{'s' if unread != 1 else ''} for pending CRM actions." if unread else "No unread notification requires attention."]
    elif model is WorkflowRule:
        active = query.filter(WorkflowRule.is_active == 1).count()
        inactive = total - active
        breakdown = [f"Automation status: {active} active and {inactive} inactive workflows."]
        owner_points = [f"Confirm whether {inactive} inactive workflow{'s' if inactive != 1 else ''} should be re-enabled or retired." if inactive else "All workflows in this result set are active."]
    sections = [{"title": "Business breakdown", "points": breakdown or [f"Matching {source} records: {total}."]}, {"title": "Priority attention", "points": owner_points or ["No immediate exception is visible in this result set."]}]
    if points:
        sections.append({"title": "Matching records", "points": points})
    return result(f"There are {total} {source} records for {label}.", f"{source.title()} · {label.title()}", [source], [{"label": source.title(), "value": total}], cols, rows, points=points, sections=sections)


def overview_answer(prompt):
    leads = scoped_query(Lead)
    customers = scoped_query(Customer)
    tasks = scoped_query(Task)
    total = leads.count()
    won = leads.filter(Lead.status == "won").count()
    metrics = [
        {"label": "Total leads", "value": total},
        {"label": "Open leads", "value": leads.filter(Lead.status.in_(OPEN_LEAD_STATUSES)).count()},
        {"label": "Conversion", "value": f"{round(won / total * 100, 1) if total else 0}%"},
        {"label": "Active customers", "value": customers.filter(Customer.status == "active").count()},
        {"label": "Overdue tasks", "value": tasks.filter(Task.status != "done", Task.due_date < date.today()).count()},
        {"label": "Unassigned leads", "value": leads.filter(Lead.assigned_to.is_(None), Lead.status.in_(OPEN_LEAD_STATUSES)).count()},
    ]
    rows = [
        {"area": "Academic leads", "count": leads.filter(Lead.lead_category.in_(("course", "internship"))).count(), "owner_action": "Review open course and internship demand"},
        {"area": "Project leads", "count": leads.filter(Lead.lead_category.in_(("business", "project"))).count(), "owner_action": "Review client project opportunities"},
        {"area": "Overdue tasks", "count": metrics[4]["value"], "owner_action": "Remove execution blockers"},
        {"area": "Unassigned leads", "count": metrics[5]["value"], "owner_action": "Assign staff today"},
    ]
    columns = [{"key": "area", "label": "Business area"}, {"key": "count", "label": "Current count"}, {"key": "owner_action", "label": "Recommended action"}]
    points = [f"{row['area']}: {row['count']}. Recommended action: {row['owner_action']}." for row in rows]
    return result("Here is the current business view calculated from the live CRM database.", "CRM business overview", ["leads", "customers", "tasks"], metrics, columns if wants_table(prompt) else [], rows if wants_table(prompt) else [], ["Counts are calculated when you ask; no browser sample data is used."], points=points)


def answer_database_question(raw_prompt):
    prompt = raw_prompt.lower().strip()
    if "follow-up" in prompt or "follow up" in prompt or "followup" in prompt:
        return followup_answer(prompt)
    if any(x in prompt for x in ("lead", "enquir", "conversion", "pipeline", "academic", "internship", "course", "project demand")):
        if "conversion" in prompt:
            return conversion_answer(prompt)
        if "demand" in prompt or ("compare" in prompt and any(x in prompt for x in ("academic", "course", "internship", "project"))):
            return demand_answer(prompt)
        return lead_answer(prompt)
    if any(x in prompt for x in ("customer", "client")):
        return customer_answer(prompt)
    if any(x in prompt for x in ("task", "overdue", "due today", "work due", "calendar", "agenda")):
        return task_answer(prompt)
    if any(x in prompt for x in ("message", "whatsapp", "communication", "delivery", "sent")):
        if not has_permission(current_user(), "communication", "view"):
            return result("You do not have permission to read communication data.", "Communication unavailable", [], notes=["Ask an administrator to grant view permission."], intent="permission_limited")
        return communication_answer(prompt)
    if any(x in prompt for x in ("employee", "staff", "team member")):
        return simple_module_answer(prompt, User, "employees", User.created_at, (("id", "ID"), ("name", "Employee"), ("role", "Role"), ("department", "Department"), ("branch", "Branch"), ("active", "Active")), lambda x: {"id": x.id, "name": x.name, "role": (x.role or "-").title(), "department": x.department or "-", "branch": x.branch or "-", "active": "Yes" if x.is_active else "No"}, "employees")
    if "campaign" in prompt:
        return simple_module_answer(prompt, Campaign, "campaigns", Campaign.created_at, (("id", "ID"), ("name", "Campaign"), ("channel", "Channel"), ("audience", "Audience"), ("status", "Status"), ("sent", "Sent"), ("created", "Created")), lambda x: {"id": x.id, "name": x.name, "channel": x.channel, "audience": x.audience, "status": (x.status or "draft").title(), "sent": x.sent_count or 0, "created": fmt_date(x.created_at)}, "campaigns")
    if "notification" in prompt or "unread" in prompt:
        result_data = simple_module_answer(prompt, Notification, "notifications", Notification.created_at, (("id", "ID"), ("title", "Notification"), ("type", "Type"), ("read", "Read"), ("created", "Created")), lambda x: {"id": x.id, "title": x.title, "type": (x.type or "-").title(), "read": "Yes" if x.is_read else "No", "created": fmt_date(x.created_at)})
        if "unread" in prompt:
            query = scoped_query(Notification).filter(Notification.is_read == 0)
            result_data["answer"] = f"You have {query.count()} unread notifications."
            result_data["structured"]["metrics"] = [{"label": "Unread", "value": query.count()}]
        return result_data
    if "workflow" in prompt or "automation" in prompt:
        return simple_module_answer(prompt, WorkflowRule, "workflows", WorkflowRule.created_at, (("id", "ID"), ("name", "Workflow"), ("entity", "Entity"), ("trigger", "Trigger"), ("active", "Active"), ("created", "Created")), lambda x: {"id": x.id, "name": x.name, "entity": x.entity_type.title(), "trigger": x.trigger_type.replace("_", " ").title(), "active": "Yes" if x.is_active else "No", "created": fmt_date(x.created_at)}, "workflows")
    return overview_answer(prompt)


@bp.get("/capabilities")
@permission_required("ai_chat", "view")
def capabilities():
    return jsonify({"sources": allowed_sources(), "table_limit": TABLE_LIMIT, "scope": "all" if current_user().role == "admin" else "assigned"})


@bp.get("/history")
@permission_required("ai_chat", "view")
def history():
    query = AIInteraction.query.filter_by(user_id=current_user().id)
    conversation_id = (request.args.get("conversation_id") or "").strip()
    if conversation_id:
        if conversation_id.startswith("legacy-"):
            try:
                query = query.filter(AIInteraction.id == int(conversation_id.removeprefix("legacy-")))
            except ValueError:
                return jsonify({"message": "Conversation not found."}), 404
        else:
            query = query.filter(AIInteraction.conversation_id == conversation_id)
        rows = query.order_by(AIInteraction.created_at.asc(), AIInteraction.id.asc()).limit(100).all()
    else:
        rows = query.order_by(AIInteraction.created_at.desc()).limit(30).all()
    return jsonify([row.to_dict() for row in rows])


@bp.get("/conversations")
@permission_required("ai_chat", "view")
def conversations():
    rows = AIInteraction.query.filter_by(user_id=current_user().id).order_by(
        AIInteraction.created_at.desc(), AIInteraction.id.desc()
    ).limit(500).all()
    grouped = {}
    for row in rows:
        conversation_id = row.conversation_id or f"legacy-{row.id}"
        if conversation_id not in grouped:
            grouped[conversation_id] = {
                "id": conversation_id,
                "title": row.conversation_title or row.prompt[:80] or "CRM conversation",
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.created_at.isoformat() if row.created_at else None,
                "message_count": 0,
            }
        grouped[conversation_id]["message_count"] += 1
    return jsonify(list(grouped.values())[:50])


@bp.post("/ask")
@permission_required("ai_chat", "ask")
def ask():
    payload = request.get_json() or {}
    prompt = (payload.get("prompt") or "Summarize CRM").strip()
    if not prompt:
        return jsonify({"message": "Enter a CRM question."}), 400
    if len(prompt) > 1000:
        return jsonify({"message": "Question must be 1000 characters or fewer."}), 400
    try:
        answer = answer_database_question(prompt)
        status, model = "success", "CRM query engine"
    except Exception:
        current_app.logger.exception("AI Chat database query failed")
        return jsonify({"message": "The live CRM query could not be completed. Please try again."}), 500
    conversation_id = str(payload.get("conversation_id") or "").strip()[:64] or uuid.uuid4().hex
    existing = AIInteraction.query.filter_by(conversation_id=conversation_id).first()
    if existing and existing.user_id != current_user().id:
        return jsonify({"message": "Conversation not found."}), 404
    conversation_title = existing.conversation_title if existing else re.sub(r"\s+", " ", prompt)[:80]
    row = AIInteraction(
        user_id=current_user().id, prompt=prompt, response=answer["answer"], intent=answer["intent"],
        conversation_id=conversation_id, conversation_title=conversation_title,
        model=model, status=status, sources=answer["sources"], response_format=answer["format"],
        response_data=json.dumps(answer["structured"], default=str), row_count=answer["row_count"],
    )
    db.session.add(row)
    db.session.flush()
    log_activity(current_user().id, "ai_chat_asked", "ai_interaction", row.id, prompt[:120], json.dumps({"sources": answer["sources"], "row_count": answer["row_count"]}))
    db.session.commit()
    return jsonify(row.to_dict())
