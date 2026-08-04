# Changelog

All notable changes to DigiDARA CRM are documented here.

## 2026-07-17

### Redesigned and improved

- Rebuilt the complete light and dark visual system around DigiDARA's indigo, brushed-gold, ivory, midnight, violet, and cyan palette.
- Redesigned the login experience and applied persistent theme switching to the full application.
- Improved desktop, tablet, and mobile layouts for navigation, cards, grids, forms, tables, drawers, modals, calendars, and communication views.
- Removed the standalone Courses page and redirected legacy AI Copilot links to AI Chat.
- Renamed Owner Reports to Reports and replaced revenue-led dashboard/report content with owner operations, lead health, demand, aging, workload, and follow-up insights.
- Removed customer revenue cards and fields from customer-facing views.
- Made dashboard, Reports, and Customer KPI cards clickable with filtered drill-down destinations.
- Connected AI Chat to authorized live lead, customer, and task records and Groq `llama3-8b-8192`, with a clearly labeled live-database fallback.
- Added AI Chat model, status, and source audit fields to the schema, model, existing-database compatibility checks, and migration.
- Added `.env.example` and expanded README/API documentation. Real secrets remain excluded from distributable ZIP files.

### Verification

- Backend Python compilation passed.
- Frontend Vite production build passed after the responsive contrast and alignment refinement.
- ZIP integrity test passed for the distributable build.

## 2026-07-09

### Added

- Added Global Search across Leads, Customers, and Tasks.
- Added a protected `GET /api/search?q=` endpoint with permission-aware result scoping.
- Connected the topbar search input to live CRM results.
- Added API documentation for the Global Search endpoint.
- Added Customer 360 with profile, relationship health, AI-style summary, timeline, messages, and tasks.
- Removed Projects and Programs modules from frontend, backend, permissions, and schema cleanup.
- Added a protected `GET /api/customers/:id/360` endpoint.
- Added Pipeline Kanban for leads with drag-and-drop stage movement.
- Added lead deal fields: deal value, probability, expected close date, and lost reason.
- Added Advanced Filters and Saved Views for Leads.
- Added Support Ticket module with priority, SLA, assignment, and ticket history database tables.
- Added Calendar agenda support using task reminders, recurrence, dependencies, and meeting fields.
- Added AI Copilot page and database-backed interaction history.
- Added Course, Batch, and Student Management module for Digidara training workflows.
- Added Core CRM bulk lead actions, CSV lead import, lead/customer/report exports, duplicate lead detection, and lead timeline.
- Added Customer Notes and Customer Document Attachments with MySQL-backed storage.
- Added recurring task automation, task reminder notifications, meeting invite tracking, and rich day/week calendar UI.
- Added AI Follow-up Automation Engine with context-aware generation, scheduling, pause/resume, send-now, manual follow-up marking, dashboard analytics, settings controls, audit history and prompt logs.
- Completed AI Lead Scoring with score factors, next-best-action recommendations, scored timestamp and bulk re-score.
- Completed AI Chat / Call Summarization with saved summary history, sentiment, key points and next action.
- Completed Source-wise Conversion Reports with leads, won deals, customers, revenue, conversion rate and average deal size by source.

## AI Scoring, Summaries, Source Conversion Reports

## Files Created

- `backend/models/communication_summary.py`
- `backend/migrations/20260711_ai_scoring_summaries_source_reports.sql`

## Files Modified

- `backend/schema.sql`
- `backend/app.py`
- `backend/models/__init__.py`
- `backend/models/lead.py`
- `backend/routes/leads.py`
- `backend/routes/communication.py`
- `backend/routes/reports.py`
- `backend/services/ai_service.py`
- `frontend/src/pages/Leads.jsx`
- `frontend/src/pages/Communication.jsx`
- `frontend/src/pages/Reports.jsx`
- `frontend/src/styles/components.css`
- `README.md`
- `docs/API.md`
- `docs/DATABASE.md`
- `CHANGELOG.md`

## Database Tables Added

- `communication_summaries`

## Tables Updated

- `leads`

## Columns Added

- `leads.ai_score_factors`
- `leads.ai_scored_at`
- `leads.ai_next_best_action`

## API Endpoints Added

- `POST /api/leads/score-all`
- `GET /api/communication/summaries`
- `POST /api/communication/summaries`
- `GET /api/reports/source-conversions`

## Frontend Pages Updated

- Leads: re-score all leads, score factors, next-best-action and scored timestamp.
- Communication: summarize thread and saved AI summary history.
- Reports: source-wise conversion analytics table and chart.

## Security Changes

- Reused existing `leads:classify`, `communication:send`, `communication:view`, and `reports:view` permissions.

## Performance Improvements

- Source conversion reporting is aggregated in SQL.
- Summary history is limited to recent records by API.

## Breaking Changes

- Existing MySQL databases must run `backend/migrations/20260711_ai_scoring_summaries_source_reports.sql` before backend startup because schema validation now expects `communication_summaries`.

## Testing Performed

- Backend Python compilation passed.
- Frontend production build passed.

## Rollback Instructions

- Hide the scoring factors, Communication summary controls and source conversion report UI.
- Keep additive columns/table for audit retention unless explicit data deletion is approved.

## AI Follow-up Automation Engine

## Files Created

- `backend/models/ai_followup.py`
- `backend/routes/ai_followups.py`
- `backend/migrations/20260711_ai_followup_engine.sql`
- `backend/.env.example`

## Files Modified

- `backend/schema.sql`
- `backend/app.py`
- `backend/models/__init__.py`
- `backend/models/lead.py`
- `backend/models/settings.py`
- `backend/routes/settings.py`
- `backend/services/ai_service.py`
- `backend/permissions.py`
- `frontend/src/App.jsx`
- `frontend/src/components/Layout/Sidebar.jsx`
- `frontend/src/permissions.js`
- `frontend/src/pages/AIFollowups.jsx`
- `frontend/src/pages/Leads.jsx`
- `frontend/src/pages/Settings.jsx`
- `frontend/src/pages/Dashboard.jsx`
- `frontend/src/styles/components.css`
- `README.md`
- `docs/API.md`
- `docs/DATABASE.md`

## Database Tables Added

- `ai_followup_history`
- `ai_followup_prompt_logs`

## Tables Updated

- `leads`
- `company_settings`

## Columns Added

- `leads.ai_followup_enabled`
- `leads.ai_followup_paused_reason`
- `leads.ai_preferred_channel`
- `leads.ai_last_followup_at`
- `leads.ai_next_followup_at`
- `leads.ai_followup_count`
- `leads.ai_engagement_score`
- `leads.ai_followup_outcome`
- `company_settings.ai_followups_enabled`
- `company_settings.ai_followup_hot_interval_days`
- `company_settings.ai_followup_warm_interval_days`
- `company_settings.ai_followup_cold_interval_days`
- `company_settings.ai_followup_business_hours`
- `company_settings.ai_followup_working_days`
- `company_settings.ai_followup_max_count`
- `company_settings.ai_followup_stop_after_no_response`
- `company_settings.ai_followup_preferred_channel`
- `company_settings.ai_followup_llm_model`

## API Endpoints Added

- `GET /api/ai-followups/lead/:lead_id`
- `POST /api/ai-followups/lead/:lead_id/generate`
- `POST /api/ai-followups/history/:id/send`
- `POST /api/ai-followups/lead/:lead_id/pause`
- `POST /api/ai-followups/lead/:lead_id/resume`
- `POST /api/ai-followups/lead/:lead_id/manual`
- `POST /api/ai-followups/run`
- `GET /api/ai-followups/workbench`
- `GET /api/ai-followups/analytics`

## Frontend Pages Updated

- Added `/ai-followups` as a dedicated AI Follow-up testing and monitoring page.
- Added sidebar navigation for AI Follow-ups.
- Added lead queue, message preview/editor, send action, run-due action, and follow-up history table.

## Testing Performed

- Backend Python compilation passed.
- Frontend production build passed.

## Rollback Instructions

- Disable AI Follow-ups in Settings.
- Leave audit tables intact for retention.
- Hide Lead drawer AI Follow-up controls if rollback is needed.

### Changed

- Updated setup documentation for MySQL-first local development.
- Updated frontend build guidance for Windows paths that contain special characters.
- Won lead conversion now carries lead deal value into the generated customer value.

### Verification

- Frontend production build passes when Vite is invoked directly through Node.
- Backend Python compilation passes.
# Owner Edition responsive UI update

- Added full light and dark theme surface coverage.
- Added large desktop, tablet and mobile layout rules.
- Improved KPI cards, owner report cards, tables, forms, modals, drawers, calendars and WhatsApp layouts.
- Improved mobile spacing, typography, actions, navigation and touch targets.
