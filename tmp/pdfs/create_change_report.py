from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output" / "pdf" / "Digidara_CRM_Change_Report_2026-07-29.pdf"
LOGO = ROOT / "frontend" / "public" / "assets" / "digidara-company-logo.png"

NAVY = colors.HexColor("#15143A")
PURPLE = colors.HexColor("#5A35B5")
GOLD = colors.HexColor("#C99C35")
INK = colors.HexColor("#1D2230")
MUTED = colors.HexColor("#667085")
PALE = colors.HexColor("#F5F3FA")
PALE_GOLD = colors.HexColor("#FFF8E7")
BORDER = colors.HexColor("#DDD8EA")
GREEN = colors.HexColor("#167A5B")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(
    name="CoverTitle", parent=styles["Title"], fontName="Helvetica-Bold",
    fontSize=26, leading=31, textColor=NAVY, alignment=TA_CENTER, spaceAfter=10,
))
styles.add(ParagraphStyle(
    name="CoverSub", parent=styles["Normal"], fontName="Helvetica",
    fontSize=11, leading=17, textColor=MUTED, alignment=TA_CENTER,
))
styles.add(ParagraphStyle(
    name="Section", parent=styles["Heading1"], fontName="Helvetica-Bold",
    fontSize=17, leading=21, textColor=NAVY, spaceBefore=8, spaceAfter=10,
))
styles.add(ParagraphStyle(
    name="Subsection", parent=styles["Heading2"], fontName="Helvetica-Bold",
    fontSize=12, leading=15, textColor=PURPLE, spaceBefore=8, spaceAfter=6,
))
styles.add(ParagraphStyle(
    name="BodySmall", parent=styles["BodyText"], fontName="Helvetica",
    fontSize=8.6, leading=12.5, textColor=INK, spaceAfter=5,
))
styles.add(ParagraphStyle(
    name="Callout", parent=styles["BodyText"], fontName="Helvetica-Bold",
    fontSize=9.2, leading=13.5, textColor=NAVY,
))
styles.add(ParagraphStyle(
    name="TableHead", parent=styles["Normal"], fontName="Helvetica-Bold",
    fontSize=7.5, leading=9.5, textColor=colors.white,
))
styles.add(ParagraphStyle(
    name="TableCell", parent=styles["Normal"], fontName="Helvetica",
    fontSize=7.2, leading=9.6, textColor=INK,
))
styles.add(ParagraphStyle(
    name="TableCellBold", parent=styles["Normal"], fontName="Helvetica-Bold",
    fontSize=7.2, leading=9.6, textColor=NAVY,
))
styles.add(ParagraphStyle(
    name="Footer", parent=styles["Normal"], fontName="Helvetica",
    fontSize=7.3, textColor=MUTED,
))


def p(text, style="BodySmall"):
    return Paragraph(text, styles[style])


def bullet(text):
    return Paragraph(f"- {text}", ParagraphStyle(
        name=f"Bullet-{len(text)}", parent=styles["BodySmall"],
        leftIndent=13, firstLineIndent=-8, spaceAfter=3,
    ))


def change_table(rows, widths=(54 * mm, 25 * mm, 101 * mm)):
    data = [[p("File", "TableHead"), p("Exact lines", "TableHead"), p("Change", "TableHead")]]
    for file_name, lines, change in rows:
        data.append([p(file_name, "TableCellBold"), p(lines, "TableCell"), p(change, "TableCell")])
    table = Table(data, colWidths=list(widths), repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
    ]))
    return KeepTogether([table])


def page_decor(canvas, doc):
    canvas.saveState()
    width, height = A4
    if doc.page > 1:
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(18 * mm, height - 15 * mm, width - 18 * mm, height - 15 * mm)
        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.setFillColor(NAVY)
        canvas.drawString(18 * mm, height - 11.5 * mm, "DIGIDARA CRM - CHANGE CONTROL REPORT")
    canvas.setStrokeColor(BORDER)
    canvas.line(18 * mm, 13 * mm, width - 18 * mm, 13 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 9 * mm, "Generated 29 July 2026 | Workspace: D:\\Digidara-AI-CRM-6")
    canvas.drawRightString(width - 18 * mm, 9 * mm, f"Page {doc.page}")
    canvas.restoreState()


database_rows = [
    ("backend/schema.sql", "65-99", "OTP enabled by default; creates login_otp_challenges with expiry, attempt, delivery, and duplicate-send indexes."),
    ("backend/schema.sql", "542-562", "Adds AI Chat conversation_id, conversation_title, and the scoped conversation-history index."),
    ("backend/schema.sql", "770-786", "Creates agency-scoped integrations table with provider uniqueness and lookup indexes."),
    ("backend/schema.sql", "957-968", "Upgrade-safe user phone/OTP columns and OTP delivery guard columns/index."),
    ("backend/schema.sql", "1040-1046", "Upgrade-safe AI conversation columns and legacy answer backfill."),
    ("backend/schema.sql", "1110-1115", "Upgrade-safe composite AI conversation index."),
    ("backend/schema.sql", "1213-1226", "Sets administrator phone to +916369979579 and enables OTP for active users with registered phones."),
    ("backend/schema.sql", "1300-1309", "Prevents schema reruns from replacing existing integration secrets with placeholders."),
    ("backend/schema.sql", "1310-1355", "Seeds non-secret Gmail/WhatsApp configuration structure, sender ID 957554507448611, and staff_login_otp."),
]

migration_rows = [
    ("backend/migrations/20260728_staff_login_otp.sql", "1-71", "Creates OTP challenge persistence, adds missing user OTP columns, updates admin phone, and enables OTP."),
    ("backend/migrations/20260728_login_otp_delivery_guard.sql", "1-77", "Adds send attempts, delivery status, Meta message ID, and duplicate-delivery index."),
    ("backend/migrations/20260728_channel_integrations.sql", "1-66", "Creates agency-scoped Gmail and WhatsApp integration storage."),
    ("backend/migrations/20260729_ai_chat_conversations.sql", "1-70", "Rerunnable migration for AI conversation IDs, titles, legacy backfill, and history index."),
]

backend_rows = [
    ("backend/models/user.py", "24", "Makes OTP enabled by default."),
    ("backend/models/login_otp_challenge.py", "6-22", "Defines secure OTP challenge model and delivery audit fields."),
    ("backend/models/integration.py", "6-19", "Defines agency/provider integration model."),
    ("backend/models/ai_interaction.py", "11-12", "Adds persistent AI conversation identity and title."),
    ("backend/models/__init__.py", "21-22, 49-50", "Registers LoginOtpChallenge and Integration models."),
    ("backend/config.py", "40-53", "Adds agency ID, OTP template, expiry, resend cooldown, and attempt configuration."),
    ("backend/app.py", "27-50", "Requires OTP and integration tables in production schema validation."),
    ("backend/app.py", "298-343", "Backfills and indexes AI conversation fields for SQLite/MySQL compatibility."),
    ("backend/seed.py", "69-84, 217", "Aligns seeded OTP state and administrator phone."),
    ("backend/services/integration_service.py", "1-57", "Loads and saves agency-scoped channel integrations."),
    ("backend/services/email_service.py", "10-40", "Loads Gmail settings through integration precedence and normalizes app passwords."),
    ("backend/services/whatsapp_service.py", "8-84", "Loads WhatsApp credentials and supports template URL-button parameters."),
    ("backend/routes/auth.py", "30-99", "Phone normalization, masking, OTP hashing, template delivery, and token issuing."),
    ("backend/routes/auth.py", "103-157", "Password validation, WhatsApp OTP creation, cooldown, and duplicate-send protection."),
    ("backend/routes/auth.py", "161-226", "OTP verification, attempt limits, resend, and prior-code invalidation."),
    ("backend/routes/settings.py", "49-67, 187-224", "Returns safe integration status and persists Gmail/WhatsApp settings."),
    ("backend/routes/ai_copilot.py", "504-569", "Lists conversations, loads chronological history, and creates or continues chats."),
    ("backend/routes/reports.py", "143-149, 475-498", "Business terminology and business-report CSV filename."),
]

frontend_rows = [
    ("frontend/src/context/AuthContext.jsx", "38-63", "Handles OTP-required login, verification, resend, and final session storage."),
    ("frontend/src/pages/Login.jsx", "12-88", "OTP screen, resend timer, verification flow, and accessible password visibility eye."),
    ("frontend/src/pages/Leads.jsx", "59-70", "Defines search, source, priority, city, service, value, and date filters."),
    ("frontend/src/pages/Leads.jsx", "114-245", "URL-synchronized Apply/Clear/Saved View behavior and duplicate-request prevention."),
    ("frontend/src/pages/Leads.jsx", "500-541, 764", "Complete filter panel and URL filter parser."),
    ("frontend/src/pages/AIChat.jsx", "54-129", "Conversation selection, New Chat behavior, message submission, and history loading."),
    ("frontend/src/pages/AIChat.jsx", "130-190", "ChatGPT-style recent-history rail, workspace, composer, and date formatting."),
    ("frontend/src/styles/components.css", "1821-1864", "Password eye and OTP form styling."),
    ("frontend/src/styles/components.css", "2499-2504, 2546-2548", "Lead-filter badge, Apply row, and mobile layout."),
    ("frontend/src/styles/components.css", "3320-3412", "Desktop/mobile AI conversation workspace and history drawer."),
]

wording_rows = [
    ("frontend/src/components/Layout/Topbar.jsx", "8", "Owner Dashboard changed to Business Dashboard."),
    ("frontend/src/pages/Dashboard.jsx", "22-54", "Business-focused dashboard headings and loading/error text."),
    ("frontend/src/pages/Customers.jsx", "110, 150", "Owner changed to Assigned Staff."),
    ("frontend/src/pages/Leads.jsx", "469, 554, 634", "Owner changed to Assigned Staff."),
    ("frontend/src/pages/Reports.jsx", "25-93", "Business Report and Priority Attention terminology."),
    ("frontend/src/pages/Settings.jsx", "193, 247, 331, 422", "Admin, administrator, and business-report wording."),
    ("frontend/src/pages/Tasks.jsx", "90", "Manager and assignment-focused wording."),
    ("backend/routes/ai_copilot.py", "143-459", "Generated answers use Assigned Staff and Priority Attention."),
]

test_rows = [
    ("backend/tests/test_auth_otp.py", "15-185", "OTP delivery, verification, cooldown, resend, failure, and compatibility tests."),
    ("backend/tests/test_integration_services.py", "16-99", "WhatsApp/Gmail integration precedence and agency isolation tests."),
    ("backend/tests/test_ai_chat_conversations.py", "17-82", "Persistent multi-message conversation API regression test."),
    ("backend/tests/test_schema_contract.py", "5-44", "Schema completeness and secret-preservation contract tests."),
    ("docs/API.md", "13-15, 283-285", "Documents OTP and AI conversation endpoints."),
    ("docs/DATABASE.md", "98-134", "Documents integration, OTP, and AI conversation persistence."),
    ("docs/TESTING_GUIDE.md", "135-141", "Adds OTP login and resend deployment checks."),
    ("README.md", "55-60, 97-107, 169", "Deployment migrations, OTP configuration, and AI Chat history notes."),
]


story = []
if LOGO.exists():
    logo = Image(str(LOGO), width=30 * mm, height=30 * mm)
    logo.hAlign = "CENTER"
    story.extend([Spacer(1, 22 * mm), logo, Spacer(1, 9 * mm)])
story.extend([
    p("DigiDARA CRM", "CoverTitle"),
    p("Production Change Control Report", "CoverTitle"),
    Spacer(1, 4 * mm),
    p("Complete file inventory, exact line references, database updates, migrations, UI changes, and validation evidence.", "CoverSub"),
    Spacer(1, 11 * mm),
])

summary = Table([
    [p("Report date", "TableCellBold"), p("29 July 2026", "TableCell")],
    [p("Workspace", "TableCellBold"), p("D:\\Digidara-AI-CRM-6", "TableCell")],
    [p("Primary changes", "TableCellBold"), p("WhatsApp login OTP, channel integrations, Leads filters, password visibility, persistent AI Chat conversations, and terminology cleanup.", "TableCell")],
    [p("Validation", "TableCellBold"), p("Frontend production build passed. All 12 backend tests passed.", "TableCell")],
], colWidths=[42 * mm, 120 * mm])
summary.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (0, -1), PALE_GOLD),
    ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ("TOPPADDING", (0, 0), (-1, -1), 7),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
]))
story.extend([summary, Spacer(1, 10 * mm)])

callout = Table([[p(
    "Security note: API tokens, app secrets, verify tokens, and Gmail app passwords are intentionally excluded from source-controlled SQL. The schema stores their keys and non-secret defaults while preserving deployed secret values on rerun.",
    "Callout",
)]], colWidths=[162 * mm])
callout.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), PALE_GOLD),
    ("BOX", (0, 0), (-1, -1), 0.8, GOLD),
    ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ("TOPPADDING", (0, 0), (-1, -1), 9),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
]))
story.extend([callout, PageBreak()])

story.extend([
    p("1. Executive Summary", "Section"),
    bullet("Implemented two-step login verification using the database-registered staff phone and WhatsApp template staff_login_otp."),
    bullet("Added agency-scoped Gmail and WhatsApp integration persistence with secure secret-handling precedence."),
    bullet("Added complete, URL-synchronized Leads filtering with explicit Apply and Clear behavior."),
    bullet("Added an accessible password visibility toggle without changing form submission behavior."),
    bullet("Rebuilt AI Chat as a persistent, multi-message conversation workspace with left history and New Chat."),
    bullet("Replaced user-facing Owner terminology with Business, Administrator, Assigned Staff, or Priority Attention according to context."),
    bullet("Updated schema.sql and upgrade migrations for all database-affecting changes."),
    Spacer(1, 5 * mm),
    p("Validation status", "Subsection"),
])

validation = Table([
    [p("Check", "TableHead"), p("Result", "TableHead")],
    [p("Frontend production build", "TableCellBold"), p("PASSED", "TableCell")],
    [p("Backend automated tests", "TableCellBold"), p("12 PASSED", "TableCell")],
    [p("Schema contract tests", "TableCellBold"), p("PASSED", "TableCell")],
    [p("git diff whitespace validation", "TableCellBold"), p("PASSED", "TableCell")],
    [p("Live MySQL inspection", "TableCellBold"), p("Not performed: local MySQL credentials were unavailable; no live database was modified.", "TableCell")],
], colWidths=[70 * mm, 92 * mm])
validation.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
    ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("LEFTPADDING", (0, 0), (-1, -1), 7),
    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ("TOPPADDING", (0, 0), (-1, -1), 6),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ("TEXTCOLOR", (1, 1), (1, 4), GREEN),
]))
story.extend([validation, PageBreak()])

sections = [
    ("2. Database Schema Changes", database_rows),
    ("3. Upgrade Migrations", migration_rows),
    ("4. Backend Models, Services, and APIs", backend_rows),
    ("5. Frontend and User Interface", frontend_rows),
    ("6. Terminology Corrections", wording_rows),
    ("7. Tests and Documentation", test_rows),
]

for index, (title, rows) in enumerate(sections):
    story.append(p(title, "Section"))
    if title == "2. Database Schema Changes":
        story.append(p("These references point to the current schema.sql and cover both fresh installations and upgrade-safe reruns.", "BodySmall"))
    elif title == "3. Upgrade Migrations":
        story.append(p("Each migration is additive and designed to preserve existing records and configuration.", "BodySmall"))
    story.extend([Spacer(1, 2 * mm), change_table(rows)])
    if index != len(sections) - 1:
        story.append(PageBreak())

story.extend([
    PageBreak(),
    p("8. Deployment Notes", "Section"),
    p("Existing MySQL installation", "Subsection"),
    bullet("Back up the production database before applying any schema change."),
    bullet("Run backend/schema.sql in MySQL Workbench, or apply the dated migrations in chronological order."),
    bullet("Confirm the active agency_id = 2 integration records contain deployed secret values before enabling them."),
    bullet("Restart the Flask backend so route and runtime compatibility changes are loaded."),
    bullet("Rebuild or redeploy the frontend assets."),
    bullet("Execute the authentication, integration, AI Chat, and schema regression tests."),
    Spacer(1, 4 * mm),
    p("No-database-change items", "Subsection"),
    p("The Leads filter interface, password eye icon, and terminology updates do not add or modify database columns. Their database behavior uses existing lead fields and existing API contracts.", "BodySmall"),
    Spacer(1, 4 * mm),
    p("Workspace note", "Subsection"),
    p("frontend/package-lock.json contains a pre-existing five-line deletion in the working tree. It was not part of the requested implementations and is not included as an authored change in this report.", "BodySmall"),
])

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
doc = SimpleDocTemplate(
    str(OUTPUT),
    pagesize=A4,
    rightMargin=15 * mm,
    leftMargin=15 * mm,
    topMargin=20 * mm,
    bottomMargin=18 * mm,
    title="DigiDARA CRM Production Change Control Report",
    author="OpenAI Codex",
    subject="Complete file changes and database schema update inventory",
)
doc.build(story, onFirstPage=page_decor, onLaterPages=page_decor)
print(OUTPUT)
