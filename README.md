# Digidara CRM

Full-stack owner-focused CRM for Digidara Technologies Pvt Ltd's course enquiries, internships and client projects: React + Vite frontend, Flask REST API, JWT authentication, RBAC, MySQL, AI Chat, WhatsApp Business API, and SMTP email.

## Project Structure

- `backend/` - Flask REST API, SQLAlchemy models, routes, seed data, and service integrations.
- `frontend/` - React + Vite CRM interface.
- `docs/` - Architecture, API, and database documentation.

## Requirements

- Python 3.10 or newer
- Node.js 18 or newer
- npm
- MySQL Server and MySQL Workbench

## Environment Setup

The backend reads environment variables from `backend/.env`.

For local development, use MySQL:

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=YOUR_MYSQL_PASSWORD
DB_NAME=digidara_crm12
```

Replace `YOUR_MYSQL_PASSWORD` with your real MySQL password in `backend/.env`. The database name is `digidara_crm12`.

Run `python seed.py` once after configuring MySQL. It applies `backend/schema.sql` automatically when tables are missing, refreshes login credentials, and inserts demo CRM data only when leads are empty.

## Run Step By Step

Open one terminal for the backend:

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python seed.py
python app.py
```

The backend runs at `http://localhost:5002`.

`python seed.py` is safe to rerun. It refreshes demo login passwords and will not duplicate demo leads when data already exists.

After updating an existing installation, rerun `backend/schema.sql` in MySQL Workbench. It adds the current permissions and CRM structures. The removed standalone Courses page is not registered by the backend or frontend; course and internship interest remains available as lead data.

For an existing production database, `backend/migrations/20260728_staff_login_otp.sql` adds the login OTP challenge table, enables two-step verification for active users with phone numbers, and sets the admin phone to `+916369979579`.

`backend/migrations/20260728_channel_integrations.sql` adds the agency-scoped `integrations` table used by Gmail and WhatsApp. Runtime precedence is environment variables, then the active integration row for `CRM_AGENCY_ID` (default `2`), then the legacy `company_settings` fields.

`backend/migrations/20260729_ai_chat_conversations.sql` adds upgrade-safe conversation IDs, titles and the conversation-history index for the persistent AI Chat history rail.

Open another terminal for the frontend:

```bash
cd frontend
npm install
npm run dev
```

The frontend runs at `http://localhost:5173`.

The frontend scripts call Vite through Node directly, so they work even when the project path contains special characters such as `&`.

```bash
cd frontend
npm run build
```

## Health Check

After starting the backend, open:

```text
http://localhost:5002/api/health
```

Expected response:

```json
{"app":"Digidara CRM","ok":true}
```

## Demo Logins

- Admin: `admin@digidaratechnologies.com` / `Admin@1234`
- Employee: `arjun@digidaratechnologies.com` / `Emp@1234`

After password validation, login sends a WhatsApp OTP to the staff member's phone stored in the database; users do not enter a phone number on the login form. The approved template defaults to `staff_login_otp` with one body variable containing the six-digit OTP. Optional environment overrides are:

```env
WHATSAPP_LOGIN_OTP_TEMPLATE_NAME=staff_login_otp
WHATSAPP_LOGIN_OTP_URL_BUTTON_ENABLED=1
WHATSAPP_COMMUNICATION_TEMPLATE_NAME=customer_communication_message
LOGIN_OTP_TTL_SECONDS=300
LOGIN_OTP_RESEND_SECONDS=60
LOGIN_OTP_MAX_ATTEMPTS=5
CRM_AGENCY_ID=2
```

Create a Utility Meta WhatsApp template named by
`WHATSAPP_COMMUNICATION_TEMPLATE_NAME` with language `en` and this body. The CRM
supplies the customer name, existing service, and transactional status update as
parameters `{{1}}`, `{{2}}`, and `{{3}}`:

```text
Hi {{1}},

This is an update regarding your existing service request for {{2}}.

Status update: {{3}}

Reply if you need clarification about this request.
```

## Environment

Copy `.env.example` to `.env`, then add your real database and integration credentials. Never commit or share `.env`. AI Chat uses a read-only planner-query-synthesis flow: the configured model selects an authorized CRM query, the server retrieves current permission-scoped database data, and the model turns that observation into a grounded decision-support answer. If the model is unavailable, the deterministic CRM query engine remains available. Chat storage defaults to 30 conversations with 50 messages per conversation and can be adjusted with `AI_CHAT_MAX_CONVERSATIONS`, `AI_CHAT_MAX_MESSAGES_PER_CONVERSATION`, and `AI_CHAT_CONTEXT_MESSAGES`.

## API Documentation

See [docs/API.md](docs/API.md).

## Product Requirements

See [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md).

## Testing Guide

See [docs/TESTING_GUIDE.md](docs/TESTING_GUIDE.md).

## Architecture Documentation

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Database Documentation

See [docs/DATABASE.md](docs/DATABASE.md).

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## Included

- JWT auth and role-aware frontend navigation
- Leads, customers, tasks, campaigns, customer WhatsApp communication logs, bell notifications, reports, employees, and settings
- Global search across leads, customers, and tasks
- Focused Customer workspace with accurate full-dataset total/active/follow-up/contact-overdue views, academic/project segmentation, responsive cards, and a simplified Customer 360 profile
- Drag-and-drop Lead Pipeline with category, priority, source, owner and lost-reason context; commercial value fields are intentionally omitted from the core Leads UI
- Aligned lead filters for category, stage, source, city and interest with user saved views
- Automatic lead intake from WhatsApp, website forms and chatbots, with source deduplication, AI classification from notes, and duplicate detection
- Lead timeline from messages and CRM activity
- Customer notes and customer document attachments
- Support tickets with priority, SLA, assignment, and resolution tracking
- Employee-focused Tasks workspace with protected assignment ownership, due/today/overdue/upcoming/completed views, concise task creation, and responsive mobile cards
- Calendar agenda driven by the same permission-scoped task assignments and due dates, with local-time-safe day/week navigation and task completion
- Recurring task automation with next occurrence creation on completion
- Legacy task reminder, recurrence, dependency and meeting-invite API fields remain compatible, but are intentionally removed from the core execution screens
- Owner-focused AI Chat backed by deterministic, permission-scoped live CRM queries across leads, customers, tasks/calendar, communication, AI follow-ups, employees, campaigns, notifications and workflows. It supports today/yesterday/this-week/this-month/last-N-days questions, academic/project segmentation, conversion calculations and owner summaries. Normal answers use detailed ChatGPT-style sections with the direct answer, business breakdown, recent movement and owner attention; a responsive record table is rendered only when the prompt explicitly contains “table” or “tabular”. The AI never executes generated SQL, and structured sections/points/tables are persisted in `ai_interactions` for accurate history reloads.
- AI Follow-up Automation Engine for context-aware lead follow-ups using LLM/fallback generation
- Dedicated AI Follow-ups page for testing generated messages, sending WhatsApp/email follow-ups, viewing lead counts, schedule status and sent-message history
- Complete AI Lead Scoring with score factors, next-best-action and bulk re-score
- AI Chat / Call Summarization with saved communication summaries and next action
- Owner Dashboard focused on total, academic and client-project leads; overall/segment conversion rates and losses; open, won and hot leads; six-month lead movement; business-line performance; source effectiveness; loss-reason intelligence; and pipeline-stage concentration (without revenue KPIs)
- Owner loss-reason analytics are supported by the upgrade-safe `idx_leads_status_lost_reason` index in `backend/schema.sql`; rerun the schema for existing MySQL installations
- Responsive Leads workspace with accurate full-dataset counts, separate Academic/Course/Internship/Project navigation, aligned status filters, paginated desktop table, mobile lead cards, and a simplified non-revenue pipeline
- Period-aware Owner Reports (30/90/180/365 days or all time) covering lead cohort conversion/loss, course/internship/project performance, acquisition-source quality, loss reasons, live owner attention, lead aging, customer contact risk and employee accountability. Sales conversion reporting adds salesperson assigned/contacted/qualified/won/lost outcomes, conversion rate, estimated creation-to-win duration, stale and never-contacted leads, task pressure, cohort funnel concentration, top converter, fastest converter and strongest business line. The matching CSV export is operational and intentionally excludes legacy revenue metrics.
- Responsive CRM Access Management workspace for owners: active/inactive user overview, secure employee creation, generated login IDs, employee role/department/branch/access editing, reusable custom roles, per-page/action permission configuration, active user counts, legacy `employee` to `staff` compatibility, last-administrator protection and self-demotion/deactivation prevention.
- Clickable dashboard, report and customer KPI cards with drill-down navigation
- Customer views focused on relationship health and execution rather than revenue cards
- Customer and task drill-down queries are supported by upgrade-safe `idx_customers_scope_status_contact` and `idx_tasks_scope_status_due` indexes in `backend/schema.sql`; rerun the schema for existing MySQL installations
- Notifications are available only from the topbar bell with unread count, All/Unread views, individual/mark-all read actions, direct task/lead/customer links, periodic refresh, and responsive mobile presentation; the standalone Notifications page has been removed
- Fully aligned responsive Communication workspace for permission-scoped customer WhatsApp sending: single recipient, personalized bulk selection, server-side `{name}`/`{phone}`/`{email}`/`{service}` replacement, scoped delivery history, balanced desktop panels, tablet stacking, and mobile cards
- Responsive read-only WhatsApp Messages workspace that consolidates bot database rows by phone, provides searchable contact conversations, complete grouped history, collapsible AI summaries, desktop/tablet split views, and a mobile list-to-chat flow
- Bell and customer message history queries use upgrade-safe `idx_notifications_user_read_created` and `idx_message_logs_recipient_sent` indexes in `backend/schema.sql`
- AI Chat provides persistent multi-message conversations, a ChatGPT-style history rail and New Chat workflow. History uses `conversation_id`, `conversation_title`, structured response fields, and the upgrade-safe `idx_ai_interactions_conversation` index in `backend/schema.sql`; rerun the schema for an existing MySQL database
- Owner reporting uses the upgrade-safe `idx_leads_report_period_status_category`, `idx_leads_report_owner_period`, `idx_leads_report_owner_status_contact`, `idx_leads_report_conversion_velocity`, and `idx_tasks_report_completed` indexes in `backend/schema.sql`; rerun the schema for an existing MySQL database
- Custom employee access roles are persisted in the `roles` table and `role_permissions`; `backend/schema.sql` removes the legacy fixed-role CHECK constraints upgrade-safely so new role keys can be assigned to `users.role`. Rerun the schema for an existing MySQL database.
- Owner Settings is organized around company/integration setup, controlled course/internship/project lead options, validated AI follow-up policies, and role-first access management. Administrator access is permanently protected; Staff/custom roles can be granted page and action permissions independently, non-view actions require page access, and every permission save records `updated_by`/`updated_at`. Integration secrets are write-only and are never returned by the settings API. Rerun `backend/schema.sql` on an existing MySQL database to add the permission audit columns/index.
- The MySQL upgrade block safely detects the legacy `leads.assigned_to_id` column before migrating assignments, so the complete schema can be rerun on both old and current databases without MySQL error 1054.
- Flask starts with the production-safe reloader/debug mode disabled by default. Set `FLASK_DEBUG=1` only for interactive development; `FLASK_HOST` and `FLASK_PORT` can override the default `127.0.0.1:5002` listener.
- Persistent light/dark theme toggle
- Business-specific responsive Login artwork representing course enquiries, internships, client projects, customer relationships, team execution and CRM analytics, with theme-safe overlays and mobile-aware cropping
- Official Digidara Technologies company logo is used consistently on Login, sidebar navigation and the browser tab
- Responsive desktop, laptop, tablet and mobile layouts across Login and every authenticated page. The topbar and desktop sidebar remain correctly anchored during vertical page scrolling, while genuinely wide tables and pipeline boards keep horizontal scrolling inside their own component. The Calendar week view fits seven days in the available desktop content width and reflows to four, two or one column on smaller displays. At tablet widths the sidebar becomes an accessible slide-out navigation drawer; dense grids reflow, settings tabs remain reachable, and page actions stack without clipping. At phone widths data tables become labelled record cards, dialogs become touch-friendly bottom sheets, and dashboard/report KPI groups remain horizontally usable without causing page overflow.
- Theme-safe shared surfaces: selecting light or dark mode updates the complete authenticated CRM interface
- AI lead classification with Groq when configured, deterministic fallback otherwise
- AI follow-up generation uses `GROQ_API_KEY` when configured and a deterministic CRM-aware fallback otherwise
- Seed data for users, leads, customers, tasks, campaigns, activity, notifications, and company settings
