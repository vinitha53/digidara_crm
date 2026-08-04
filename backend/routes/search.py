from flask import Blueprint, jsonify, request
from sqlalchemy import or_
from models import Customer, Lead, Student, Task
from permissions import has_permission
from .utils import current_user, permission_required

bp = Blueprint("search", __name__, url_prefix="/api/search")

MIN_QUERY_LENGTH = 2
MAX_RESULTS_PER_MODULE = 5


def like_term(term):
    return f"%{term.strip()}%"


def scoped(query, model, owner_field, assign_permission):
    user = current_user()
    if has_permission(user, assign_permission[0], assign_permission[1]):
        return query
    return query.filter(owner_field == user.id)


def result(module, title, subtitle, href, meta=None):
    return {
        "module": module,
        "title": title,
        "subtitle": subtitle,
        "href": href,
        "meta": meta or {},
    }


def search_leads(term):
    if not has_permission(current_user(), "leads", "view"):
        return []
    query = scoped(Lead.query, Lead, Lead.assigned_to, ("leads", "assign"))
    query = query.filter(or_(
        Lead.name.ilike(term),
        Lead.phone.ilike(term),
        Lead.email.ilike(term),
        Lead.company.ilike(term),
        Lead.service.ilike(term),
        Lead.city.ilike(term),
    ))
    return [
        result("Leads", lead.name, lead.service or lead.phone, "/leads", {
            "status": lead.status,
            "tag": lead.tag,
            "id": lead.id,
        })
        for lead in query.order_by(Lead.updated_at.desc()).limit(MAX_RESULTS_PER_MODULE).all()
    ]


def search_customers(term):
    if not has_permission(current_user(), "customers", "view"):
        return []
    query = scoped(Customer.query.filter(Customer.lead_id.isnot(None)), Customer, Customer.assigned_to, ("leads", "assign"))
    query = query.filter(or_(
        Customer.name.ilike(term),
        Customer.phone.ilike(term),
        Customer.email.ilike(term),
        Customer.company.ilike(term),
        Customer.service.ilike(term),
    ))
    return [
        result("Customers", customer.name, customer.service or customer.phone, "/customers", {
            "status": customer.status,
            "value": customer.value,
            "id": customer.id,
        })
        for customer in query.order_by(Customer.updated_at.desc()).limit(MAX_RESULTS_PER_MODULE).all()
    ]


def search_tasks(term):
    if not has_permission(current_user(), "tasks", "view"):
        return []
    query = scoped(Task.query, Task, Task.assigned_to, ("tasks", "assign"))
    query = query.filter(or_(
        Task.title.ilike(term),
        Task.notes.ilike(term),
        Task.related_name.ilike(term),
    ))
    return [
        result("Tasks", task.title, task.related_name or task.priority, "/tasks", {
            "status": task.status,
            "priority": task.priority,
            "id": task.id,
        })
        for task in query.order_by(Task.created_at.desc()).limit(MAX_RESULTS_PER_MODULE).all()
    ]


def search_students(term):
    if not has_permission(current_user(), "education", "view"):
        return []
    query = Student.query.filter(or_(
        Student.name.ilike(term),
        Student.phone.ilike(term),
        Student.email.ilike(term),
    ))
    return [
        result("Students", student.name, (student.course.name if student.course else student.phone), f"/leads?search={student.name}", {
            "status": student.status,
            "id": student.id,
        })
        for student in query.order_by(Student.created_at.desc()).limit(MAX_RESULTS_PER_MODULE).all()
    ]


@bp.get("/")
@permission_required("dashboard", "view")
def global_search():
    query = (request.args.get("q") or "").strip()
    if len(query) < MIN_QUERY_LENGTH:
        return jsonify({"query": query, "items": [], "total": 0})

    term = like_term(query)
    items = (
        search_leads(term)
        + search_customers(term)
        + search_tasks(term)
        + search_students(term)
    )
    return jsonify({"query": query, "items": items, "total": len(items)})
