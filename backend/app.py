import os
from threading import Event, Thread
from flask import Flask, jsonify
from sqlalchemy import text
from config import Config
from extensions import cors, db, jwt
from routes.auth import bp as auth_bp
from routes.ai_copilot import bp as ai_copilot_bp
from routes.ai_followups import bp as ai_followups_bp
from routes.ai_followups import process_due_followups
from routes.campaigns import bp as campaigns_bp
from routes.communication import bp as communication_bp
from routes.customers import bp as customers_bp
from routes.employees import bp as employees_bp
from routes.external_sources import bp as external_sources_bp
from routes.integrations import bp as integrations_bp
from routes.leads import bp as leads_bp
from routes.notifications import bp as notifications_bp
from routes.reports import bp as reports_bp
from routes.saved_views import bp as saved_views_bp
from routes.settings import bp as settings_bp
from routes.search import bp as search_bp
from routes.tasks import bp as tasks_bp
from routes.workflows import bp as workflows_bp
from permissions import PERMISSION_PAGES, PERMISSION_ROLES, default_allowed
from models import Role, RolePermission


MYSQL_REQUIRED_TABLES = {
    "users",
    "role_permissions",
    "roles",
    "leads",
    "ai_followup_history",
    "ai_followup_prompt_logs",
    "customers",
    "customer_notes",
    "customer_documents",
    "tasks",
    "campaigns",
    "message_logs",
    "communication_summaries",
    "meeting_invites",
    "activity_log",
    "notifications",
    "company_settings",
    "saved_views",
    "ai_interactions",
    "workflow_rules",
    "workflow_rule_runs",
    "login_otp_challenges",
    "integrations",
}


def is_sqlite(app):
    return app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite")


def validate_mysql_schema(app):
    if is_sqlite(app):
        return
    with app.app_context():
        existing = set(db.session.execute(text("SHOW TABLES")).scalars().all())
        missing = sorted(MYSQL_REQUIRED_TABLES - existing)
        if missing:
            raise RuntimeError(
                "MySQL schema is incomplete. Run backend/schema.sql in MySQL Workbench "
                f"against database '{app.config['SQLALCHEMY_DATABASE_URI'].rsplit('/', 1)[-1]}' "
                f"before starting the backend. Missing tables: {', '.join(missing)}"
            )


def ensure_company_settings_columns(app):
    if not is_sqlite(app):
        return
    columns = {
        "about_crm": "TEXT",
        "whatsapp_phone_number_id": "TEXT",
        "gmail_address": "TEXT",
        "gmail_app_password": "TEXT",
        "google_review_place_id": "TEXT",
        "google_review_api_key": "TEXT",
        "course_name_options": "TEXT",
        "internship_name_options": "TEXT",
        "business_service_options": "TEXT",
        "ai_followups_enabled": "INTEGER DEFAULT 0",
        "ai_followup_hot_interval_days": "INTEGER DEFAULT 2",
        "ai_followup_warm_interval_days": "INTEGER DEFAULT 4",
        "ai_followup_cold_interval_days": "INTEGER DEFAULT 5",
        "ai_followup_business_hours": "TEXT DEFAULT '09:00-18:00'",
        "ai_followup_working_days": "TEXT DEFAULT 'Mon,Tue,Wed,Thu,Fri,Sat'",
        "ai_followup_max_count": "INTEGER DEFAULT 6",
        "ai_followup_stop_after_no_response": "INTEGER DEFAULT 4",
        "ai_followup_preferred_channel": "TEXT DEFAULT 'WhatsApp'",
        "ai_followup_llm_model": "TEXT DEFAULT 'llama3-8b-8192'",
    }
    with app.app_context():
        existing = {row[1] for row in db.session.execute(text("PRAGMA table_info(company_settings)")).all()}
        for name, kind in columns.items():
            if name not in existing:
                db.session.execute(text(f"ALTER TABLE company_settings ADD COLUMN {name} {kind}"))
        db.session.execute(text("""
            UPDATE company_settings
            SET google_review_url = 'https://g.page/r/CXarerFSXX1qEBM/review'
            WHERE id = 1 AND (google_review_url IS NULL OR google_review_url = '' OR google_review_url = 'https://g.page/r/example')
        """))
        db.session.execute(text("""
            UPDATE company_settings
            SET course_name_options = 'GenAI Course
Python Full Stack
AI Training'
            WHERE id = 1 AND (course_name_options IS NULL OR course_name_options = '')
        """))
        db.session.execute(text("""
            UPDATE company_settings
            SET internship_name_options = 'AI Internship
ML / Data Science
Web Development Internship'
            WHERE id = 1 AND (internship_name_options IS NULL OR internship_name_options = '')
        """))
        db.session.execute(text("""
            UPDATE company_settings
            SET business_service_options = 'AI Product Development
Digital Marketing
AI Consulting
Website Development
Software Development'
            WHERE id = 1 AND (business_service_options IS NULL OR business_service_options = '')
        """))
        db.session.commit()


def ensure_lead_columns(app):
    if not is_sqlite(app):
        return
    columns = {
        "lead_category": "TEXT DEFAULT 'course'",
        "qualification": "TEXT",
        "program_duration": "TEXT",
        "course_name": "TEXT",
        "internship_name": "TEXT",
        "business_name": "TEXT",
        "business_requirement": "TEXT",
        "deal_value": "INTEGER DEFAULT 0",
        "probability": "INTEGER DEFAULT 10",
        "expected_close_date": "DATE",
        "lost_reason": "TEXT",
        "lost_reason_detail": "TEXT",
        "ai_score_factors": "TEXT",
        "ai_scored_at": "DATETIME",
        "ai_next_best_action": "TEXT",
        "ai_followup_enabled": "INTEGER DEFAULT 1",
        "ai_followup_paused_reason": "TEXT",
        "ai_preferred_channel": "TEXT",
        "ai_last_followup_at": "DATETIME",
        "ai_next_followup_at": "DATETIME",
        "ai_followup_count": "INTEGER DEFAULT 0",
        "ai_engagement_score": "INTEGER DEFAULT 0",
        "ai_followup_outcome": "TEXT",
    }
    with app.app_context():
        existing = {row[1] for row in db.session.execute(text("PRAGMA table_info(leads)")).all()}
        for name, kind in columns.items():
            if name not in existing:
                db.session.execute(text(f"ALTER TABLE leads ADD COLUMN {name} {kind}"))
        db.session.execute(text("UPDATE leads SET program_duration = NULL WHERE lead_category != 'internship'"))
        db.session.execute(text("""
            UPDATE leads
            SET source = CASE lower(source)
                WHEN 'website' THEN 'website'
                WHEN 'chatbot' THEN 'chatbot'
                WHEN 'whatsapp' THEN 'whatsapp'
                WHEN 'email' THEN 'email'
                WHEN 'inperson' THEN 'inperson'
                WHEN 'in person' THEN 'inperson'
                ELSE 'website'
            END
        """))
        db.session.commit()


def ensure_lead_integration_columns(app):
    columns = {
        "source_system": "TEXT" if is_sqlite(app) else "VARCHAR(40) NULL",
        "external_id": "TEXT" if is_sqlite(app) else "VARCHAR(190) NULL",
        "external_created_at": "DATETIME",
    }
    with app.app_context():
        if is_sqlite(app):
            existing = {row[1] for row in db.session.execute(text("PRAGMA table_info(leads)")).all()}
            for name, kind in columns.items():
                if name not in existing:
                    db.session.execute(text(f"ALTER TABLE leads ADD COLUMN {name} {kind}"))
            db.session.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_leads_source_external ON leads(source_system, external_id)"))
        else:
            existing = set(db.session.execute(text("""
                SELECT COLUMN_NAME
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'leads'
            """)).scalars().all())
            for name, kind in columns.items():
                if name not in existing:
                    db.session.execute(text(f"ALTER TABLE leads ADD COLUMN {name} {kind}"))
            has_index = db.session.execute(text("""
                SELECT 1
                FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'leads'
                  AND INDEX_NAME = 'uq_leads_source_external'
                LIMIT 1
            """)).scalar()
            if not has_index:
                db.session.execute(text("ALTER TABLE leads ADD UNIQUE KEY uq_leads_source_external (source_system, external_id)"))
        db.session.commit()


def ensure_task_planning_columns(app):
    if not is_sqlite(app):
        return
    columns = {
        "reminder_at": "DATETIME",
        "recurrence_rule": "TEXT",
        "recurrence_parent_id": "INTEGER",
        "recurrence_next_due": "DATE",
        "reminder_sent_at": "DATETIME",
        "meeting_invite_sent_at": "DATETIME",
        "dependency_task_id": "INTEGER",
        "meeting_start": "DATETIME",
        "meeting_end": "DATETIME",
        "meeting_location": "TEXT",
    }
    with app.app_context():
        existing = {row[1] for row in db.session.execute(text("PRAGMA table_info(tasks)")).all()}
        for name, kind in columns.items():
            if name not in existing:
                db.session.execute(text(f"ALTER TABLE tasks ADD COLUMN {name} {kind}"))
        db.session.commit()


def ensure_user_access_columns(app):
    columns = {
        "login_id": "TEXT",
        "branch": "TEXT",
    }
    with app.app_context():
        if is_sqlite(app):
            existing = {row[1] for row in db.session.execute(text("PRAGMA table_info(users)")).all()}
            for name, kind in columns.items():
                if name not in existing:
                    db.session.execute(text(f"ALTER TABLE users ADD COLUMN {name} {kind}"))
            db.session.execute(text("""
                UPDATE users
                SET login_id = lower(substr(email, 1, instr(email, '@') - 1))
                WHERE login_id IS NULL OR login_id = ''
            """))
            db.session.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_login_id_unique ON users(login_id)"))
        else:
            existing = set(db.session.execute(text("""
                SELECT COLUMN_NAME
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'users'
            """)).scalars().all())
            mysql_columns = {
                "login_id": "VARCHAR(80) NULL",
                "branch": "VARCHAR(100) NULL",
            }
            for name, kind in mysql_columns.items():
                if name not in existing:
                    db.session.execute(text(f"ALTER TABLE users ADD COLUMN {name} {kind}"))
            has_index = db.session.execute(text("""
                SELECT 1
                FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'users'
                  AND INDEX_NAME = 'uq_users_login_id'
                LIMIT 1
            """)).scalar()
            if not has_index:
                db.session.execute(text("ALTER TABLE users ADD UNIQUE KEY uq_users_login_id (login_id)"))
        db.session.commit()


def ensure_customer_conversion_rules(app):
    if not is_sqlite(app):
        return
    with app.app_context():
        db.session.execute(text("""
            INSERT INTO customers (lead_id, name, phone, email, company, service, status, assigned_to, notes, created_at, updated_at)
            SELECT l.id, l.name, l.phone, l.email, COALESCE(l.company, l.business_name), l.service, 'active', l.assigned_to, l.notes, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            FROM leads l
            WHERE l.status = 'won'
              AND NOT EXISTS (SELECT 1 FROM customers c WHERE c.lead_id = l.id)
        """))
        db.session.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_lead_unique ON customers(lead_id) WHERE lead_id IS NOT NULL"))
        db.session.commit()


def ensure_ai_chat_columns(app):
    columns = {
        "conversation_id": "VARCHAR(64)", "conversation_title": "VARCHAR(160)",
        "model": "VARCHAR(100)", "status": "VARCHAR(30) DEFAULT 'success'", "sources": "VARCHAR(255)",
        "response_format": "VARCHAR(30) DEFAULT 'summary'", "response_data": "TEXT", "row_count": "INTEGER DEFAULT 0",
    }
    with app.app_context():
        if is_sqlite(app):
            existing = {row[1] for row in db.session.execute(text("PRAGMA table_info(ai_interactions)")).all()}
        else:
            existing = set(db.session.execute(text("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ai_interactions'")).scalars().all())
        for name, kind in columns.items():
            if name not in existing:
                db.session.execute(text(f"ALTER TABLE ai_interactions ADD COLUMN {name} {kind}"))
        db.session.execute(text("""
            UPDATE ai_interactions
            SET conversation_id = 'legacy-' || id,
                conversation_title = substr(trim(prompt), 1, 80)
            WHERE (conversation_id IS NULL OR conversation_id = '')
        """) if is_sqlite(app) else text("""
            UPDATE ai_interactions
            SET conversation_id = CONCAT('legacy-', id),
                conversation_title = LEFT(TRIM(prompt), 80)
            WHERE conversation_id IS NULL OR conversation_id = ''
        """))
        if is_sqlite(app):
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_ai_interactions_conversation
                ON ai_interactions(user_id, conversation_id, created_at)
            """))
        else:
            has_index = db.session.execute(text("""
                SELECT 1
                FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'ai_interactions'
                  AND INDEX_NAME = 'idx_ai_interactions_conversation'
                LIMIT 1
            """)).scalar()
            if not has_index:
                db.session.execute(text("""
                    ALTER TABLE ai_interactions
                    ADD KEY idx_ai_interactions_conversation (user_id, conversation_id, created_at)
                """))
        db.session.commit()


def ensure_role_permissions(app):
    with app.app_context():
        if is_sqlite(app):
            existing = {row[1] for row in db.session.execute(text("PRAGMA table_info(role_permissions)")).all()}
            column_sql = {"updated_by": "INTEGER", "updated_at": "DATETIME"}
        else:
            existing = set(db.session.execute(text("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'role_permissions'")).scalars().all())
            column_sql = {"updated_by": "INT UNSIGNED NULL", "updated_at": "DATETIME NULL"}
        for name, kind in column_sql.items():
            if name not in existing:
                db.session.execute(text(f"ALTER TABLE role_permissions ADD COLUMN {name} {kind}"))
        db.session.commit()
        for key, label, description in (("admin", "Administrator", "Full CRM access"), ("staff", "Staff", "Standard employee access")):
            if not Role.query.filter_by(key=key).first():
                db.session.add(Role(key=key, label=label, description=description, is_system=1, is_active=1))
        db.session.flush()
        configured_roles = [{"key": role.key} for role in Role.query.filter(Role.is_active == 1).all()]
        for role in configured_roles:
            role_key = role["key"]
            for page in PERMISSION_PAGES:
                for action in page["actions"]:
                    exists = RolePermission.query.filter_by(role=role_key, page_key=page["key"], action=action).first()
                    if not exists:
                        db.session.add(RolePermission(
                            role=role_key,
                            page_key=page["key"],
                            action=action,
                            allowed=1 if default_allowed(role_key, page["key"], action) else 0,
                        ))
        db.session.commit()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.url_map.strict_slashes = False
    db.init_app(app)
    jwt.init_app(app)
    cors_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
    cors_origins.extend(
        origin.strip().rstrip("/")
        for origin in os.getenv("CORS_ORIGINS", "").split(",")
        if origin.strip()
    )
    cors.init_app(app, resources={r"/api/*": {"origins": cors_origins}})

    for bp in [
        auth_bp, leads_bp, customers_bp, tasks_bp, campaigns_bp, communication_bp,
        notifications_bp, reports_bp, employees_bp, settings_bp, search_bp,
        saved_views_bp, ai_copilot_bp, ai_followups_bp,
        workflows_bp, integrations_bp, external_sources_bp,
    ]:
        app.register_blueprint(bp)

    @app.get("/api/health")
    def health():
        return jsonify({"ok": True, "app": "Digidara CRM"})

    @app.get("/")
    def index():
        return jsonify({"ok": True, "app": "Digidara CRM", "frontend": "http://localhost:5173"})

    if is_sqlite(app):
        with app.app_context():
            db.create_all()
        ensure_company_settings_columns(app)
        ensure_lead_columns(app)
        ensure_lead_integration_columns(app)
        ensure_task_planning_columns(app)
        ensure_user_access_columns(app)
        ensure_customer_conversion_rules(app)
    else:
        validate_mysql_schema(app)
        ensure_lead_integration_columns(app)
        ensure_user_access_columns(app)
    ensure_ai_chat_columns(app)
    ensure_role_permissions(app)

    return app


def start_local_followup_scheduler(app):
    if not app.config.get("AI_FOLLOWUP_TEST_MODE"):
        return None
    interval = int(app.config.get("AI_FOLLOWUP_SCHEDULER_INTERVAL_SECONDS") or 15)
    stop_event = Event()

    def worker():
        app.logger.warning(
            "AI follow-up LOCAL TEST MODE is active: hot=%sm, warm=%sm, cold=%sm",
            app.config["AI_FOLLOWUP_TEST_HOT_MINUTES"],
            app.config["AI_FOLLOWUP_TEST_WARM_MINUTES"],
            app.config["AI_FOLLOWUP_TEST_COLD_MINUTES"],
        )
        while not stop_event.wait(interval):
            with app.app_context():
                try:
                    result = process_due_followups(limit=25)
                    if any(result.values()):
                        app.logger.info("Local AI follow-up scheduler: %s", result)
                except Exception:
                    db.session.rollback()
                    app.logger.exception("Local AI follow-up scheduler failed")
                finally:
                    db.session.remove()

    Thread(target=worker, name="local-ai-followup-scheduler", daemon=True).start()
    return stop_event


app = None if os.getenv("DIGIDARA_SKIP_AUTO_APP") == "1" else create_app()


if __name__ == "__main__":
    if app is None:
        app = create_app()
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    if not debug or os.getenv("WERKZEUG_RUN_MAIN") == "true":
        start_local_followup_scheduler(app)
    app.run(
        host=os.getenv("FLASK_HOST", "127.0.0.1"),
        port=int(os.getenv("FLASK_PORT", "5002")),
        debug=debug,
    )
