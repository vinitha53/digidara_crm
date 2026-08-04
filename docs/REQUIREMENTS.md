# Digidara CRM Requirements Document

Version: 1.0

Date: 2026-07-20

Product: Digidara CRM

## 1. Purpose

Digidara CRM is a web-based customer relationship management system for Digidara Technologies. It manages academic enquiries, internship enquiries, client project leads, customer relationships, tasks, campaigns, communication logs, AI follow-ups, reports, employees, settings and role-based access.

The product is intended for internal CRM users such as owners, administrators and staff members.

## 2. Technology Requirements

Backend:

- Python 3.10 or newer
- Flask REST API
- SQLAlchemy ORM
- JWT authentication
- MySQL database

Frontend:

- Node.js 18 or newer
- npm
- React 18
- Vite

Database:

- MySQL Server
- Default CRM database name: `digidara_crm12`
- Schema file: `backend/schema.sql`

Supported local URLs:

- Backend API: `http://localhost:5000`
- Frontend app: `http://localhost:5173`

## 3. User Roles And Access

The system supports role-based access control.

Default roles:

- Administrator: full CRM access.
- Staff: limited operational access.

The system must support custom reusable roles through Employee Access Management.

Permission areas:

- Dashboard
- Leads
- Customers
- Tasks
- Bell Notifications
- Calendar
- AI Chat
- AI Follow-ups
- Campaigns
- Communication
- WhatsApp Messages
- Reports
- Employees
- Settings
- Workflow Automation

Access rules:

- Users must log in before accessing CRM pages.
- Users without a page's `view` permission must see a permission error or be prevented from accessing that page.
- Staff users must only see records allowed by their scope, such as assigned leads, customers and tasks.
- Administrators must be protected from accidentally removing the final active administrator.
- Users must not be allowed to deactivate or demote their own administrator access.

## 4. Authentication Requirements

The system must provide:

- Login with email and password.
- JWT-secured API access.
- Session restore through stored authentication state.
- Logout.
- Current user lookup.
- Password change.

Seeded demo users:

- Admin: `admin@digidaratechnologies.com` / `Admin@1234`
- Employee: `arjun@digidaratechnologies.com` / `Emp@1234`

## 5. Functional Requirements

### 5.1 Dashboard

The dashboard must show owner-focused CRM metrics including:

- Total lead counts.
- Academic lead counts.
- Client project lead counts.
- Conversion and loss rates.
- Open, won, hot and lost lead summaries.
- Category performance.
- Lead movement trends.
- Source effectiveness.
- Loss-reason intelligence.
- Pipeline-stage concentration.

Dashboard KPI cards must support drill-down navigation where applicable.

### 5.2 Leads

The Leads module must support:

- Create, view, update and delete leads based on permissions.
- Lead categories: course, internship and business/client project.
- Lead fields including name, phone, email, service/interest, source, status, tag, city, owner and notes.
- Stage/status tracking: new, contacted, qualified, won and lost.
- Category navigation for all, academic, course, internship and project leads.
- Filters for status, source, city and interest.
- Paginated desktop table and responsive mobile cards.
- Bulk actions.
- CSV import.
- Duplicate detection.
- CSV export.
- Lead timeline from CRM activity and communication logs.
- AI classification and scoring.
- Pipeline view.

Conversion behavior:

- Moving a lead to won must require conversion permission.
- Won leads may create or link to customer records.
- Lost leads should support a loss reason.

### 5.3 Customers

The Customers module must support:

- Create, view, update and delete customers based on permissions.
- Customer overview counts.
- Active, follow-up and contact-overdue views.
- Academic/project segmentation.
- Customer 360 profile.
- Customer notes.
- Customer document attachments.
- Send review request.
- Sync review information where integration settings are configured.
- CSV export.

The Customer 360 profile must include customer details, linked lead data when available, relationship health, recent messages, tasks, activity and timeline.

### 5.4 Tasks

The Tasks module must support:

- Create, view, update, delete and complete tasks based on permissions.
- Assignment to users where the signed-in user has assignment permission.
- Staff users without assignment permission must retain their own assignment.
- Filter tasks by status, priority, assignee and operational views such as today, upcoming and overdue.
- Task completion from both Tasks and Calendar.
- Due reminder and invite endpoints may remain API-compatible.

### 5.5 Calendar

The Calendar module must:

- Show due-dated tasks in a calendar layout.
- Support date range navigation.
- Use the same task permission scope as the Tasks module.
- Allow task completion where the user has permission.

### 5.6 Campaigns

The Campaigns module must support:

- Create campaigns.
- Edit campaigns.
- Send campaigns.
- Schedule campaigns.
- View campaign statistics.

Access must follow campaign permissions.

### 5.7 Communication

The Communication module must support:

- Permission-scoped customer recipient lookup.
- Single WhatsApp message sending.
- Bulk personalized WhatsApp sending.
- Server-side template replacement for `{name}`, `{phone}`, `{email}` and `{service}`.
- Message log viewing.
- AI communication summaries.

WhatsApp delivery depends on valid integration credentials. Without credentials, the system should still provide clear failure handling and preserve safe CRM behavior.

### 5.8 WhatsApp Messages

The WhatsApp Messages workspace must:

- Show read-only WhatsApp conversation sessions from the bot database.
- Allow searching contacts/conversations.
- Show complete grouped message history.
- Show AI summaries where available.
- Support desktop/tablet split view and mobile list-to-chat flow.

### 5.9 AI Chat

The AI Chat module must:

- Answer CRM questions using permission-scoped live CRM records.
- Support questions about leads, customers, tasks/calendar, communication, AI follow-ups, employees, campaigns, notifications and workflows.
- Support date phrases such as today, yesterday, this week, this month and last N days.
- Provide structured answers.
- Render tables only when the user explicitly asks for a table or tabular output.
- Persist chat history in `ai_interactions`.
- Avoid executing generated SQL.

### 5.10 AI Follow-ups

The AI Follow-ups module must:

- Show workbench and analytics data.
- Generate lead follow-up messages.
- Send generated or edited messages.
- Pause and resume lead automation.
- Mark manual follow-ups.
- Run due follow-up processing for permitted users.

Automation stop conditions must include closed/won/lost/converted leads, converted customers, paused leads, no-contact notes and maximum follow-up count.

### 5.11 Reports

The Reports module must provide:

- Owner operating report.
- Period filters: 30, 90, 180, 365 days and all time.
- Lead conversion/loss reporting.
- Category demand.
- Lost reasons.
- Lead aging.
- Source conversions.
- Pipeline funnel.
- Employee performance.
- Monthly trend.
- Activity.
- CSV export where permitted.

Reports should focus on operational CRM performance and avoid legacy revenue KPIs where intentionally removed.

### 5.12 Employees And Roles

The Employees module must support:

- View active/inactive CRM users.
- Create employees.
- Edit employee identity, department, branch, role and access state.
- Generate unique login IDs.
- Create custom roles.
- Edit role permissions.
- Show role user counts.
- Protect administrator access.

### 5.13 Settings

The Settings module must support:

- Company profile settings.
- Integration settings.
- Lead option management for courses, internships and business services.
- AI follow-up policy settings.
- Permissions management.

Integration secrets must be write-only and must not be returned to the frontend after saving.

### 5.14 Notifications

The system must provide a topbar bell for notifications.

Requirements:

- Show unread count.
- List all and unread notifications.
- Mark one notification as read.
- Mark all notifications as read.
- Link task/lead/customer notifications to relevant pages when possible.
- There must be no standalone Notifications page; `/notifications` redirects to dashboard.

### 5.15 Global Search

Global search must:

- Search leads, customers and tasks.
- Require at least two search characters.
- Return only modules the user can view.
- Respect staff record scoping.
- Navigate users to relevant module pages.

### 5.16 Theme And Responsive UI

The frontend must support:

- Light and dark themes.
- Desktop sidebar.
- Tablet/mobile navigation drawer.
- Responsive tables/cards.
- No page-level horizontal overflow except intentionally scrollable wide tables or boards.
- Mobile-friendly dialogs and forms.

## 6. Non-Functional Requirements

Security:

- Protected endpoints require JWT authentication.
- API actions must enforce backend permissions.
- Frontend permissions are for navigation/UI only and must not replace backend checks.
- Secrets must not be displayed after saving.

Reliability:

- `python seed.py` must be safe to rerun.
- Existing demo leads must not duplicate.
- Schema setup must create/use `digidara_crm12`.
- Backend startup must validate required MySQL tables.

Performance:

- Lists must support pagination or capped result sets.
- Search and reports must use permission-scoped queries.
- Large tables/boards must remain usable with horizontal scrolling inside the component.

Compatibility:

- Backend health endpoint must return a successful response.
- Removed pages must redirect or remain inaccessible without breaking navigation.
- Legacy API-compatible fields may remain stored even when not shown in the UI.

## 7. External Integrations

Optional integrations:

- WhatsApp Business API
- SMTP/Gmail email
- Google Reviews
- Groq for AI generation

If integration credentials are missing, QA should verify that the system handles failures clearly and does not crash.

## 8. Acceptance Criteria

The product is ready for testing handoff when:

- Backend starts without schema errors.
- Frontend starts and loads login page.
- Admin and staff demo users can log in.
- Main modules load without blank screens.
- CRUD operations work according to role permissions.
- Staff users cannot access admin-only features.
- Seed data exists and is not duplicated on rerun.
- Reports, dashboard and search show permission-scoped data.
- Responsive layouts work on desktop, tablet and mobile widths.
- Build command completes successfully.

