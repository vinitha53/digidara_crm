# Database Documentation

Database engine: MySQL

Schema file: `backend/schema.sql`

Default database name: `digidara_crm12`

## Core Tables

- `users`
- `role_permissions`
- `leads`
- `customers`
- `tasks`
- `campaigns`
- `message_logs`
- `communication_summaries`
- `meeting_invites`
- `ai_followup_history`
- `ai_followup_prompt_logs`
- `activity_log`
- `notifications`
- `company_settings`

## Change Policy

- Reuse existing tables whenever possible.
- Additive schema changes should be added to `backend/schema.sql`.
- Destructive schema changes require explicit approval.
- New production migrations should include a rollback plan.

## Global Search

The Global Search feature added on 2026-07-09 does not require database changes. It queries existing indexed business tables and caps results per module.

## Customer 360

The Customer 360 feature added on 2026-07-09 does not require database changes. It composes data from existing tables:

- `customers`
- `leads`
- `message_logs`
- `tasks`
- `activity_log`

## Removed Tables

Projects and Programs were removed from the CRM. Rerunning `backend/schema.sql` drops these old tables if they exist:

- `project_updates`
- `projects`
- `program_progress_updates`
- `program_enrollments`

## Pipeline Kanban

The Pipeline Kanban feature added on 2026-07-09 extends the existing `leads` table with additive fields:

- `deal_value INT NOT NULL DEFAULT 0`
- `probability TINYINT UNSIGNED NOT NULL DEFAULT 10`
- `expected_close_date DATE NULL`
- `lost_reason VARCHAR(255) NULL`

Index added:

- `idx_leads_expected_close (expected_close_date)`

## Owner Dashboard Intelligence

The owner dashboard uses existing lead fields for source effectiveness, pipeline distribution and loss-reason analysis. No new columns are required.

Index added for production loss-reason aggregation and filtered drill-downs:

- `idx_leads_status_lost_reason (status, lost_reason)`

Rerun `backend/schema.sql` for an existing MySQL installation. The upgrade helper adds the index only when it is missing.

## Leads Workspace Alignment

The responsive Leads workspace and `GET /leads/overview` use the existing indexed `lead_category`, `status`, `source` and primary-key fields. No additional columns, tables or indexes are required, so this UI/API alignment does not change `backend/schema.sql`.

## Customer, Task And Calendar Alignment

The focused Customer, Tasks and Calendar workspaces do not add or remove columns. Existing commercial and advanced task-planning fields remain stored for backward compatibility even though they are not displayed in the core screens.

Two composite indexes support the new permission-scoped summaries and date/status drill-downs:

- `idx_customers_scope_status_contact (assigned_to, status, last_contact)`
- `idx_tasks_scope_status_due (assigned_to, status, due_date)`

Both indexes are declared on fresh table creation and added upgrade-safely by `backend/schema.sql`. Rerun that schema in MySQL Workbench for existing installations.

## Bell Notifications And Customer Communication

Removing the standalone Notifications page does not remove the `notifications` table: task assignments and workflows still write alerts that are consumed by the topbar bell. Customer single/bulk WhatsApp sends continue to use `message_logs`, so no columns or tables were removed.

The `integrations` table stores agency-scoped Gmail and WhatsApp channel configuration as JSON. Secret values are stored in the deployed database or environment and are intentionally excluded from source-controlled schema seed data. Environment variables take precedence, followed by the active row for `CRM_AGENCY_ID`, followed by legacy `company_settings` integration fields.

Two-step login persistence is stored separately from user credentials:

- `users.phone` is the registered WhatsApp destination and `users.otp_enabled` controls whether a second step is required.
- `login_otp_challenges` stores only an HMAC digest of the six-digit OTP, expiry/attempt limits, delivery state and the Meta message identifier.
- `idx_login_otp_user_created`, `idx_login_otp_expires`, and `idx_login_otp_delivery` support cooldown, verification and delivery-deduplication checks.
- The schema sets the administrator phone to `+916369979579` and enables OTP for active users that have a registered phone.

Two composite indexes support the new scoped, newest-first queries:

- `idx_notifications_user_read_created (user_id, is_read, created_at)`
- `idx_message_logs_recipient_sent (recipient_type, recipient_id, sent_at)`

Both indexes are included for fresh installations and added upgrade-safely by `backend/schema.sql` for existing MySQL databases.

## 2026-07-10 CRM Expansion

New tables:

- `saved_views`
- `customer_notes`
- `customer_documents`
- `support_tickets`
- `ticket_history`
- `courses`
- `batches`
- `students`
- `ai_interactions`

AI Chat conversations are grouped without duplicating answer data:

- `ai_interactions.conversation_id VARCHAR(64)` identifies a user's conversation.
- `ai_interactions.conversation_title VARCHAR(160)` stores the history-rail title.
- `idx_ai_interactions_conversation (user_id, conversation_id, created_at)` supports scoped chronological history.
- Existing standalone answers are migrated to individual `legacy-<id>` conversations.

New nullable `tasks` columns:

- `reminder_at`
- `recurrence_rule`
- `dependency_task_id`
- `meeting_start`
- `meeting_end`
- `meeting_location`
- `recurrence_parent_id`
- `recurrence_next_due`
- `reminder_sent_at`
- `meeting_invite_sent_at`

Rollback plan:

- Hide the Kanban UI and stop sending these fields from the frontend.
- The additive columns can remain without affecting existing lead CRUD behavior.
- Dropping columns in production should only happen after explicit approval and backup.

## 2026-07-11 AI Follow-up Automation

New tables:

- `ai_followup_history`
- `ai_followup_prompt_logs`

New `leads` columns:

- `ai_followup_enabled`
- `ai_followup_paused_reason`
- `ai_preferred_channel`
- `ai_last_followup_at`
- `ai_next_followup_at`
- `ai_followup_count`
- `ai_engagement_score`
- `ai_followup_outcome`

New `company_settings` columns:

- `ai_followups_enabled`
- `ai_followup_hot_interval_days`
- `ai_followup_warm_interval_days`
- `ai_followup_cold_interval_days`
- `ai_followup_business_hours`
- `ai_followup_working_days`
- `ai_followup_max_count`
- `ai_followup_stop_after_no_response`
- `ai_followup_preferred_channel`
- `ai_followup_llm_model`

Migration file:

- `backend/migrations/20260711_ai_followup_engine.sql`

Rollback plan:

- Disable `company_settings.ai_followups_enabled`.
- Pause all lead automation by setting `leads.ai_followup_enabled = 0`.
- Keep history/prompt tables for audit retention unless explicit data deletion is approved.

## 2026-07-11 AI Scoring, Summaries, Source Reports

New table:

- `communication_summaries`

New `leads` columns:

- `ai_score_factors`
- `ai_scored_at`
- `ai_next_best_action`

Migration file:

- `backend/migrations/20260711_ai_scoring_summaries_source_reports.sql`

Source-wise conversion reports use existing `leads` and `customers` relationships and do not require a separate reporting table.

Rollback plan:

- Hide AI scoring factors, summary UI, and source conversion report UI if rollback is needed.
- Keep `communication_summaries` and added lead columns for audit retention unless explicit data deletion is approved.
