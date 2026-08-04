from models import Role, RolePermission


PERMISSION_ROLES = [
    {"key": "admin", "label": "Admin"},
    {"key": "staff", "label": "Staff"},
]

PERMISSION_PAGES = [
    {"key": "dashboard", "label": "Dashboard", "actions": ["view"]},
    {"key": "leads", "label": "Leads", "actions": ["view", "create", "update", "delete", "assign", "convert", "classify"]},
    {"key": "customers", "label": "Customers", "actions": ["view", "create", "update", "delete", "send_review", "sync_review"]},
    {"key": "tasks", "label": "Tasks", "actions": ["view", "create", "update", "delete", "assign", "complete"]},
    {"key": "notifications", "label": "Bell Notifications", "actions": ["view", "update"]},
    {"key": "calendar", "label": "Calendar", "actions": ["view", "schedule"]},
    {"key": "ai_chat", "label": "AI Chat", "actions": ["view", "ask"]},
    {"key": "ai_followups", "label": "AI Follow-ups", "actions": ["view", "generate", "send", "run"]},
    {"key": "workflows", "label": "Workflow Automation", "actions": ["view", "manage"]},
    {"key": "campaigns", "label": "Campaigns", "actions": ["view", "create", "update", "send", "schedule"]},
    {"key": "communication", "label": "Communication", "actions": ["view", "send"]},
    {"key": "whatsapp_messages", "label": "WhatsApp Message", "actions": ["view"]},
    {"key": "reports", "label": "Reports", "actions": ["view", "export"]},
    {"key": "employees", "label": "Employees", "actions": ["view", "create", "update", "delete"]},
    {"key": "settings", "label": "Settings", "actions": ["view", "update", "manage"]},
]

PAGE_LOOKUP = {page["key"]: page for page in PERMISSION_PAGES}
ROLE_ALIASES = {"employee": "staff", "staff": "staff", "admin": "admin"}

STAFF_DEFAULTS = {
    "dashboard": {"view"},
    "leads": {"view", "create", "update", "classify", "convert"},
    "customers": {"view", "update", "send_review", "sync_review"},
    "tasks": {"view", "create", "update", "complete"},
    "notifications": {"view", "update"},
    "calendar": {"view", "schedule"},
    "ai_chat": {"view", "ask"},
    "ai_followups": {"view", "generate", "send"},
    "communication": {"view", "send"},
    "whatsapp_messages": {"view"},
}


def permission_role(role):
    value = ROLE_ALIASES.get(role or "staff", role or "staff")
    if value in {item["key"] for item in PERMISSION_ROLES}:
        return value
    return value if Role.query.filter_by(key=value, is_active=1).first() else "staff"


def role_definitions(include_inactive=False):
    query = Role.query
    if not include_inactive:
        query = query.filter(Role.is_active == 1)
    return [role.to_dict() for role in query.order_by(Role.is_system.desc(), Role.label).all()]


def default_allowed(role, page_key, action):
    role = permission_role(role)
    if role == "admin":
        return True
    if role == "staff":
        return action in STAFF_DEFAULTS.get(page_key, set())
    return False


def serialize_permissions(role):
    role = permission_role(role)
    if role == "admin":
        return {
            page["key"]: {action: True for action in page["actions"]}
            for page in PERMISSION_PAGES
        }
    rows = RolePermission.query.filter_by(role=role).all()
    configured = {(row.page_key, row.action): bool(row.allowed) for row in rows}
    result = {}
    for page in PERMISSION_PAGES:
        page_key = page["key"]
        result[page_key] = {}
        for action in page["actions"]:
            result[page_key][action] = configured.get((page_key, action), default_allowed(role, page_key, action))
    return result


def has_permission(user, page_key, action="view"):
    if not user or not user.is_active:
        return False
    if page_key not in PAGE_LOOKUP or action not in PAGE_LOOKUP[page_key]["actions"]:
        return False
    return bool(serialize_permissions(user.role).get(page_key, {}).get(action))
