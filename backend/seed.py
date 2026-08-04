from datetime import date, datetime, timedelta
import os
from pathlib import Path

os.environ["DIGIDARA_SKIP_AUTO_APP"] = "1"
import pymysql
from app import create_app
from extensions import db
from models import ActivityLog, Batch, Campaign, CompanySettings, Course, Customer, Lead, Notification, Student, Task, User


SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def schema_statements(sql):
    delimiter = ";"
    statement = []
    for raw_line in sql.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        if stripped.upper().startswith("DELIMITER "):
            delimiter = stripped.split(None, 1)[1]
            continue
        statement.append(line)
        if stripped.endswith(delimiter):
            query = "\n".join(statement).strip()
            query = query[:-len(delimiter)].strip()
            statement = []
            if query:
                yield query
    trailing = "\n".join(statement).strip()
    if trailing:
        yield trailing


def run_schema_sql():
    if not SCHEMA_PATH.exists():
        raise RuntimeError(f"Schema file not found: {SCHEMA_PATH}")
    print("MySQL schema is missing or incomplete. Applying backend/schema.sql automatically...")
    db_name = os.getenv("DB_NAME", "digidara_crm12").replace("`", "``")
    connection = pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            cursor.execute(f"USE `{db_name}`")
            for statement in schema_statements(SCHEMA_PATH.read_text(encoding="utf-8")):
                if statement.upper().startswith("CREATE DATABASE "):
                    continue
                if statement.upper().startswith("USE "):
                    continue
                cursor.execute(statement)
    finally:
        connection.close()
    print("Schema applied successfully.")


def ensure_user(name, login_id, email, password, phone, role, branch, department, initials, color):
    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(email=email)
        db.session.add(user)
    user.name = name
    user.login_id = login_id
    user.phone = phone
    user.role = role
    user.branch = branch
    user.department = department
    user.avatar_initials = initials
    user.avatar_color = color
    user.is_active = 1
    user.otp_enabled = 1 if phone else 0
    user.set_password(password)
    return user


def ensure_company_settings():
    settings = db.session.get(CompanySettings, 1)
    if not settings:
        settings = CompanySettings(id=1)
        db.session.add(settings)
    settings.tagline = "AI training, automation and product engineering"
    settings.about_crm = "Digidara CRM manages leads, customers, tasks, campaigns, communication and revenue reporting for Digidara Technologies."
    settings.phone = "+91 98765 43210"
    settings.gst_number = "33ABCDE1234F1Z5"
    settings.google_review_url = "https://g.page/r/CXarerFSXX1qEBM/review"
    settings.google_review_place_id = settings.google_review_place_id or ""
    settings.google_review_api_key = settings.google_review_api_key or ""
    settings.whatsapp_phone_number_id = settings.whatsapp_phone_number_id or "1234567890"
    settings.gmail_address = settings.gmail_address or "info@digidaratechnologies.com"
    settings.course_name_options = "GenAI Course\nPython Full Stack\nAI Training"
    settings.internship_name_options = "AI Internship\nML / Data Science\nWeb Development Internship"
    settings.business_service_options = "AI Product Development\nDigital Marketing\nAI Consulting\nWebsite Development\nSoftware Development"


def seed_demo_data(admin, arjun, sneha, karthik):
    if Lead.query.first():
        return False

    leads = [
        ("Priya Raman", "course", "GenAI Course", None, None, "B.Tech CSE", None, "website", "hot", "new", arjun.id),
        ("Vikram S", "internship", None, "AI Internship", None, "BCA", "2 weeks", "whatsapp", "hot", "qualified", arjun.id),
        ("Naveen Tech Labs", "business", None, None, "AI Product Development", None, None, "email", "hot", "contacted", karthik.id),
        ("Meena Raj", "course", "Python Full Stack", None, None, "M.Sc IT", None, "chatbot", "warm", "new", arjun.id),
        ("Greenline Exports", "business", None, None, "Digital Marketing", None, None, "inperson", "warm", "contacted", karthik.id),
        ("Suresh B", "internship", None, "ML / Data Science", None, "Diploma", "2 weeks", "inperson", "cold", "lost", sneha.id),
        ("Aadhya Clinics", "business", None, None, "AI Consulting", None, None, "email", "hot", "won", arjun.id),
        ("CodeNest Academy", "course", "AI Training", None, None, "Faculty", None, "website", "warm", "won", sneha.id),
    ]
    deal_values = [25000, 18000, 175000, 30000, 85000, 12000, 175000, 65000]
    probabilities = [35, 55, 70, 25, 50, 10, 100, 100]

    lead_objs = []
    for i, (name, category, course, internship, business, qualification, duration, source, tag, status, owner) in enumerate(leads):
        service = course or internship or business
        lead_objs.append(Lead(
            name=name,
            phone="+91 90000 00000",
            email=name.lower().replace(" ", ".") + "@example.com",
            company=name if category == "business" else None,
            service=service,
            lead_category=category,
            qualification=qualification,
            program_duration=duration,
            course_name=course,
            internship_name=internship,
            business_name=name if category == "business" else None,
            business_requirement=business,
            source=source,
            tag=tag,
            status=status,
            deal_value=deal_values[i],
            probability=probabilities[i],
            assigned_to=owner,
            notes="Interested in a structured consultation.",
            ai_score=88 if tag == "hot" else 61 if tag == "warm" else 35,
            ai_reason=f"{tag.title()} lead based on service fit and interest.",
            ai_score_factors=f"Seed scoring: source={source}; stage={status}; tag={tag}",
            ai_next_best_action="Contact the lead and confirm the next step.",
            city="Coimbatore",
        ))
    db.session.add_all(lead_objs)
    db.session.flush()

    db.session.add_all([
        Customer(lead_id=lead_objs[6].id, name="Aadhya Clinics", phone="+91 90000 01001", email="ops@aadhya.example", company="Aadhya Clinics", service="AI Consulting", value=175000, status="active", assigned_to=arjun.id, last_contact=date.today(), notes="Deploying AI front-desk workflow.", rating=5),
        Customer(lead_id=lead_objs[7].id, name="CodeNest Academy", phone="+91 90000 01002", email="hello@codenest.example", company="CodeNest Academy", service="AI Training", value=65000, status="followup", assigned_to=sneha.id, last_contact=date.today() - timedelta(days=2), notes="Faculty upskilling batch.", rating=4),
    ])

    db.session.add_all([
        Task(title="Call Priya for AI training proposal", related_type="lead", related_name="Priya Raman", due_date=date.today(), reminder_at=datetime.utcnow() + timedelta(hours=2), meeting_start=datetime.utcnow() + timedelta(hours=4), meeting_location="Google Meet", assigned_to=arjun.id, priority="High", status="pending", created_by=admin.id),
        Task(title="Send quote to Naveen Tech Labs", related_type="lead", related_name="Naveen Tech Labs", due_date=date.today() - timedelta(days=1), reminder_at=datetime.utcnow() - timedelta(hours=3), assigned_to=karthik.id, priority="High", status="pending", created_by=admin.id),
        Task(title="Collect feedback from CodeNest", related_type="customer", related_name="CodeNest Academy", due_date=date.today(), assigned_to=sneha.id, priority="Medium", status="pending", created_by=admin.id),
        Task(title="Update campaign analytics", related_type="internal", related_name="Marketing", due_date=date.today() + timedelta(days=1), assigned_to=karthik.id, priority="Low", status="pending", created_by=admin.id),
        Task(title="Prepare monthly revenue report", related_type="internal", related_name="Reports", due_date=date.today() - timedelta(days=3), assigned_to=admin.id, priority="Medium", status="done", completed_at=datetime.utcnow(), created_by=admin.id),
        Task(title="Follow up Greenline Exports", related_type="lead", related_name="Greenline Exports", due_date=date.today() + timedelta(days=2), assigned_to=karthik.id, priority="Medium", status="pending", created_by=admin.id),
    ])

    db.session.add_all([
        Campaign(name="May GenAI Webinar", channel="Both", audience="All leads", message_body="Hi {name}, join our GenAI webinar this week.", status="sent", sent_count=16, opened_count=9, reply_count=3, created_by=karthik.id, sent_at=datetime.utcnow() - timedelta(days=5)),
        Campaign(name="AI Consulting Follow-up", channel="Email", audience="Hot leads", message_body="Hi {name}, here is a tailored AI consulting note.", status="sent", sent_count=5, opened_count=3, reply_count=1, created_by=arjun.id, sent_at=datetime.utcnow() - timedelta(days=2)),
        Campaign(name="June Course Reminder", channel="WhatsApp", audience="Warm leads", message_body="Hi {name}, June batches are now open.", status="scheduled", scheduled_at=datetime.utcnow() + timedelta(days=3), created_by=karthik.id),
        Campaign(name="Customer Feedback Drive", channel="Email", audience="All customers", message_body="Hi {name}, tell us how your Digidara experience went.", status="draft", created_by=sneha.id),
    ])

    for i, action in enumerate(["lead_created", "lead_classified", "task_created", "campaign_sent", "customer_created", "task_completed", "lead_updated", "message_sent", "settings_updated", "employee_created"]):
        db.session.add(ActivityLog(user_id=[admin.id, arjun.id, sneha.id, karthik.id][i % 4], action=action, entity_type="crm", entity_id=i + 1, entity_name=f"Sample item {i + 1}", created_at=datetime.utcnow() - timedelta(hours=i + 1)))

    notices = [
        ("lead_assigned", "New lead assigned", "Priya Raman is ready for follow-up."),
        ("task_overdue", "Task overdue", "Send quote to Naveen Tech Labs is overdue."),
        ("campaign_done", "Campaign completed", "May GenAI Webinar finished sending."),
        ("reply_received", "New reply", "Aadhya Clinics replied to your email."),
        ("feedback", "Feedback received", "CodeNest rated the training 4 stars."),
    ]
    db.session.add_all([Notification(user_id=admin.id, type=t, title=title, body=body) for t, title, body in notices])
    return True


def seed_new_modules(admin, arjun, sneha):
    if not Course.query.first():
        genai = Course(name="GenAI Course", category="course", duration="6 weeks", fee=25000, status="active", description="Applied GenAI training for students and professionals.")
        python = Course(name="Python Full Stack", category="course", duration="12 weeks", fee=30000, status="active")
        internship = Course(name="AI Internship", category="internship", duration="4 weeks", fee=18000, status="active")
        db.session.add_all([genai, python, internship])
        db.session.flush()
        batch = Batch(course_id=genai.id, name="GenAI July Morning Batch", mentor_id=sneha.id, start_date=date.today(), end_date=date.today() + timedelta(days=42), schedule="Mon-Fri 10 AM", capacity=25, status="running")
        db.session.add(batch)
        db.session.flush()
        db.session.add(Student(name="Priya Raman", phone="+91 90000 00000", email="priya.raman@example.com", course_id=genai.id, batch_id=batch.id, status="active", attendance_percent=92, placement_status="not_started"))
    # Support tickets removed


if __name__ == "__main__":
    try:
        app = create_app()
    except RuntimeError as exc:
        message = str(exc)
        if "MySQL schema is incomplete" not in message:
            print(message)
            raise SystemExit(1)
        run_schema_sql()
        app = create_app()

    with app.app_context():
        admin = ensure_user("Digidara Admin", "admin", "admin@digidaratechnologies.com", "Admin@1234", "+916369979579", "admin", "Coimbatore", "management", "DA", "#534AB7")
        arjun = ensure_user("Arjun Kumar", "arjun", "arjun@digidaratechnologies.com", "Emp@1234", "+91 98765 11111", "employee", "Coimbatore", "sales", "AK", "#1D9E75")
        sneha = ensure_user("Sneha Thilak", "sneha", "sneha@digidaratechnologies.com", "Emp@1234", "+91 98765 22222", "employee", "Coimbatore", "support", "ST", "#BA7517")
        karthik = ensure_user("Karthik M", "karthik", "karthik@digidaratechnologies.com", "Emp@1234", "+91 98765 33333", "employee", "Coimbatore", "marketing", "KM", "#A32D2D")
        db.session.flush()

        ensure_company_settings()
        demo_seeded = seed_demo_data(admin, arjun, sneha, karthik)
        seed_new_modules(admin, arjun, sneha)
        db.session.commit()

        print("Seed completed.")
        print("Login credentials refreshed:")
        print("Admin: admin@digidaratechnologies.com / Admin@1234")
        print("Employee: arjun@digidaratechnologies.com / Emp@1234")
        if demo_seeded:
            print("Demo CRM data inserted.")
        else:
            print("Existing leads found, demo CRM data was not duplicated.")
