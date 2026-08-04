# API Documentation

Base URL: `http://localhost:5000/api`

Authentication: protected endpoints require a JWT access token in the `Authorization` header.

```http
Authorization: Bearer <access_token>
```

## Auth

- `POST /auth/login` validates email/login ID and password, reads the registered staff phone from the database, then sends a WhatsApp OTP using `staff_login_otp`.
- `POST /auth/verify-otp` exchanges a valid six-digit login OTP for access and refresh tokens.
- `POST /auth/resend-otp` sends a replacement OTP after the resend cooldown.
- `POST /auth/logout`
- `GET /auth/me`
- `POST /auth/change-password`
- `POST /auth/refresh`

## Global Search

### `GET /search`

Searches across CRM modules the logged-in user is allowed to view.

Query parameters:

- `q` - Search text. Minimum 2 characters.

Example:

```http
GET /api/search?q=priya
```

Response:

```json
{
  "query": "priya",
  "total": 1,
  "items": [
    {
      "module": "Leads",
      "title": "Priya Raman",
      "subtitle": "GenAI Course",
      "href": "/leads",
      "meta": {
        "id": 1,
        "status": "new",
        "tag": "hot"
      }
    }
  ]
}
```

Search coverage:

- Leads: name, phone, email, company, service, city
- Customers: name, phone, email, company, service
- Tasks: title, notes, related name

Permission behavior:

- Users must have `dashboard:view`.
- Module results are included only when the user has that module's `view` permission.
- Staff users see scoped records only, matching the existing module ownership rules.

## Main CRM Endpoints

- `/leads`
- `/integrations/leads`
- `/ai-followups`
- `/customers`
- `/tasks`
- `/notifications` (topbar bell API; there is no standalone Notifications page)
- `/campaigns`
- `/communication`
- `/reports`
- `/employees`
- `/settings`

### Employees and custom roles

- `GET /employees` returns CRM users with resolved role labels, access state and login metadata.
- `POST /employees` creates a CRM user with an active role and generated unique login ID.
- `PUT /employees/:id` updates identity, department, branch, role or active access. Users cannot demote/deactivate themselves, and the final active administrator is protected.
- `GET /employees/roles` returns system/custom roles, user counts, page definitions and the complete permission matrix.
- `POST /employees/roles` creates a reusable custom role from a permission template or explicit permission matrix. Administrator access is required.
- `PUT /employees/roles/:key` updates custom role metadata or any role permission matrix. Administrator access is required.
- Existing `employee` user rows resolve to the system `staff` role for backward compatibility.

### Owner dashboard

- `GET /reports/owner-overview` returns total, academic (course + internship), and client-project lead counts; overall and segment conversion/loss counts and rates; category performance; six-month lead/win/loss movement; source effectiveness; loss-reason distribution; and pipeline-stage concentration. Conversion rate is `won leads / total leads * 100`.
- Dashboard drill-downs use `GET /leads?segment=academic|project`, `status=won|lost`, `stage=open`, `source=:source`, or `lost_reason=:reason`; these filters can be combined.

## Leads And Pipeline

The Leads module supports both table and Kanban pipeline workflows.

- `GET /leads/overview` returns permission-scoped full-dataset totals for all, academic, course, internship and client-project leads plus status counts. The Leads page uses this endpoint so category totals are not limited to the current paginated page.
- `GET /leads` supports pagination with `page` and `per_page`, category navigation with `lead_category` or `segment`, and combinable status/source/city/service filters.

Pipeline stages are stored in the existing `status` field:

- `new`
- `contacted`
- `qualified`
- `won`
- `lost`

Deal fields:

- `deal_value` - Non-negative integer value for the opportunity.
- `probability` - Integer from 0 to 100.
- `expected_close_date` - Optional close date.
- `lost_reason` - Required by convention when a deal is moved to `lost`; defaults to `Not specified` if omitted.

These legacy-compatible commercial fields remain available through the API, but the core Leads table, form and pipeline no longer display them. The workspace is focused on category, interest, source, owner, priority and stage.

Updating a pipeline stage uses the existing lead update endpoint:

```http
PUT /api/leads/:id
```

Example:

```json
{
  "status": "qualified",
  "deal_value": 85000,
  "probability": 65,
  "expected_close_date": "2026-07-31"
}
```

Permission behavior:

- Requires `leads:update`.
- Moving a lead to `won` also requires `leads:convert`.
- Staff users can only update leads visible through existing lead scoping.

## External Lead Intake

`POST /integrations/leads` accepts leads from separate apps such as the WhatsApp bot, chatbot, and website enquiry forms. This endpoint does not use JWT login; it uses a shared API key plus HMAC signature so another domain can push data without direct CRM database access.

Required headers:

- `X-CRM-API-Key`
- `X-CRM-Timestamp` as Unix seconds
- `X-CRM-Signature` as HMAC SHA256 hex of `timestamp.raw_json_body`, using `CRM_INTEGRATION_SIGNING_SECRET`

Example body:

```json
{
  "source_system": "whatsapp",
  "external_id": "wa_919876543210_2026-07-21",
  "name": "Priya",
  "phone": "919876543210",
  "lead_category": "course",
  "course_name": "GenAI Course",
  "message": "Interested in course details"
}
```

The CRM stores the row as a normal lead, sets `source` from the source system, and uses `source_system + external_id` to update duplicate external records instead of creating repeated leads.

## Customers

### `GET /customers/overview`

Returns permission-scoped full-dataset counts for `total`, `active`, `followup`, `contact_overdue`, and academic/course/internship/project segments. Contact overdue means an active/follow-up relationship has no `last_contact` or was last contacted at least seven days ago.

### `GET /customers`

Supports `search`, `status`, `attention=contact_overdue`, `segment=academic|course|internship|project`, and `page`. Each row includes its source lead category and the business-specific course, internship, or project interest used by the focused Customer workspace.

### `GET /customers/:id/360`

Returns a Customer 360 profile for the selected customer.

Response sections:

- `customer` - Customer relationship profile.
- `lead` - Source lead, when the customer was converted from a lead.
- `health` - Relationship score, status label, open tasks, overdue tasks, and message count.
- `ai_summary` - Rule-based relationship summary generated from existing CRM records.
- `messages` - Recent customer communication logs.
- `tasks` - Related customer tasks.
- `activity` - Related customer and source lead activity logs.
- `timeline` - Unified timeline assembled from lead, communication, task, and activity records.

Permission behavior:

- Requires `customers:view`.
- Staff users only access customers visible through existing customer scoping.

## Tasks And Calendar

- `GET /tasks` returns the permission-scoped task list and supports `status`, `assigned_to`, `priority`, and `view=today|upcoming|overdue`.
- `GET /tasks/assignees` returns all active employees only to users with `tasks:assign`; other users receive only their own user record.
- `POST /tasks` and `PUT /tasks/:id` force staff without `tasks:assign` to retain their own assignment, even when another `assigned_to` is submitted directly to the API.
- `GET /tasks/calendar?start=YYYY-MM-DD&end=YYYY-MM-DD` returns due-dated tasks for the same task scope. The core Calendar intentionally uses task due dates as its single source of truth.
- `POST /tasks/:id/complete` completes visible work and remains available from both Tasks and Calendar.

Legacy reminder, recurrence, dependency and meeting-invite fields and endpoints remain API-compatible for existing integrations, but are no longer shown in the core Tasks and Calendar screens.

## Bell Notifications

- `GET /notifications?limit=30` returns only the authenticated user's newest notifications; `unread=1` limits the result to unread items and `limit` is capped at 100.
- `POST /notifications/:id/read` marks one notification owned by the authenticated user as read.
- `POST /notifications/read-all` marks all notifications owned by that user as read.
- Task notifications link to Tasks, matched workflow notifications link to their scoped lead/customer, and general alerts remain inside the bell without redirecting to a removed page.

## Customer WhatsApp Communication

- `GET /communication/customer-recipients` returns up to 200 permission-scoped converted customers and supports `status` and `search` filters.
- `POST /communication/quick-send` sends a single WhatsApp message when `recipient_type=customer`; customer ownership is checked server-side.
- `POST /communication/bulk-whatsapp` accepts `customer_ids`, sends an individually personalized WhatsApp message to each accessible customer, caps each request at 200 unique IDs, and reports sent/skipped/failed/missing totals. Legacy `lead_ids` requests remain compatible.
- `GET /communication/message-log?recipient_type=customer` returns recent delivery logs scoped to customers/leads the user may access.
- `{name}`, `{phone}`, `{email}`, and `{service}` tokens are replaced server-side for both single and bulk sends.
- `POST /communication/sync-whatsapp-leads` reads unique contacts from the configured WhatsApp bot database and creates or updates CRM leads with `source=whatsapp`, so the same bot contacts reflect in the Lead Dashboard and source reports. Requires `leads:create`.

## AI Follow-up Automation

AI follow-ups are integrated into Leads, Settings, Communication logs and Dashboard analytics.

Endpoints:

- `GET /ai-followups/lead/:lead_id` - Lead follow-up status and history.
- `POST /ai-followups/lead/:lead_id/generate` - Generate/regenerate a context-aware follow-up.
- `POST /ai-followups/history/:id/send` - Send generated or edited follow-up.
- `POST /ai-followups/lead/:lead_id/pause` - Pause automation for a lead.
- `POST /ai-followups/lead/:lead_id/resume` - Resume automation and schedule next follow-up.
- `POST /ai-followups/lead/:lead_id/manual` - Mark a manual follow-up.
- `POST /ai-followups/run` - Admin scheduler endpoint to process due leads.
- `GET /ai-followups/workbench` - Dedicated testing and monitoring dataset for the AI Follow-ups page.
- `GET /ai-followups/analytics` - Dashboard metrics.

Stop conditions:

- Lead status is won, lost, converted, closed, or not interested.
- Lead has converted to a customer.
- Automation is paused on the lead.
- Lead notes indicate no further communication.
- Maximum follow-up count is reached.

Generated messages use previous CRM message logs, tasks, lead notes, activity, lead temperature, stage, score, source, interest and assigned salesperson context.

## AI Lead Scoring

Endpoints:

- `POST /leads/:id/classify` - Scores one lead and updates `tag`, `ai_score`, `ai_reason`, score factors and next-best-action.
- `POST /leads/score-all` - Re-scores all visible active leads.

The scoring engine uses lead source, stage, deal value, contact completeness, message activity and open tasks. If Groq is configured it asks the LLM for scoring; otherwise it uses a deterministic production fallback.

## AI Chat / Call Summarization

Endpoints:

- `GET /communication/summaries` - Lists saved AI communication summaries.
- `POST /communication/summaries` - Generates and saves a summary for a lead/customer/employee message thread.

Summaries include summary text, key points, sentiment, next action, model used and message count.

## Owner Reports

Endpoints:

- `GET /reports/owner-report?period=90` returns one complete owner-operating report. Supported periods are `30`, `90`, `180`, `365`, and `all`. The response separates selected-period lead/customer/completed-task performance from current open-lead, overdue-task and customer-contact risks. It also returns cohort funnel concentration and salesperson conversion/follow-up performance; average days to win is an estimate from lead creation to the final won-status update.
- `GET /reports/export?period=90` exports the matching operational view as CSV, including summary, business-line performance, source quality and salesperson assigned/contacted/qualified/won/lost conversion accountability. Revenue and pipeline-value fields are intentionally excluded.
- Legacy granular report endpoints remain available for compatible integrations, but the Reports page uses `owner-report` as its single source of truth.
# AI Chat

- `GET /api/ai-chat/capabilities` returns the signed-in user's authorized CRM data areas, query scope and table row limit.
- `GET /api/ai-chat/conversations` returns up to 50 persisted conversation summaries for the signed-in user.
- `GET /api/ai-chat/history?conversation_id=:id` returns one conversation in chronological order. Omitting the ID preserves the legacy recent-answer response.
- `POST /api/ai-chat/ask` accepts `{ "prompt": "...", "conversation_id": "optional-existing-id" }`. A missing ID starts a new persisted conversation; subsequent questions reuse the returned `conversation_id`. The endpoint runs deterministic permission-scoped queries against live CRM data and never executes model-generated SQL.
