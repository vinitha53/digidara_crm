from datetime import date, datetime, time, timedelta
import csv
import io
from flask import Blueprint, Response, jsonify, request
from sqlalchemy import case, func, or_
from extensions import db
from models import ActivityLog, Customer, Lead, Task, User
from services.lost_reason_service import canonical_lost_reason
from .utils import current_user, permission_required

bp = Blueprint("reports", __name__, url_prefix="/api/reports")
OPEN_STATUSES = ("new", "contacted", "qualified")


def loss_reason_breakdown(query, total_lost, limit=None):
    grouped = {}
    rows = query.with_entities(Lead.lost_reason, func.count(Lead.id)).filter(
        Lead.status == "lost"
    ).group_by(Lead.lost_reason).all()
    for reason, count in rows:
        category = canonical_lost_reason(reason) or "Not specified"
        grouped[category] = grouped.get(category, 0) + int(count or 0)
    ordered = sorted(grouped.items(), key=lambda item: (-item[1], item[0]))
    if limit:
        ordered = ordered[:limit]
    return [{
        "id": name,
        "key": name,
        "name": name,
        "count": count,
        "share": round(count / max(total_lost, 1) * 100, 1),
    } for name, count in ordered]


def report_period(value):
    today = date.today()
    options = {
        "30": ("Last 30 days", today - timedelta(days=29)),
        "90": ("Last 90 days", today - timedelta(days=89)),
        "180": ("Last 6 months", today - timedelta(days=179)),
        "365": ("Last 12 months", today - timedelta(days=364)),
        "all": ("All time", None),
    }
    key = value if value in options else "90"
    label, start = options[key]
    return key, label, start, today


def period_query(query, column, start):
    return query.filter(column >= datetime.combine(start, time.min)) if start else query


def average_conversion_days(query):
    pairs = query.filter(Lead.status == "won", Lead.created_at.isnot(None), Lead.updated_at.isnot(None)).with_entities(Lead.created_at, Lead.updated_at).all()
    durations = [max((updated_at - created_at).total_seconds() / 86400, 0) for created_at, updated_at in pairs]
    return round(sum(durations) / len(durations), 1) if durations else None


def owner_report_data(period_value="90"):
    period, period_label, start, today = report_period(period_value)
    leads = period_query(Lead.query, Lead.created_at, start)
    total = leads.count()
    won = leads.filter(Lead.status == "won").count()
    lost = leads.filter(Lead.status == "lost").count()
    open_count = leads.filter(Lead.status.in_(OPEN_STATUSES)).count()
    pipeline_order = (("new", "New"), ("contacted", "Contacted"), ("qualified", "Qualified"), ("won", "Won"), ("lost", "Lost"))
    pipeline = []
    for key, name in pipeline_order:
        count = leads.filter(Lead.status == key).count()
        pipeline.append({"id": key, "key": key, "name": name, "value": count, "share": round(count / max(total, 1) * 100, 1)})
    average_days_to_win = average_conversion_days(leads)

    category_rows = []
    category_definitions = (("course", "Courses", ("course",)), ("internship", "Internships", ("internship",)), ("project", "Client Projects", ("business", "project")))
    for key, name, values in category_definitions:
        group = leads.filter(Lead.lead_category.in_(values))
        group_total = group.count()
        group_won = group.filter(Lead.status == "won").count()
        category_rows.append({
            "id": key, "key": key, "name": name, "leads": group_total,
            "open": group.filter(Lead.status.in_(OPEN_STATUSES)).count(),
            "won": group_won, "lost": group.filter(Lead.status == "lost").count(),
            "conversion_rate": round(group_won / max(group_total, 1) * 100, 1),
        })

    source_groups = leads.with_entities(
        Lead.source, func.count(Lead.id),
        func.sum(case((Lead.status == "won", 1), else_=0)),
        func.sum(case((Lead.status == "lost", 1), else_=0)),
    ).group_by(Lead.source).all()
    sources = []
    for source, source_total, source_won, source_lost in source_groups:
        source_total, source_won, source_lost = int(source_total or 0), int(source_won or 0), int(source_lost or 0)
        sources.append({
            "id": source or "unknown", "key": source or "unknown",
            "name": (source or "unknown").replace("_", " ").title(),
            "leads": source_total, "won": source_won, "lost": source_lost,
            "conversion_rate": round(source_won / max(source_total, 1) * 100, 1),
        })
    sources.sort(key=lambda row: (row["conversion_rate"], row["leads"]), reverse=True)

    loss_reasons = loss_reason_breakdown(leads, lost)

    trend_start = start or shift_month(today.replace(day=1), -11)
    month_cursor = trend_start.replace(day=1)
    current_month = today.replace(day=1)
    trend = []
    while month_cursor <= current_month:
        month_end = shift_month(month_cursor, 1)
        trend.append({
            "name": month_cursor.strftime("%b %y"),
            "leads": Lead.query.filter(Lead.created_at >= month_cursor, Lead.created_at < month_end).count(),
            "won": Lead.query.filter(Lead.status == "won", Lead.updated_at >= month_cursor, Lead.updated_at < month_end).count(),
            "lost": Lead.query.filter(Lead.status == "lost", Lead.updated_at >= month_cursor, Lead.updated_at < month_end).count(),
        })
        month_cursor = month_end

    current_open = Lead.query.filter(Lead.status.in_(OPEN_STATUSES))
    stale_cutoff = datetime.combine(today - timedelta(days=7), time.min)
    unassigned = current_open.filter(Lead.assigned_to.is_(None)).count()
    stale = current_open.filter(func.coalesce(Lead.last_contacted, Lead.created_at) < stale_cutoff).count()
    hot = current_open.filter(Lead.tag == "hot").count()
    overdue_tasks = Task.query.filter(Task.status != "done", Task.due_date < today).count()
    tasks_due_today = Task.query.filter(Task.status != "done", Task.due_date == today).count()
    new_customers = period_query(Customer.query, Customer.created_at, start).count()
    contact_cutoff = today - timedelta(days=7)
    customers_contact_overdue = Customer.query.filter(Customer.status.in_(("active", "followup")), or_(Customer.last_contact.is_(None), Customer.last_contact <= contact_cutoff)).count()

    aging_buckets = []
    for name, low, high in (("0–2 days", 0, 2), ("3–7 days", 3, 7), ("8–14 days", 8, 14), ("15+ days", 15, 36500)):
        aging_buckets.append({"id": name, "name": name, "value": current_open.filter(Lead.created_at <= datetime.combine(today - timedelta(days=low), time.max), Lead.created_at > datetime.combine(today - timedelta(days=high + 1), time.min)).count()})

    employees = []
    for user in User.query.filter(User.is_active == 1, User.role != "admin").order_by(User.name).all():
        assigned = leads.filter(Lead.assigned_to == user.id)
        assigned_count = assigned.count()
        assigned_won = assigned.filter(Lead.status == "won").count()
        employee_stale = assigned.filter(Lead.status.in_(OPEN_STATUSES), func.coalesce(Lead.last_contacted, Lead.created_at) < stale_cutoff).count()
        never_contacted = assigned.filter(Lead.status.in_(OPEN_STATUSES), Lead.last_contacted.is_(None)).count()
        open_tasks = Task.query.filter(Task.assigned_to == user.id, Task.status != "done").count()
        employee_overdue = Task.query.filter(Task.assigned_to == user.id, Task.status != "done", Task.due_date < today).count()
        completed = Task.query.filter(Task.assigned_to == user.id, Task.status == "done")
        completed = period_query(completed, Task.completed_at, start).count()
        employees.append({
            "id": user.id, "name": user.name, "department": user.department or "—",
            "leads_assigned": assigned_count, "open_leads": assigned.filter(Lead.status.in_(OPEN_STATUSES)).count(),
            "contacted_leads": assigned.filter(Lead.status == "contacted").count(),
            "qualified_leads": assigned.filter(Lead.status == "qualified").count(),
            "leads_won": assigned_won, "leads_lost": assigned.filter(Lead.status == "lost").count(),
            "win_rate": round(assigned_won / max(assigned_count, 1) * 100, 1),
            "average_days_to_win": average_conversion_days(assigned),
            "stale_leads": employee_stale, "never_contacted": never_contacted,
            "open_tasks": open_tasks, "overdue_tasks": employee_overdue, "tasks_completed": completed,
        })
    employees.sort(key=lambda row: (row["overdue_tasks"], row["open_leads"]), reverse=True)

    unspecified_losses = next((row["count"] for row in loss_reasons if row["name"] == "Not specified"), 0)
    actions = []
    if overdue_tasks:
        actions.append({"id": "overdue_tasks", "priority": "critical", "title": f"Resolve {overdue_tasks} overdue task{'s' if overdue_tasks != 1 else ''}", "detail": "Remove execution blockers and confirm new completion dates.", "to": "/tasks?filter=overdue"})
    if unassigned:
        actions.append({"id": "unassigned", "priority": "high", "title": f"Assign {unassigned} open lead{'s' if unassigned != 1 else ''}", "detail": "Every open enquiry needs a named staff member responsible for follow-up.", "to": "/leads?stage=open"})
    if stale:
        actions.append({"id": "stale", "priority": "high", "title": f"Recover {stale} stale lead{'s' if stale != 1 else ''}", "detail": "No contact has been recorded for more than seven days.", "to": "/leads?stage=open"})
    if customers_contact_overdue:
        actions.append({"id": "customer_contact", "priority": "medium", "title": f"Contact {customers_contact_overdue} overdue customer{'s' if customers_contact_overdue != 1 else ''}", "detail": "Protect active customer relationships with a scheduled check-in.", "to": "/customers?attention=contact_overdue"})
    if unspecified_losses:
        actions.append({"id": "loss_reason", "priority": "medium", "title": f"Complete {unspecified_losses} missing lost reason{'s' if unspecified_losses != 1 else ''}", "detail": "Accurate loss reasons are required for useful business decisions.", "to": "/leads?status=lost"})
    if not actions:
        actions.append({"id": "healthy", "priority": "healthy", "title": "No critical operating exception", "detail": "Continue monitoring source quality and lead progression.", "to": "/leads"})

    best_source = sources[0] if sources else None
    ranked_converters = [row for row in employees if row["leads_assigned"]]
    top_converter = max(ranked_converters, key=lambda row: (row["leads_won"], row["win_rate"], -row["overdue_tasks"]), default=None)
    fastest_converter = min((row for row in employees if row["average_days_to_win"] is not None), key=lambda row: row["average_days_to_win"], default=None)
    best_business_line = max((row for row in category_rows if row["leads"]), key=lambda row: (row["conversion_rate"], row["won"]), default=None)
    return {
        "period": {"key": period, "label": period_label, "start": start.isoformat() if start else None, "end": today.isoformat()},
        "summary": {
            "leads": total, "open": open_count, "won": won, "lost": lost,
            "average_days_to_win": average_days_to_win,
            "conversion_rate": round(won / max(total, 1) * 100, 1),
            "loss_rate": round(lost / max(total, 1) * 100, 1), "new_customers": new_customers,
            "current_open": current_open.count(), "unassigned": unassigned, "stale": stale,
            "hot": hot, "overdue_tasks": overdue_tasks, "tasks_due_today": tasks_due_today,
            "customer_contact_overdue": customers_contact_overdue,
        },
        "categories": category_rows, "sources": sources, "best_source": best_source,
        "pipeline": pipeline,
        "conversion_insights": {
            "top_converter": top_converter,
            "fastest_converter": fastest_converter,
            "best_business_line": best_business_line,
            "average_days_to_win": average_days_to_win,
        },
        "loss_reasons": loss_reasons, "trend": trend, "aging": aging_buckets,
        "employees": employees, "actions": actions,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


@bp.get("/owner-report")
@permission_required("reports", "view")
def owner_report():
    return jsonify(owner_report_data(request.args.get("period", "90")))

@bp.get("/owner-overview")
@permission_required("dashboard", "view")
def owner_overview():
    user = current_user()
    from routes.ai_followups import scoped_metrics, scoped_performance
    today = date.today()
    month_start = today.replace(day=1)
    open_statuses = ["new", "contacted", "qualified"]
    leads = Lead.query if user.role == "admin" else Lead.query.filter(Lead.assigned_to == user.id)
    customers = Customer.query if user.role == "admin" else Customer.query.filter(Customer.assigned_to == user.id)
    tasks = Task.query if user.role == "admin" else Task.query.filter(Task.assigned_to == user.id)
    category_rows = leads.with_entities(
        Lead.lead_category,
        func.count(Lead.id),
        func.sum(case((Lead.status.in_(open_statuses), 1), else_=0)),
        func.sum(case((Lead.status == "won", 1), else_=0)),
        func.sum(case((Lead.status == "lost", 1), else_=0)),
    ).group_by(Lead.lead_category).all()
    category_totals = {
        "course": {"name": "Courses", "total": 0, "open": 0, "won": 0, "lost": 0},
        "internship": {"name": "Internships", "total": 0, "open": 0, "won": 0, "lost": 0},
        "project": {"name": "Client Projects", "total": 0, "open": 0, "won": 0, "lost": 0},
    }
    for category, total, open_count, won_count, lost_count in category_rows:
        key = "project" if (category or "").lower() in {"business", "project"} else (category or "").lower()
        if key not in category_totals:
            continue
        stats = category_totals[key]
        stats["total"] += int(total or 0)
        stats["open"] += int(open_count or 0)
        stats["won"] += int(won_count or 0)
        stats["lost"] += int(lost_count or 0)

    for stats in category_totals.values():
        stats["conversion_rate"] = round(stats["won"] / max(stats["total"], 1) * 100, 1)

    academic = {
        metric: category_totals["course"][metric] + category_totals["internship"][metric]
        for metric in ("total", "open", "won", "lost")
    }
    project = category_totals["project"]
    total = leads.count()
    won = leads.filter_by(status="won").count()
    lost = leads.filter_by(status="lost").count()
    open_leads = leads.filter(Lead.status.in_(open_statuses)).count()
    unassigned = leads.filter(Lead.assigned_to.is_(None), Lead.status.in_(open_statuses)).count()
    stale_cutoff = today - timedelta(days=7)
    stale = leads.filter(Lead.status.in_(open_statuses), func.coalesce(Lead.last_contacted, Lead.created_at) < stale_cutoff).count()
    overdue = tasks.filter(Task.status != "done", Task.due_date < today).count()

    try:
        trend_months = int(request.args.get("trend_months", 6))
    except (TypeError, ValueError):
        trend_months = 6
    if trend_months not in {3, 6, 12}:
        trend_months = 6

    monthly_trend = []
    for months_ago in range(trend_months - 1, -1, -1):
        start = shift_month(month_start, -months_ago)
        end = shift_month(start, 1)
        monthly_trend.append({
            "name": start.strftime("%b"),
            "leads": leads.filter(Lead.created_at >= start, Lead.created_at < end).count(),
            "won": leads.filter(Lead.status == "won", Lead.updated_at >= start, Lead.updated_at < end).count(),
            "lost": leads.filter(Lead.status == "lost", Lead.updated_at >= start, Lead.updated_at < end).count(),
        })

    source_rows = leads.with_entities(
        Lead.source,
        func.count(Lead.id),
        func.sum(case((Lead.status == "won", 1), else_=0)),
        func.sum(case((Lead.status == "lost", 1), else_=0)),
    ).group_by(Lead.source).all()
    source_performance = [{
        "key": source or "unknown",
        "name": (source or "unknown").replace("_", " ").title(),
        "leads": int(source_total or 0),
        "won": int(source_won or 0),
        "lost": int(source_lost or 0),
        "conversion_rate": round(int(source_won or 0) / max(int(source_total or 0), 1) * 100, 1),
    } for source, source_total, source_won, source_lost in source_rows]
    source_performance.sort(key=lambda item: (item["leads"], item["won"]), reverse=True)

    loss_reasons = loss_reason_breakdown(leads, lost, limit=6)

    pipeline_order = [
        ("new", "New"),
        ("contacted", "Contacted"),
        ("qualified", "Qualified"),
        ("won", "Won"),
        ("lost", "Lost"),
    ]
    pipeline_counts = dict(leads.with_entities(Lead.status, func.count(Lead.id)).group_by(Lead.status).all())
    pipeline_total = sum(int(pipeline_counts.get(key, 0) or 0) for key, _ in pipeline_order)
    pipeline_snapshot = [{
        "key": key,
        "name": label,
        "value": int(pipeline_counts.get(key, 0) or 0),
        "share": round(int(pipeline_counts.get(key, 0) or 0) / max(pipeline_total, 1) * 100, 1),
    } for key, label in pipeline_order]

    return jsonify({
        "total_leads": total,
        "academic_leads": academic["total"],
        "project_leads": project["total"],
        "lost_leads": lost,
        "academic_lost": academic["lost"],
        "project_lost": project["lost"],
        "won_leads": won,
        "academic_won": academic["won"],
        "project_won": project["won"],
        "loss_rate": round(lost / max(total, 1) * 100, 1),
        "academic_loss_rate": round(academic["lost"] / max(academic["total"], 1) * 100, 1),
        "project_loss_rate": round(project["lost"] / max(project["total"], 1) * 100, 1),
        "conversion_rate": round(won / max(total, 1) * 100, 1),
        "academic_conversion_rate": round(academic["won"] / max(academic["total"], 1) * 100, 1),
        "project_conversion_rate": round(project["won"] / max(project["total"], 1) * 100, 1),
        "category_performance": list(category_totals.values()),
        "monthly_trend": monthly_trend,
        "monthly_trend_months": trend_months,
        "source_performance": source_performance,
        "loss_reasons": loss_reasons,
        "pipeline_snapshot": pipeline_snapshot,
        "open_leads": open_leads,
        "active_customers": customers.filter_by(status="active").count(),
        "unassigned_leads": unassigned, "stale_leads": stale, "overdue_tasks": overdue,
        "attention_count": unassigned + stale + overdue,
        "lost_this_month": leads.filter(Lead.status == "lost", Lead.updated_at >= month_start).count(),
        "tasks_today": tasks.filter_by(due_date=today).filter(Task.status != "done").count(),
        "completed_today": tasks.filter(func.date(Task.completed_at) == today).count(),
        "hot_leads": leads.filter_by(tag="hot").filter(Lead.status.in_(open_statuses)).count(),
        "ai_followups": scoped_metrics(user),
        "ai_followup_performance": scoped_performance(user),
    })


def shift_month(value, offset):
    month_index = value.year * 12 + value.month - 1 + offset
    return date(month_index // 12, month_index % 12 + 1, 1)

@bp.get("/category-demand")
@permission_required("dashboard", "view")
def category_demand():
    rows = db.session.query(Lead.lead_category, func.count(Lead.id)).group_by(Lead.lead_category).all()
    labels = {"course": "Courses", "internship": "Internships", "business": "Client Projects", "project": "Client Projects"}
    totals = {}
    for category, count in rows:
        label = labels.get((category or "").lower(), (category or "Other").title())
        totals[label] = totals.get(label, 0) + count
    return jsonify([{"name": name, "value": value} for name, value in sorted(totals.items(), key=lambda item: item[1], reverse=True)])

@bp.get("/lost-reasons")
@permission_required("reports", "view")
def lost_reasons():
    total = Lead.query.filter(Lead.status == "lost").count()
    return jsonify([{"name": row["name"], "value": row["count"]} for row in loss_reason_breakdown(Lead.query, total)])

@bp.get("/lead-aging")
@permission_required("reports", "view")
def lead_aging():
    today = date.today()
    open_query = Lead.query.filter(Lead.status.in_(["new", "contacted", "qualified"]))
    buckets = [("0-2 days", 0, 2), ("3-7 days", 3, 7), ("8-14 days", 8, 14), ("15+ days", 15, 36500)]
    return jsonify([{"name": name, "value": open_query.filter(Lead.created_at <= today - timedelta(days=low), Lead.created_at > today - timedelta(days=high + 1)).count()} for name, low, high in buckets])


@bp.get("/summary")
@permission_required("dashboard", "view")
def summary():
    revenue = db.session.query(func.coalesce(func.sum(Customer.value), 0)).scalar()
    deals = Customer.query.count()
    total_leads = Lead.query.count()
    won = Lead.query.filter_by(status="won").count()
    month_start = date.today().replace(day=1)
    month_revenue = db.session.query(func.coalesce(func.sum(Customer.value), 0)).filter(Customer.created_at >= month_start).scalar()
    return jsonify({
        "total_leads": total_leads,
        "active_customers": Customer.query.filter_by(status="active").count(),
        "pending_tasks": Task.query.filter_by(status="pending").count(),
        "revenue_this_month": month_revenue,
        "total_revenue": revenue,
        "deals_won": deals,
        "avg_deal_size": round(revenue / max(deals, 1)),
        "lead_to_win_rate": round(won / max(total_leads, 1) * 100, 1),
    })


@bp.get("/revenue-by-service")
@permission_required("dashboard", "view")
def revenue_by_service():
    rows = db.session.query(Customer.service, func.sum(Customer.value)).group_by(Customer.service).all()
    return jsonify([{"name": r[0], "value": r[1] or 0} for r in rows])


@bp.get("/leads-by-source")
@permission_required("dashboard", "view")
def leads_by_source():
    total = max(Lead.query.count(), 1)
    rows = db.session.query(Lead.source, func.count(Lead.id)).group_by(Lead.source).all()
    return jsonify([{"name": r[0], "count": r[1], "share": round(r[1] / total * 100, 1)} for r in rows])


@bp.get("/source-conversions")
@permission_required("reports", "view")
def source_conversions():
    lead_rows = db.session.query(
        Lead.source,
        func.count(Lead.id),
        func.sum(case((Lead.status == "won", 1), else_=0)),
        func.coalesce(func.sum(Lead.deal_value), 0),
    ).group_by(Lead.source).all()
    customer_rows = {
        row[0]: {"customers": row[1], "revenue": row[2]}
        for row in db.session.query(
        Lead.source,
        func.count(Customer.id),
        func.coalesce(func.sum(Customer.value), 0),
        ).join(Customer, Customer.lead_id == Lead.id).group_by(Lead.source).all()
    }
    result = []
    for source, total, won, pipeline_value in lead_rows:
        customer_data = customer_rows.get(source, {"customers": 0, "revenue": 0})
        customer_count = customer_data["customers"]
        revenue = customer_data["revenue"]
        total = total or 0
        won = int(won or 0)
        revenue = int(revenue or 0)
        result.append({
            "name": source or "unknown",
            "leads": total,
            "won": won,
            "customers": customer_count,
            "conversion_rate": round(won / max(total, 1) * 100, 1),
            "revenue": revenue,
            "pipeline_value": int(pipeline_value or 0),
            "avg_deal_size": round(revenue / max(customer_count, 1)),
        })
    result.sort(key=lambda row: (row["conversion_rate"], row["revenue"]), reverse=True)
    best = result[0] if result else None
    return jsonify({
        "items": result,
        "best_source": best["name"] if best else None,
        "total_sources": len(result),
        "total_revenue": sum(row["revenue"] for row in result),
    })


@bp.get("/pipeline-funnel")
@permission_required("dashboard", "view")
def pipeline_funnel():
    order = ["new", "contacted", "qualified", "won", "lost"]
    counts = dict(db.session.query(Lead.status, func.count(Lead.id)).group_by(Lead.status).all())
    return jsonify([{"name": s.title(), "value": counts.get(s, 0)} for s in order])


@bp.get("/employee-performance")
@permission_required("reports", "view")
def employee_performance():
    rows = []
    for u in User.query.all():
        assigned = Lead.query.filter_by(assigned_to=u.id).count()
        won = Lead.query.filter_by(assigned_to=u.id, status="won").count()
        done = Task.query.filter_by(assigned_to=u.id, status="done").count()
        rows.append({"name": u.name, "leads_assigned": assigned, "leads_won": won, "tasks_completed": done, "win_rate": round(won / max(assigned, 1) * 100, 1)})
    return jsonify(rows)


@bp.get("/monthly-trend")
@permission_required("reports", "view")
def monthly_trend():
    today = date.today().replace(day=1)
    data = []
    for i in range(5, -1, -1):
        start = (today - timedelta(days=31 * i)).replace(day=1)
        end = (start + timedelta(days=32)).replace(day=1)
        revenue = db.session.query(func.coalesce(func.sum(Customer.value), 0)).filter(Customer.created_at >= start, Customer.created_at < end).scalar()
        leads = Lead.query.filter(Lead.created_at >= start, Lead.created_at < end).count()
        data.append({"name": start.strftime("%b"), "revenue": revenue, "leads": leads})
    return jsonify(data)


@bp.get("/activity")
@permission_required("dashboard", "view")
def activity():
    return jsonify([x.to_dict() for x in ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(10).all()])


@bp.get("/export")
@permission_required("reports", "export")
def export_reports():
    report = owner_report_data(request.args.get("period", "90"))
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Digidara CRM Business Operational Report"])
    writer.writerow(["Period", report["period"]["label"]])
    writer.writerow(["Generated", report["generated_at"]])
    writer.writerow([])
    writer.writerow(["SUMMARY"])
    writer.writerow(["Metric", "Value"])
    for key, value in report["summary"].items():
        writer.writerow([key.replace("_", " ").title(), value])
    writer.writerow([])
    writer.writerow(["BUSINESS LINE PERFORMANCE"])
    writer.writerow(["Business Line", "Leads", "Open", "Won", "Lost", "Conversion Rate"])
    for row in report["categories"]:
        writer.writerow([row["name"], row["leads"], row["open"], row["won"], row["lost"], f'{row["conversion_rate"]}%'])
    writer.writerow([])
    writer.writerow(["SOURCE QUALITY"])
    writer.writerow(["Source", "Leads", "Won", "Lost", "Conversion Rate"])
    for row in report["sources"]:
        writer.writerow([row["name"], row["leads"], row["won"], row["lost"], f'{row["conversion_rate"]}%'])
    writer.writerow([])
    writer.writerow(["TEAM ACCOUNTABILITY"])
    writer.writerow(["Employee", "Department", "Assigned Leads", "Contacted", "Qualified", "Open Leads", "Won", "Lost", "Conversion Rate", "Average Days to Win", "Stale Leads", "Never Contacted", "Open Tasks", "Overdue Tasks", "Tasks Completed"])
    for row in report["employees"]:
        writer.writerow([row["name"], row["department"], row["leads_assigned"], row["contacted_leads"], row["qualified_leads"], row["open_leads"], row["leads_won"], row["leads_lost"], f'{row["win_rate"]}%', row["average_days_to_win"] if row["average_days_to_win"] is not None else "No wins", row["stale_leads"], row["never_contacted"], row["open_tasks"], row["overdue_tasks"], row["tasks_completed"]])
    filename = f'digidara-business-report-{report["period"]["key"]}.csv'
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})
